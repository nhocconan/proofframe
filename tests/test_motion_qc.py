"""Deterministic motion/camera measurements on synthetic ffmpeg media (measurement, not perception)."""
from __future__ import annotations

import pytest

from proofframe import media
from proofframe.interfaces import AssetInput
from proofframe.verify import motion
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import CapBudget, DirStore, HAS_FFMPEG
from tests.test_decoded_qc_pipeline import contract

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")

SRC = {
    # a textured scene so global motion is observable
    "still": "testsrc2=s=160x284:r=10:d=3,trim=end_frame=1,loop=loop=-1:size=1,fps=10,trim=duration=3",
    "pan": "testsrc2=s=320x284:r=10:d=3,crop=160:284:x='t*30':y=0",
    "push": "testsrc2=s=160x284:r=10:d=3,scale=w='160*(1+t*0.4)':h='284*(1+t*0.4)':eval=frame,crop=160:284",
    "flash": "color=c=gray:s=160x284:r=10:d=3,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,1.5,1.55)'",
    "moving": "testsrc2=s=160x284:r=10:d=3",
}


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("motion")
    out = {}
    for name, src in SRC.items():
        p = d / f"{name}.mkv"
        media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-t", "3", "-c:v", "ffv1", "-y", str(p)])
        out[name] = p
    return out


def m(path, metric):
    return motion.measure(path, start_ms=0, end_ms=3000, metric=metric)["value"]


def test_still_as_video_has_near_zero_motion(clips):
    assert m(clips["still"], "motion_mean_abs_diff") < 1
    assert m(clips["still"], "motion_max_step") < 1
    assert m(clips["still"], "global_motion_px") == 0


def test_pan_and_push_are_measured_as_camera_motion(clips):
    assert m(clips["pan"], "global_motion_px") > 20
    assert m(clips["push"], "global_motion_px") > 20


def test_peak_frame_sampling_lands_on_one_frame_flash(clips):
    peaks = motion.peak_times(clips["flash"], 0, 3000, k=2)
    assert peaks and any(abs(t - 1500) <= 300 for t in peaks[:2])


def test_motion_beyond_video_stream_is_not_measured(tmp_path):
    p = tmp_path / "audio_longer.mkv"
    media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=10:d=2", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=16000:duration=3", "-c:v", "ffv1", "-c:a", "pcm_s16le", "-y", str(p)])
    with pytest.raises(ValueError):
        motion.measure(p, start_ms=0, end_ms=3000, metric="motion_mean_abs_diff")


def _run(tmp_path, clip, metric, relation, expected, tolerance=0, scope=None):
    c = contract(metric, scope)
    c["assertions"][0]["expected"] = str(expected)
    c["assertions"][0]["observation"].update(technical_relation=relation, tolerance=tolerance)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/x-matroska")
    return run_verification(run_id="m", run_mode="synthetic_fixture", contract_json=c,
                            assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(0)).envelope


def test_pipeline_still_fails_at_least_3_and_costs_nothing(tmp_path, clips):
    env = _run(tmp_path, clips["still"], "motion_mean_abs_diff", "at_least", 3)
    assert env["checks"][0]["status"] == "FAIL" and env["decision"]["decision"] == "BLOCK"
    assert env["cost"]["estimated_usd"] == 0 and env["traces"] == []
    assert env["report"]["evidence"][0]["inspection"] == "sampled"


def test_pipeline_pan_fails_camera_hold(tmp_path, clips):
    env = _run(tmp_path, clips["pan"], "global_motion_px", "at_most", 10)
    assert env["checks"][0]["status"] == "FAIL"


def test_pipeline_held_camera_passes(tmp_path, clips):
    env = _run(tmp_path, clips["moving"], "global_motion_px", "at_most", 10)
    assert env["checks"][0]["status"] == "PASS"


def test_pipeline_unmeasurable_motion_is_not_checked_never_pass(tmp_path):
    p = tmp_path / "x.mkv"
    media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=10:d=2", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=16000:duration=3", "-c:v", "ffv1", "-c:a", "pcm_s16le", "-y", str(p)])
    env = _run(tmp_path, p, "motion_mean_abs_diff", "at_least", 3, scope={"start_ms": 0, "end_ms": 3000})
    assert env["checks"][0]["status"] == "NOT_CHECKED"
    # default scope follows the VIDEO stream, so the same file is measurable without an explicit scope
    env = _run(tmp_path, p, "motion_mean_abs_diff", "at_least", 3)
    assert env["checks"][0]["status"] == "PASS"


def test_plan_counts_peak_frames_and_can_drop_them():
    from proofframe.verify.plan import RunPlan, Workload, estimate, fit
    w = Workload(scan_spans_ms=[30_000])
    with_peaks = estimate(w, RunPlan())
    assert with_peaks >= estimate(w, RunPlan(peak_frames=0))
    p = fit(w, 0.0001)
    assert p.peak_frames == 0 and any("peak-frame" in r for r in p.reductions)
