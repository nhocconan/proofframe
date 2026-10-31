"""A continuity audit that compared zero shot pairs must not PASS (regression: single-shot clips reported
"0 shot pairs compared" with status PASS, a vacuous result)."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from proofframe.interfaces import AssetInput
from proofframe.providers.meta import CallResult
from proofframe.verify.plan import RunPlan, Workload, estimate
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore
from tests.test_continuity import LogFake, _three_shot_clip

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")

CONTRACT = {"schema_version": "proofframe.contract.v0.1", "contract_id": "cs", "revision": 1, "tenant_id": "t",
            "profile": "film", "profile_revision": "x",
            "assets": [{"asset_id": "v", "media_type": "video", "role": "output", "canonical_sha256": None}],
            "assertions": [{"assertion_id": "continuity", "source_pointer": "/profile/film/cross_shot_continuity",
                            "target_asset_id": "v", "predicate": "no cross-shot continuity errors",
                            "expected": "no confirmed major errors", "global_sentinel": True,
                            "coverage": {"kind": "sampled", "minimum_items": 1},
                            "observation": {"kind": "cross_shot_continuity", "subject": "whole film",
                                            "attribute": "continuity", "comparator": "continuity_audit"}}]}


class NeverCalled:
    model = "fake-observer"
    traces: list = []

    def observe_images(self, **_):
        raise AssertionError("a single continuous shot has nothing to compare: no model call expected")


def _run(tmp_path, clip, observer):
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    return run_verification(run_id="c", run_mode="synthetic_fixture", contract_json=CONTRACT,
                            assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                            observer=observer).envelope


def test_single_shot_clip_is_not_checked_not_pass(tmp_path):
    clip = tmp_path / "one.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    env = _run(tmp_path, clip, NeverCalled())
    c = env["checks"][0]
    assert c["status"] == "NOT_CHECKED" and c["evidence_ids"] == [] and c["findings"] == []
    assert "single continuous shot has no cross-shot pairs" in c["rationale"]
    assert "0 shot pairs compared" in c["rationale"] and len(c["shots"]) == 1
    # a blocking check that did not run keeps the run in REVIEW; it is never ELIGIBLE
    assert env["decision"]["decision"] == "REVIEW" and env["decision"]["unresolved"] == ["continuity"]
    assert env["report"]["results"][0]["status"] == "NOT_CHECKED"
    assert env["cost"]["estimated_usd"] == 0


def test_multi_shot_clip_still_passes_when_pairs_were_compared(tmp_path):
    clip = tmp_path / "three.mp4"
    _three_shot_clip(clip)
    env = _run(tmp_path, clip, LogFake("rejected"))
    c = env["checks"][0]
    assert c["status"] == "PASS" and len(c["shots"]) == 3
    assert "shot pairs compared" in c["rationale"] and "0 shot pairs" not in c["rationale"]


def test_plan_does_not_budget_a_single_shot_audit():
    assert estimate(Workload(continuity_shots=[[(0, 5000)]]), RunPlan()) == 0
    assert estimate(Workload(continuity_shots=[[(0, 5000), (5000, 9000)]]), RunPlan()) > 0


def test_approved_single_shot_exclusion_is_not_applicable_and_excluded(tmp_path):
    """The video-only auto-contract approves the single-shot exclusion up front, so one continuous shot is
    NOT_APPLICABLE (excluded by policy) rather than an unresolved blocking check; without it, NOT_CHECKED."""
    from proofframe.verify.autocontract import SINGLE_SHOT_EXCLUSION
    clip = tmp_path / "one.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    contract = {**CONTRACT, "assertions": [{**CONTRACT["assertions"][0], "blocking": True,
                                            "approved_exclusion": SINGLE_SHOT_EXCLUSION}]}
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    env = run_verification(run_id="c", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                           observer=NeverCalled()).envelope
    c = env["checks"][0]
    assert c["status"] == "NOT_APPLICABLE" and c["evidence_ids"] == []
    assert "0 shot pairs compared" in c["rationale"]
    assert env["decision"]["decision"] == "ELIGIBLE" and env["decision"]["unresolved"] == []


def test_auto_contract_carries_the_exclusion_on_continuity_only():
    from proofframe.verify.autocontract import SINGLE_SHOT_EXCLUSION, build_auto_contract
    c = build_auto_contract("v", {"sha256": "a" * 64, "duration_ms": 4000}, "t")
    rows = {a["assertion_id"]: a for a in c["assertions"]}
    assert rows["continuity"]["approved_exclusion"] == SINGLE_SHOT_EXCLUSION
    assert rows["gen-artifacts"].get("approved_exclusion") is None
