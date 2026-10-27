"""Cross-shot continuity audit: helpers + pipeline plumbing with a fake observer (not a benchmark)."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from proofframe import media
from proofframe.interfaces import AssetInput
from proofframe.verify import continuity
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore


def test_plan_keyframes_two_for_long_shots_one_for_short():
    keys = continuity.plan_keyframes([(0, 5000), (5000, 6000)])
    assert [k.label for k in keys] == ["S1a", "S1b", "S2"]
    assert keys[2].t_ms == 5500


def test_plan_keyframes_falls_back_to_one_per_shot_over_budget():
    shots = [(i * 4000, (i + 1) * 4000) for i in range(20)]  # 40 > budget
    assert len(continuity.plan_keyframes(shots)) == 20


def test_batches_overlap_and_cover():
    shots = [(i * 1000, (i + 1) * 1000) for i in range(60)]
    bs = continuity.batches(continuity.plan_keyframes(shots))
    covered = {k.shot for b in bs for k in b}
    assert covered == set(range(60)) and all(len(b) <= continuity.MAX_KEYFRAMES for b in bs)
    assert {k.shot for k in bs[0]} & {k.shot for k in bs[1]}  # overlap between consecutive batches


def test_identity_never_auto_fails():
    assert continuity.finding_status("identity", "confirmed", "critical") == "review"
    assert continuity.finding_status("prop_scale", "confirmed", "major") == "confirmed"


def _three_shot_clip(path):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=3",
                    "-f", "lavfi", "-i", "color=c=red:size=320x180:rate=24:duration=3",
                    "-f", "lavfi", "-i", "smptebars=size=320x180:rate=24:duration=3",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-c:v", "libx264", str(path)], check=True)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_detect_shots_finds_hard_cuts(tmp_path):
    clip = tmp_path / "c.mp4"
    _three_shot_clip(clip)
    shots = media.detect_shots(clip, 9000)
    assert len(shots) == 3 and abs(shots[1][0] - 3000) <= 100 and abs(shots[2][0] - 6000) <= 100


class LogFake:
    model = "fake-observer"

    def __init__(self, verdict, kind="prop_scale"):
        self.verdict, self.kind, self.traces = verdict, kind, []

    def observe_images(self, *, images, purpose, **_):
        from proofframe.providers.meta import CallResult
        labels = [l for l, _ in images]
        if purpose.startswith("continuity_log"):
            parsed = {"log": [{"entity": "red radio", "kind": "prop", "appearances": [
                          {"frame": labels[0], "description": "big"}, {"frame": labels[-1], "description": "small"}]}],
                      "errors": [{"entity": "red radio", "kind": self.kind, "frame_a": labels[-1],
                                  "frame_b": labels[0], "description": "much smaller", "severity": "major"}]}
        elif purpose.startswith("continuity_pair"):
            parsed = {"same_scene": "yes", "people_a": "", "people_b": "", "discrepancies": [
                {"entity": "red radio", "kind": self.kind, "description": "much smaller", "severity": "major"}]}
        else:
            parsed = {"shot_a_description": "big", "shot_b_description": "small", "same_entity": "yes",
                      "verdict": self.verdict, "severity": "major", "innocent_explanation_considered": "x",
                      "explanation": "y"}
        t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "ok", "cost_usd": 0.0}
        self.traces.append(t)
        return CallResult(ok=True, parsed=parsed, trace=t, outcome="ok")


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("verdict,kind,status", [("confirmed", "prop_scale", "FAIL"), ("rejected", "prop_scale", "PASS"),
                                                  ("confirmed", "identity", "UNCERTAIN")])
def test_continuity_pipeline(tmp_path, verdict, kind, status):
    clip = tmp_path / "c.mp4"
    _three_shot_clip(clip)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    contract = {"schema_version": "proofframe.contract.v0.1", "contract_id": "cs", "revision": 1, "tenant_id": "t",
                "profile": "film", "profile_revision": "x",
                "assets": [{"asset_id": "v", "media_type": "video", "role": "output", "canonical_sha256": None}],
                "assertions": [{"assertion_id": "continuity", "source_pointer": "/profile/film/cross_shot_continuity",
                                "target_asset_id": "v", "predicate": "no cross-shot continuity errors",
                                "expected": "no confirmed major errors", "global_sentinel": True,
                                "coverage": {"kind": "sampled", "minimum_items": 1},
                                "observation": {"kind": "cross_shot_continuity", "subject": "whole film",
                                                "attribute": "continuity", "comparator": "continuity_audit"}}]}
    env = run_verification(run_id="c", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                           observer=LogFake(verdict, kind)).envelope
    c = env["checks"][0]
    assert c["status"] == status and len(c["shots"]) == 3
    f = c["findings"][0]
    assert f["ref_start_ms"] < f["start_ms"]  # earlier shot is the reference, later shot is where it shows


def test_plan_pairs_adjacent_plus_registry_long_range():
    log = [{"entity": "radio", "kind": "prop", "appearances": [{"frame": "S1", "description": ""},
                                                             {"frame": "S5", "description": ""}]}]
    pairs = continuity.plan_pairs(6, log, {"S1": 0, "S5": 4}, [(i * 5000, (i + 1) * 5000) for i in range(6)])
    keys = {(a, b) for a, b, _ in pairs}
    assert {(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)} <= keys and (0, 4) in keys
    assert dict(((a, b), e) for a, b, e in pairs)[(0, 4)] == ["radio"]


def test_long_films_still_get_registry_pairs():
    n = 70
    log = [{"entity": "radio", "kind": "prop", "appearances": [{"frame": "S1", "description": ""},
                                                             {"frame": "S70", "description": ""}]}]
    pairs = continuity.plan_pairs(n, log, {"S1": 0, "S70": 69}, [(i * 5000, (i + 1) * 5000) for i in range(n)])
    assert (0, 69) in {(a, b) for a, b, _ in pairs}
