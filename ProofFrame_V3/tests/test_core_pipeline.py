"""Core verifier tests. The pipeline test uses a FAKE observer (labelled synthetic_fixture) on real
ffmpeg-generated media: it tests plumbing/policy, NOT video understanding."""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from proofframe.interfaces import AssetInput, BudgetExhausted
from proofframe.media import sha256_file, windows
from proofframe.verify.compare import FrameReading, classify, decide, normalize_text
from proofframe.verify.pipeline import confirm_question, localize_question, run_verification
from proofframe_contracts.models import Contract

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "demo/contract_tos_bridge.json").read_text(encoding="utf-8"))
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def fr(label, vis, value, visible=True):
    return FrameReading(label=label, evidence_id=f"ev-{label}", t_ms=0, subject_visible=visible,
                        visibility=vis, value=value)


# ------------------------------------------------------------- blind observation
def test_expected_value_never_in_observer_prompts():
    contract = Contract.model_validate(CONTRACT)
    for a in contract.assertions:
        if a.observation is None or a.observation.kind == "technical":
            continue
        for q, schema in (localize_question(a.observation), confirm_question(a.observation, ["F1", "F2"])):
            payload = q + json.dumps(schema, ensure_ascii=False)
            if a.observation.comparator == "exact_text_nfc":
                assert a.expected not in payload
                assert normalize_text(a.expected) not in normalize_text(payload)
            else:  # closed vocabularies list every option; the expected one must not be singled out
                assert payload.count(f'"{a.expected}"') == 1  # only inside the enum list


def test_vietnamese_nfc_and_dash_normalisation():
    composed = "Thom và Celia"
    decomposed = "Thom và Celia"
    assert composed != decomposed and normalize_text(composed) == normalize_text(decomposed)
    assert normalize_text("Amsterdam — Thom") == normalize_text("Amsterdam - Thom")
    assert normalize_text("Celina") != normalize_text("Celia")


# ------------------------------------------------------------- comparison policy
def test_pass_requires_min_clear_matches():
    assert decide("category_equals", "blue", [fr("F1", "clear", "blue")], min_items=2,
                  localized_values=[]).status == "UNCERTAIN"
    assert decide("category_equals", "blue", [fr("F1", "clear", "blue"), fr("F2", "clear", "blue")],
                  min_items=2, localized_values=[]).status == "PASS"


def test_fail_needs_consistent_contradiction():
    one = decide("exact_text_nfc", "A", [fr("F1", "clear", "B")], min_items=1, localized_values=[])
    assert one.status == "UNCERTAIN"
    corroborated = decide("exact_text_nfc", "A", [fr("F1", "clear", "B")], min_items=1, localized_values=["B"])
    assert corroborated.status == "FAIL"
    inconsistent = decide("exact_text_nfc", "A", [fr("F1", "clear", "B"), fr("F2", "clear", "C")],
                          min_items=1, localized_values=[])
    assert inconsistent.status == "UNCERTAIN"


def test_partial_or_invisible_never_passes():
    for frames in ([fr("F1", "partial", "brown"), fr("F2", "partial", "brown")],
                   [fr("F1", "not_visible", "", visible=False)],
                   [fr("F1", "clear", "cannot_determine"), fr("F2", "clear", "cannot_determine")], []):
        assert decide("category_equals", "brown", frames, min_items=1, localized_values=["brown"]).status == "UNCERTAIN"


def test_mixed_frames_are_uncertain():
    v = decide("category_equals", "blue", [fr("F1", "clear", "blue"), fr("F2", "clear", "red")],
               min_items=1, localized_values=[])
    assert v.status == "UNCERTAIN"


def test_regression_classes():
    assert classify("FAIL", "PASS") == "FIXED"
    assert classify("FAIL", "FAIL") == "STILL_FAILING"
    assert classify("PASS", "FAIL") == "REGRESSION"
    assert classify("PASS", "ERROR") == "UNCERTAIN"
    assert classify(None, "PASS") == "NOT_COMPARABLE"


def test_windows_overlap_and_cover():
    w = windows(0, 300_000)
    assert w[0] == (0, 60_000) and w[-1][1] == 300_000
    assert all(b[0] < a[1] for a, b in zip(w, w[1:]))  # overlap
    assert windows(10_000, 25_000) == [(10_000, 25_000)]
    assert windows(0, 120_000) == [(0, 60_000), (57_000, 120_000)]  # 3 s tail absorbed


# ------------------------------------------------------------- pipeline plumbing (fake observer)
class DirStore:
    def __init__(self, root: Path):
        self.root = root

    def put_file(self, src: Path, *, media_type: str) -> str:
        sha = sha256_file(src)
        dst = self.root / sha
        if not dst.exists():
            shutil.copyfile(src, dst)
        return sha

    def path_for(self, sha256: str) -> Path:
        return self.root / sha256


class CapBudget:
    def __init__(self, cap):
        self.cap, self.spent, self.rows = cap, 0.0, {}

    def reserve(self, *, run_id, provider, model, amount_usd, purpose):
        if self.spent + amount_usd > self.cap:
            raise BudgetExhausted("cap")
        rid = uuid.uuid4().hex
        self.spent += amount_usd
        self.rows[rid] = amount_usd
        return rid

    def settle(self, rid, *, cost_usd, **_):
        if cost_usd is not None:
            self.spent += cost_usd - self.rows[rid]


class FakeObserver:
    """Returns scripted readings and records every outbound question."""
    model = "fake-observer"

    def __init__(self, script, fail_on=None):
        self.script, self.fail_on, self.traces, self.questions = script, fail_on or set(), [], []

    def _res(self, purpose, parsed, outcome="ok"):
        from proofframe.providers.meta import CallResult
        t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": outcome, "cost_usd": 0.0}
        self.traces.append(t)
        return CallResult(ok=outcome == "ok", parsed=parsed, trace=t, outcome=outcome)

    def observe_video(self, *, question, purpose, **_):
        self.questions.append(question)
        aid = purpose.split(":")[1]
        if aid in self.fail_on:
            return self._res(purpose, None, "http_error")
        val = self.script[aid]
        return self._res(purpose, {"segments": [{"start_s": 1, "end_s": 9, "subject_visible": True,
                                                  "visibility": "clear", "value": val, "notes": ""}]})

    def observe_images(self, *, images, question, purpose, **_):
        self.questions.append(question)
        aid = purpose.split(":")[1]
        val = self.script[aid]
        vis = "partial" if aid == "eyes-01" else "clear"
        return self._res(purpose, {"frames": [{"label": lab, "subject_visible": True, "visibility": vis,
                                                "value": val} for lab, _ in images]})


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg (run in the app container)")
def test_pipeline_end_to_end_with_fake_observer(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=60",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-c:v", "libx264", "-c:a", "aac",
                    "-shortest", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    obs = FakeObserver({"caption-01": "Amsterdam — Thom và Celina trên cầu", "wardrobe-01": "blue",
                        "title-01": "40 YEARS LATER", "eyes-01": "brown"}, fail_on={"title-01"})
    out = run_verification(run_id="t1", run_mode="synthetic_fixture", contract_json=CONTRACT,
                           assets=[AssetInput("shot-01", 1, sha, "video")], store=store,
                           budget=CapBudget(1.0), observer=obs)
    env = out.envelope
    st = {c["assertion_id"]: c["status"] for c in env["checks"]}
    assert st == {"caption-01": "FAIL", "wardrobe-01": "PASS", "title-01": "ERROR", "eyes-01": "UNCERTAIN",
                  "tech-duration": "PASS", "tech-audio": "PASS"}
    assert env["decision"]["decision"] == "BLOCK" and env["decision"]["publish_authorized"] is False
    assert "title-01" in env["decision"]["unresolved"]  # provider ERROR is unresolved, not a content FAIL
    cap = next(c for c in env["checks"] if c["assertion_id"] == "caption-01")
    assert cap["focus"]["start_ms"] >= 10_000 and cap["focus"]["end_ms"] <= 25_000
    ev = {e["evidence_id"]: e for e in env["evidence"]}
    assert all(ev[i]["kind"] == "frame" and store.path_for(ev[i]["sha256"]).exists() for i in cap["evidence_ids"])
    for q in obs.questions:
        assert "Celia trên cầu" not in q and "brown" not in q.split("closed list:")[0]
    assert env["labels"][0].startswith("SYNTHETIC FIXTURE")


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg (run in the app container)")
def test_budget_exhaustion_is_not_checked(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=60",
                    "-f", "lavfi", "-i", "sine=duration=60", "-c:v", "libx264", "-c:a", "aac", "-shortest",
                    str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    from proofframe.providers.meta import MetaObserver
    obs = MetaObserver(api_key="unused", budget=CapBudget(0.0), run_id="t2", base_url="http://127.0.0.1:9")
    out = run_verification(run_id="t2", run_mode="synthetic_fixture", contract_json=CONTRACT,
                           assets=[AssetInput("shot-01", 1, sha, "video")], store=store,
                           budget=CapBudget(0.0), observer=obs)
    st = {c["assertion_id"]: c["status"] for c in out.envelope["checks"]}
    assert st["caption-01"] == st["wardrobe-01"] == "NOT_CHECKED"
    assert out.envelope["decision"]["decision"] == "REVIEW"  # nothing failed, but mandatory checks unresolved


def test_occurs_semantics_never_fail_on_sampled_miss():
    pre = [fr("F1", "clear", "intact"), fr("F2", "clear", "intact"), fr("F3", "clear", "intact")]
    assert decide("category_equals", "broken", pre, min_items=1, localized_values=["intact"]).status == "FAIL"
    assert decide("category_equals", "broken", pre, min_items=1, localized_values=["intact"],
                  temporal="occurs").status == "UNCERTAIN"
    seen = pre + [fr("F4", "clear", "broken"), fr("F5", "clear", "broken")]
    assert decide("category_equals", "broken", seen, min_items=2, localized_values=[], temporal="occurs").status == "PASS"


def test_temporal_default_keeps_contract_fingerprint_stable():
    from proofframe_contracts.models import fingerprint
    c = Contract.model_validate(CONTRACT)
    assert "temporal" not in json.dumps(c.model_dump(mode="json"))
    assert fingerprint(c) == "c633262697111248d3f540c7920b0c1be5654b81009d58aa22b312c9eb1acc58"  # stored before the change
