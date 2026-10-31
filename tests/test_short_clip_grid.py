"""Clips shorter than the stage-2 frame grid must still be sampled (>= first/middle/last), never ERROR.

Regression: a 1.04 s clip with a 3 s+ grid step produced an empty grid, so a clean scan had no frames to
cite and CheckResult rejected the PASS ("PASS and FAIL require inspectable evidence references")."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from proofframe import media
from proofframe.interfaces import AssetInput
from proofframe.verify import pipeline
from proofframe.verify.plan import RunPlan
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")

CONTRACT = {"schema_version": "proofframe.contract.v0.1", "contract_id": "scan", "revision": 1,
            "tenant_id": "t", "profile": "film", "profile_revision": "x",
            "assets": [{"asset_id": "v", "media_type": "video", "role": "output", "canonical_sha256": None}],
            "assertions": [{"assertion_id": "gen-artifacts", "source_pointer": "/profile/film/no_generation_artifacts",
                            "target_asset_id": "v", "predicate": "no visible generation defects",
                            "expected": "no confirmed major defects", "global_sentinel": True,
                            "coverage": {"kind": "sampled", "minimum_items": 1},
                            "observation": {"kind": "generation_artifact_scan", "subject": "whole video",
                                            "attribute": "generation defects", "comparator": "anomaly_scan"}}]}


class CleanObserver:
    model = "fake-observer"

    def _r(self, purpose, parsed):
        from proofframe.providers.meta import CallResult
        t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "ok", "cost_usd": 0.0}
        return CallResult(ok=True, parsed=parsed, trace=t, outcome="ok")

    def observe_video(self, *, purpose, **_):
        return self._r(purpose, {"defects": []})

    def observe_images(self, *, images, purpose, **_):
        return self._r(purpose, {"frames": [{"label": l, "defects": []} for l, _ in images]})


def _clip(tmp_path, seconds=1.04):
    clip = tmp_path / "short.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=640x360:rate=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True)
    return clip


def _run(tmp_path, clip, monkeypatch, step_ms):
    monkeypatch.setattr(pipeline, "fit_plan", lambda *a, **k: RunPlan(grid_step_ms=step_ms))
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    return run_verification(run_id="s", run_mode="synthetic_fixture", contract_json=CONTRACT,
                            assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                            observer=CleanObserver()).envelope


@pytest.mark.parametrize("step_ms", [2000, 3000, 4000])
def test_short_clip_passes_with_grid_frames_inside_stream(tmp_path, monkeypatch, step_ms):
    clip = _clip(tmp_path)
    env = _run(tmp_path, clip, monkeypatch, step_ms)
    c = env["checks"][0]
    assert c["status"] == "PASS", c.get("rationale")
    ev = {e["evidence_id"]: e for e in env["evidence"]}
    frames = [ev[i] for i in c["evidence_ids"]]
    limit = media.clamp_to_video(clip, 10**9) + 1
    assert len(frames) >= 3 and all(0 <= f["start_ms"] < limit for f in frames), [f["start_ms"] for f in frames]


def test_scan_grid_has_first_middle_last_inside_stream(tmp_path):
    clip = _clip(tmp_path)
    for step in (2000, 3000, 4000):
        g = pipeline._scan_grid(clip, 0, 1040, step)
        assert len(g) >= 3 and g[0] == 0 and all(0 <= t <= media.clamp_to_video(clip, 10**9) for t in g)


def test_zero_extractable_frames_is_never_pass(tmp_path, monkeypatch):
    clip = _clip(tmp_path)

    def no_frames(src, at_ms, out, width=960):
        raise RuntimeError("no video frame decodable")

    monkeypatch.setattr(pipeline.media, "extract_frame", no_frames)
    try:
        env = _run(tmp_path, clip, monkeypatch, 3000)
    except RuntimeError:
        return  # the stage aborts: nothing was inspected, nothing is reported as PASS
    assert env["checks"][0]["status"] != "PASS"
