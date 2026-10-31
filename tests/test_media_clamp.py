"""Frame extraction must stay inside the VIDEO stream (regression class: audio outlasts picture).

Seen in a live probe: a 3.04 s picture inside a 3.16 s container; a sample at 3.1 s made ffmpeg exit 0
with no frame, and the pipeline later failed with ENOENT on the missing PNG."""
import pytest

from proofframe import media


@pytest.fixture(scope="module")
def long_audio_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("clamp") / "audio_outlasts_video.mkv"
    media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=10:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=3",
                "-c:v", "ffv1", "-c:a", "pcm_s16le", "-y", str(path)])
    return path


def test_probe_reports_video_stream_duration_separately(long_audio_clip):
    p = media.probe(long_audio_clip)
    assert p.duration_ms >= 2900 and p.video_duration_ms is not None and p.video_duration_ms <= 2100


@pytest.mark.parametrize("at_ms", [2500, 2999, 10_000])
def test_extract_frame_past_video_end_returns_last_frame_not_enoent(long_audio_clip, tmp_path, at_ms):
    out = media.extract_frame(long_audio_clip, at_ms, tmp_path / "f.png", width=64)
    assert out.exists() and out.stat().st_size > 0


def test_clamp_never_exceeds_last_frame_start(long_audio_clip):
    assert media.clamp_to_video(long_audio_clip, 2999) <= 1900
    assert media.clamp_to_video(long_audio_clip, 500) == 500
    assert media.clamp_to_video(long_audio_clip, -5) == 0
