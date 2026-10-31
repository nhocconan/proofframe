"""Container vs stream extent: every sample/evidence time and every decoded-QC scope lives inside the stream.

Regressions from the 17-clip probe run (real clips, ffprobe numbers reproduced here with synthetic media):
- gen-artifacts ERROR "evidence interval must be increasing (start 1100, end 1042)": a hunt defect at 1.0 s in a
  1.04 s clip became a 200 ms candidate running past the clip, and its sample time was recorded unclamped.
- qc-black/qc-freeze ERROR on 12 of 17 clips (picture shorter than the container) and qc-silence/-loudness/
  -true-peak ERROR on 6 (audio shorter than the container): the detector scope was the container duration."""
from __future__ import annotations

import subprocess
import uuid

import pytest

from proofframe import media
from proofframe.interfaces import AssetInput
from proofframe.verify import pipeline
from proofframe.verify.autocontract import build_auto_contract
from proofframe.verify.plan import RunPlan
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore
from tests.test_short_clip_grid import CONTRACT, CleanObserver

pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _mp4(path, *, video_s, audio_s=None, tone="sine=frequency=440:sample_rate=48000", video_offset_s=0.0):
    """mp4 whose video and audio streams differ in length (audio_s None: no audio stream)."""
    args = []
    if video_offset_s:
        args += ["-itsoffset", str(video_offset_s)]
    args += ["-f", "lavfi", "-i", f"testsrc2=size=160x90:rate=24:duration={video_s}"]
    if audio_s is not None:
        args += ["-f", "lavfi", "-i", f"{tone}:duration={audio_s}", "-c:a", "aac"]
    _ff(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def _run(tmp_path, clip, contract, observer=None, assertion_ids=None, run_id="se"):
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    contract = contract(sha) if callable(contract) else contract
    env = run_verification(run_id=run_id, run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(1),
                           observer=observer, assertion_ids=assertion_ids).envelope
    return env, {c["assertion_id"]: c for c in env["checks"]}


def _qc(tmp_path, clip):
    def contract(sha):
        pr = media.probe(clip)
        return build_auto_contract("v", {"sha256": sha, "duration_ms": pr.duration_ms, "has_audio": pr.has_audio}, "t")
    store_probe = contract("0" * 64)
    ids = [a["assertion_id"] for a in store_probe["assertions"] if a["assertion_id"].startswith("qc-")]
    return _run(tmp_path, clip, contract, assertion_ids=ids)


# ------------------------------------------------------------------ bug 1: evidence times
class EndOfClipHunt(CleanObserver):
    """The hunt reports a defect that starts at the end of the clip and 'ends' after it."""

    def __init__(self, start_s, end_s):
        self.window = (start_s, end_s)

    def observe_video(self, *, purpose, **_):
        return self._r(purpose, {"defects": [{"start_s": self.window[0], "end_s": self.window[1],
                                              "category": "object", "severity": "major", "description": "x"}]})

    def observe_images(self, *, images, purpose, **_):
        if purpose.startswith("grid"):
            return super().observe_images(images=images, purpose=purpose)
        return self._r(purpose, {"verdict": "rejected", "severity": "major", "innocent_explanation_considered": "x",
                                 "evidence_labels": [images[1][0]], "explanation": "y"})


def _assert_evidence_inside_stream(env, clip):
    end = media.probe(clip).video_duration_ms
    frames = [e for e in env["evidence"] if e["kind"] == "frame"]
    assert frames
    for e in frames:
        assert 0 <= e["start_ms"] < e["end_ms"] <= end, e


@pytest.mark.parametrize("video_s,audio_s,start_s,end_s", [
    (1.04, None, 1.0, 3.0),     # the probe clip: 1.042 s, defect "at 1.0-3.0 s"
    (2.0, 3.0, 2.4, 2.9),       # audio outlasts the picture: candidate inside the container, past the video
])
def test_hunt_candidate_past_the_picture_cannot_break_evidence(tmp_path, monkeypatch, video_s, audio_s, start_s, end_s):
    clip = _mp4(tmp_path / "c.mp4", video_s=video_s, audio_s=audio_s)
    monkeypatch.setattr(pipeline, "fit_plan", lambda *a, **k: RunPlan(grid_step_ms=2000))
    env, checks = _run(tmp_path, clip, CONTRACT, observer=EndOfClipHunt(start_s, end_s))
    c = checks["gen-artifacts"]
    assert c["status"] == "PASS", c["rationale"]
    _assert_evidence_inside_stream(env, clip)


def test_frame_interval_is_increasing_and_inside_the_stream(tmp_path):
    clip = _mp4(tmp_path / "c.mp4", video_s=2.0, audio_s=3.0)
    container = media.probe(clip).duration_ms
    end = media.probe(clip).video_duration_ms
    assert container > end
    for t in (0, 1500, end - 1, end, container - 1, container, 10_000):
        a, b = media.frame_interval(clip, t, container)
        assert 0 <= a < b <= end, (t, a, b)


# ------------------------------------------------------------------ bug 2: decoded QC scope
def test_probe_reports_per_stream_extent(tmp_path):
    p = media.probe(_mp4(tmp_path / "c.mp4", video_s=2.0, audio_s=1.7))
    assert p.stream_window("video") == (0, p.video_duration_ms) and 1990 <= p.video_duration_ms <= 2050
    assert p.stream_window("audio")[1] < p.duration_ms and 1650 <= p.audio_end_ms <= 1800
    assert media.probe(_mp4(tmp_path / "v.mp4", video_s=1.0)).stream_window("audio") is None


@pytest.mark.parametrize("video_s,audio_s", [(2.0, 1.7), (2.0, 2.3)])
def test_qc_measures_when_streams_differ_from_the_container(tmp_path, video_s, audio_s):
    clip = _mp4(tmp_path / "c.mp4", video_s=video_s, audio_s=audio_s)
    p = media.probe(clip)
    assert p.duration_ms != p.video_duration_ms or p.duration_ms != p.audio_end_ms  # the mismatch is real
    env, checks = _qc(tmp_path, clip)
    assert set(checks) == {"qc-black", "qc-freeze", "qc-silence", "qc-loudness", "qc-true-peak"}
    for aid, c in checks.items():
        assert c["status"] in {"PASS", "FAIL"}, (aid, c["status"], c["rationale"])
        assert c["evidence_ids"], aid
    assert checks["qc-black"]["observed"] == "0" and checks["qc-freeze"]["observed"] == "0"
    ev = {e["evidence_id"]: e for e in env["evidence"]}
    video_cov = ev[checks["qc-black"]["evidence_ids"][0]]
    audio_cov = ev[checks["qc-silence"]["evidence_ids"][0]]
    assert video_cov["end_ms"] <= p.video_duration_ms + 1 and audio_cov["end_ms"] <= p.audio_end_ms + 1
    trimmed = checks["qc-black"] if p.duration_ms > p.video_duration_ms else checks["qc-silence"]
    assert any("trimmed to the" in line for line in trimmed["limitations"])


def test_qc_video_that_starts_late_is_measured(tmp_path):
    clip = _mp4(tmp_path / "c.mp4", video_s=2.0, audio_s=2.0, video_offset_s=0.1)
    assert media.probe(clip).video_start_ms >= 80
    _, checks = _qc(tmp_path, clip)
    assert checks["qc-black"]["status"] == "PASS" and checks["qc-freeze"]["status"] == "PASS"


def test_qc_stream_far_shorter_than_container_still_fails_closed(tmp_path):
    clip = _mp4(tmp_path / "c.mp4", video_s=3.0, audio_s=1.0)  # 2 s of the scope has no audio: not slack
    _, checks = _qc(tmp_path, clip)
    assert checks["qc-silence"]["status"] == "ERROR"
    assert checks["qc-black"]["status"] == "PASS"


def test_no_audio_clip_gets_no_audio_qc_and_the_rest_measures(tmp_path):
    clip = _mp4(tmp_path / "c.mp4", video_s=2.0)
    _, checks = _qc(tmp_path, clip)
    assert set(checks) == {"qc-black", "qc-freeze"} and all(c["status"] == "PASS" for c in checks.values())


def test_digital_silence_is_measured_not_error(tmp_path):
    clip = _mp4(tmp_path / "c.mp4", video_s=2.0, audio_s=2.0, tone="anullsrc=r=48000:cl=stereo")
    _, checks = _qc(tmp_path, clip)
    assert checks["qc-silence"]["status"] == "PASS" and int(checks["qc-silence"]["observed"]) >= 1900
    for aid in ("qc-loudness", "qc-true-peak"):  # no finite level exists: honest UNCERTAIN, never ERROR/PASS
        assert checks[aid]["status"] == "UNCERTAIN", (aid, checks[aid]["rationale"])
