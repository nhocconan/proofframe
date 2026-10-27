"""Artifact-scan decision rules and pipeline plumbing (fake observer on real ffmpeg media; not a benchmark)."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from proofframe.interfaces import AssetInput
from proofframe.verify import anomaly
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore


def f(verdict, severity="major"):
    return {"verdict": verdict, "severity": severity, "category": "anatomy", "start_ms": 5000, "end_ms": 7000,
            "description": "floating hand", "evidence_ids": ["ev-1"]}


def test_decide_scan_rules():
    kw = dict(candidates_total=1, adjudicated=1, frames_scanned=30, calls_failed=0)
    assert anomaly.decide_scan([f("confirmed")], **kw)[0] == "FAIL"
    assert anomaly.decide_scan([f("confirmed", "minor")], **kw)[0] == "UNCERTAIN"
    assert anomaly.decide_scan([f("unclear")], **kw)[0] == "UNCERTAIN"
    assert anomaly.decide_scan([f("rejected")], **kw)[0] == "PASS"
    assert anomaly.decide_scan([f("review", "minor")], **kw)[0] == "UNCERTAIN"
    assert anomaly.decide_scan([], **{**kw, "candidates_total": 0, "adjudicated": 0})[0] == "PASS"
    # failed scan calls never yield PASS; unadjudicated candidates never yield PASS
    assert anomaly.decide_scan([], **{**kw, "candidates_total": 0, "adjudicated": 0, "calls_failed": 1})[0] == "UNCERTAIN"
    assert anomaly.decide_scan([f("rejected")], **{**kw, "candidates_total": 9})[0] == "UNCERTAIN"


def test_merge_candidates_groups_nearby_same_category():
    C = anomaly.Candidate
    m = anomaly.merge_candidates([C(5000, 6000, "anatomy", "minor", "a", {"video"}),
                                  C(6500, 8000, "anatomy", "major", "b", {"grid"}),
                                  C(30000, 31000, "text", "minor", "c", {"grid"})])
    assert len(m) == 2 and m[0].category == "anatomy" and m[0].severity == "major"
    assert (m[0].start_ms, m[0].end_ms) == (5000, 8000) and m[0].sources == {"video", "grid"}


class ScanFake:
    model = "fake-observer"

    def __init__(self, verdict):
        self.verdict, self.traces = verdict, []

    def _r(self, purpose, parsed):
        from proofframe.providers.meta import CallResult
        t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "ok", "cost_usd": 0.0}
        self.traces.append(t)
        return CallResult(ok=True, parsed=parsed, trace=t, outcome="ok")

    def observe_video(self, *, purpose, **_):
        return self._r(purpose, {"defects": [{"start_s": 5, "end_s": 8, "category": "anatomy", "severity": "major",
                                              "description": "hand without a body"}]})

    def observe_images(self, *, images, purpose, **_):
        if purpose.startswith("grid"):
            return self._r(purpose, {"frames": [{"label": l, "defects": []} for l, _ in images]})
        return self._r(purpose, {"verdict": self.verdict, "severity": "major", "innocent_explanation_considered": "x",
                                 "evidence_labels": [images[1][0]], "explanation": "y"})


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("verdict,status", [("confirmed", "FAIL"), ("rejected", "PASS"), ("unclear", "UNCERTAIN")])
def test_scan_pipeline(tmp_path, verdict, status):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=20",
                    "-c:v", "libx264", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    contract = {"schema_version": "proofframe.contract.v0.1", "contract_id": "scan", "revision": 1,
                "tenant_id": "t", "profile": "film", "profile_revision": "x",
                "assets": [{"asset_id": "v", "media_type": "video", "role": "output", "canonical_sha256": None}],
                "assertions": [{"assertion_id": "gen-artifacts", "source_pointer": "/profile/film/no_generation_artifacts",
                                "target_asset_id": "v", "predicate": "no visible generation defects",
                                "expected": "no confirmed major defects", "global_sentinel": True,
                                "coverage": {"kind": "sampled", "minimum_items": 1},
                                "observation": {"kind": "generation_artifact_scan", "subject": "whole video",
                                                "attribute": "generation defects", "comparator": "anomaly_scan"}}]}
    env = run_verification(run_id="s", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                           observer=ScanFake(verdict)).envelope
    c = env["checks"][0]
    assert c["status"] == status
    assert c["findings"][0]["verdict"] == verdict and c["findings"][0]["start_ms"] == 5000
    if status == "FAIL":
        assert env["decision"]["decision"] == "BLOCK" and c["focus"] == {"start_ms": 5000, "end_ms": 8000}
