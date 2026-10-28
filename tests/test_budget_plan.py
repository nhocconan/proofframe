"""Budget behaviour of the audits: pre-run plan, partial results on a budget stop, in-flight reservation wait."""
from __future__ import annotations

import threading
import time
import uuid

import pytest

from proofframe.interfaces import AssetInput, BudgetExhausted
from proofframe.providers.meta import CallResult, _WaitingBudget
from proofframe.verify import anomaly, plan
from proofframe.verify.pipeline import run_verification
from tests.test_continuity import LogFake, _three_shot_clip
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore

FIVE_MIN_SHOTS = [(i * 4600, (i + 1) * 4600) for i in range(65)]


def five_min() -> plan.Workload:
    return plan.Workload(assertion_minutes=[5] * 6, scan_spans_ms=[300_000], continuity_shots=[FIVE_MIN_SHOTS])


def test_full_plan_when_budget_unknown_or_sufficient():
    w = plan.Workload(scan_spans_ms=[60_000], continuity_shots=[FIVE_MIN_SHOTS[:13]])
    for budget in (None, 10.0):
        p = plan.fit(w, budget)
        assert p.reductions == [] and p.fits and p.estimate_usd == p.full_estimate_usd
        assert p.max_suspicions == 24 and p.grid_step_ms == 2000


def test_long_film_plan_shrinks_in_order_and_records_reductions():
    p = plan.fit(five_min(), 2.0)
    assert p.full_estimate_usd > 2.0 and p.estimate_usd < p.full_estimate_usd
    assert p.reductions[0].startswith("long-range registry pairs 12")
    assert p.fits == (p.estimate_usd <= 2.0)
    assert [len(p.limits("scan")), len(p.limits("continuity"))] == [0, 1]  # one line per affected stage
    assert p.limits("continuity")[0].startswith("budget plan (est. $2.06 full vs $2.00 available)")


def test_reductions_skip_absent_stages():
    p = plan.fit(plan.Workload(scan_spans_ms=[600_000]), 0.05)
    assert p.reductions and all(r.startswith("artifact-scan") for r in p.reductions)
    assert not p.fits  # still too expensive: reported, not hidden


def test_decide_scan_budget_stop_never_passes_but_keeps_confirmed_fail():
    conf = [{"verdict": "confirmed", "severity": "major", "category": "object", "start_ms": 0, "end_ms": 1000,
             "description": "bottle"}]
    kw = dict(candidates_total=1, adjudicated=1, frames_scanned=10, calls_failed=0)
    assert anomaly.decide_scan(conf, **kw, budget_skipped=3, calls_total=8)[0] == "FAIL"
    st, why = anomaly.decide_scan([], **kw, budget_skipped=3, calls_total=8)
    assert st == "UNCERTAIN" and "3 of 8" in why
    assert anomaly.decide_scan([], **kw, budget_skipped=8, calls_total=8)[0] == "NOT_CHECKED"


class OneSlotBudget:
    """Cap fits one upper-bound reservation; real cost is far lower once settled."""

    def __init__(self):
        self.spent, self.rows = 0.0, {}

    def reserve(self, *, amount_usd, **_):
        if self.spent + amount_usd > 1.0:
            raise BudgetExhausted("cap")
        rid = uuid.uuid4().hex
        self.spent += amount_usd
        self.rows[rid] = amount_usd
        return rid

    def settle(self, rid, *, cost_usd, **_):
        self.spent += cost_usd - self.rows.pop(rid)


def test_waiting_budget_retries_after_in_flight_call_settles():
    b = _WaitingBudget(OneSlotBudget())
    first = b.reserve(run_id="r", provider="p", model="m", amount_usd=0.9, purpose="x")
    got = {}

    def second():
        got["rid"] = b.reserve(run_id="r", provider="p", model="m", amount_usd=0.9, purpose="y")

    t = threading.Thread(target=second)
    t.start()
    time.sleep(0.2)
    assert "rid" not in got  # waiting, not refused
    b.settle(first, cost_usd=0.05, cost_basis="x", usage=None, remote_request_id=None, outcome="ok")
    t.join(timeout=5)
    assert got.get("rid")


def test_waiting_budget_refuses_when_nothing_in_flight():
    b = _WaitingBudget(OneSlotBudget())
    with pytest.raises(BudgetExhausted):
        b.reserve(run_id="r", provider="p", model="m", amount_usd=1.5, purpose="x")


class StopAfter(LogFake):
    """Budget runs out after `n` successful adjudications."""

    def __init__(self, verdict, n):
        super().__init__(verdict)
        self.left = n
        self.lock = threading.Lock()

    def observe_images(self, *, images, purpose, **kw):
        if purpose.startswith("continuity_adjudicate"):
            with self.lock:
                self.left -= 1
                stop = self.left < 0
            if stop:
                t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "budget_exhausted",
                     "cost_usd": 0.0, "error": "run cap would be exceeded"}
                self.traces.append(t)
                return CallResult(ok=False, parsed=None, trace=t, outcome="budget_exhausted")
        return super().observe_images(images=images, purpose=purpose, **kw)


class PlannedBudget(CapBudget):
    def remaining(self, *, run_id):
        return 0.30


def _contract():
    return {"schema_version": "proofframe.contract.v0.1", "contract_id": "cs", "revision": 1, "tenant_id": "t",
            "profile": "film", "profile_revision": "x",
            "assets": [{"asset_id": "v", "media_type": "video", "role": "output", "canonical_sha256": None}],
            "assertions": [{"assertion_id": "continuity", "source_pointer": "/profile/film/cross_shot_continuity",
                            "target_asset_id": "v", "predicate": "no cross-shot continuity errors",
                            "expected": "no confirmed major errors", "global_sentinel": True,
                            "coverage": {"kind": "sampled", "minimum_items": 1},
                            "observation": {"kind": "cross_shot_continuity", "subject": "whole film",
                                            "attribute": "continuity", "comparator": "continuity_audit"}}]}


def _run(tmp_path, observer, budget):
    clip = tmp_path / "c.mp4"
    _three_shot_clip(clip)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    return run_verification(run_id="c", run_mode="synthetic_fixture", contract_json=_contract(),
                            assets=[AssetInput("v", 1, sha, "video")], store=store, budget=budget,
                            observer=observer).envelope


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("verdict,status", [("confirmed", "FAIL"), ("rejected", "UNCERTAIN")])
def test_budget_stop_mid_audit_keeps_paid_findings(tmp_path, verdict, status):
    env = _run(tmp_path, StopAfter(verdict, 1), CapBudget(1))
    c = env["checks"][0]
    assert c["status"] == status  # never PASS on incomplete coverage; a confirmed FAIL survives
    assert len(c["findings"]) == 1 and "Budget exhausted" in c["rationale"]
    if status == "UNCERTAIN":
        assert "budget ran out" in c["observed"]  # never reads as a clean result


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_plan_recorded_and_reductions_become_limitations(tmp_path):
    env = _run(tmp_path, LogFake("rejected"), PlannedBudget(1))
    assert env["plan"]["budget_usd"] == 0.3 and env["plan"]["reductions"]
    assert sum(s.startswith("budget plan (") for s in env["checks"][0]["limitations"]) == 1
