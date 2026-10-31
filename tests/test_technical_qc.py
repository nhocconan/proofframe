"""Synthetic FFmpeg mutations exercise decoded measurements, not perception quality."""
from dataclasses import FrozenInstanceError
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from proofframe import media
from proofframe.verify.technical import TechnicalQCSettings, scan


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    directory = tmp_path_factory.mktemp("technical-qc")
    result = {}
    sources = {
        "black": "color=black:s=64x64:r=10:d=2",
        "still": "color=red:s=64x64:r=10:d=2",
        "moving": "testsrc2=s=64x64:r=10:d=2",
        "black_tail": "testsrc2=s=64x64:r=10:d=2,drawbox=color=black:t=fill:enable='gte(t,1)'",
        "black_head": "testsrc2=s=64x64:r=10:d=2,drawbox=color=black:t=fill:enable='lt(t,1)'",
    }
    for name, source in sources.items():
        path = directory / f"{name}.mkv"
        media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source,
                    "-c:v", "ffv1", "-threads", "1", "-y", str(path)])
        result[name] = path
    for name, source in {"silent": "anullsrc=r=16000:cl=mono:d=2",
                         "tone": "sine=frequency=440:sample_rate=16000:duration=2",
                         "silent_tail": "sine=frequency=440:sample_rate=16000:duration=2,volume=0:enable='gte(t,1)'"}.items():
        path = directory / f"{name}.wav"
        media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source,
                    "-c:a", "pcm_s16le", "-y", str(path)])
        result[name] = path
    return result


@pytest.mark.parametrize("name,metric,total", [
    ("black", "black_duration_ms", 2000),
    ("moving", "black_duration_ms", 0),
    ("still", "black_duration_ms", 0),
    ("black_tail", "black_duration_ms", 1000),
    ("black_head", "black_duration_ms", 1000),
    ("still", "freeze_duration_ms", 2000),
    ("moving", "freeze_duration_ms", 0),
    ("silent", "silence_duration_ms", 2000),
    ("tone", "silence_duration_ms", 0),
])
def test_decoded_mutation_and_control(clips, name, metric, total):
    result = scan(clips[name], start_ms=0, end_ms=2000, metric=metric)
    assert result["value"] == total
    assert result["coverage"] == {"start_ms": 0, "end_ms": 2000}
    assert result["settings"]["black_picture_ratio"] == 0.98
    assert "intentional" in result["limitations"][0]
    assert "status" not in result


def test_scoped_source_timestamps_and_eof(clips):
    result = scan(clips["black_tail"], start_ms=500, end_ms=1800, metric="black_duration_ms")
    assert result["value"] == 800
    assert result["intervals"] == [{"start_ms": 1000, "end_ms": 1800}]
    assert scan(clips["black_tail"], start_ms=0, end_ms=900, metric="black_duration_ms")["value"] == 0


def test_silent_audio_is_different_from_missing_audio(clips):
    assert scan(clips["silent"], start_ms=500, end_ms=1500, metric="silence_duration_ms")["value"] == 1000
    with pytest.raises(ValueError, match="audio stream required"):
        scan(clips["still"], start_ms=0, end_ms=2000, metric="silence_duration_ms")
    tail = scan(clips["silent_tail"], start_ms=500, end_ms=2000, metric="silence_duration_ms")
    assert 950 <= tail["value"] <= 1050
    assert abs(tail["intervals"][0]["start_ms"] - 1000) <= 50


def test_non_aligned_scope_reports_actual_first_frame(clips):
    result = scan(clips["black"], start_ms=150, end_ms=1850, metric="black_duration_ms")
    assert result["coverage"] == {"start_ms": 200, "end_ms": 1850}
    assert result["intervals"] == [{"start_ms": 200, "end_ms": 1850}]


def test_nonzero_container_start_maps_to_playback_scope(clips, tmp_path):
    shifted = tmp_path / "shifted.mkv"
    media._run(["ffmpeg", "-v", "error", "-i", str(clips["black_tail"]),
                "-c", "copy", "-output_ts_offset", "5", "-y", str(shifted)])
    assert media.probe(shifted).start_time_s == 5
    result = scan(shifted, start_ms=500, end_ms=1800, metric="black_duration_ms")
    assert result["intervals"] == [{"start_ms": 1000, "end_ms": 1800}]


def test_producer_metadata_is_not_a_detector_event(clips, monkeypatch):
    monkeypatch.setattr(media, "probe", lambda _: media.Probe(2000, 64, 64, False, 0.0, 10.0))
    monkeypatch.setattr(media, "_run", lambda _: CompletedProcess(
        [], 0, b"#tb 0: 1/10\n0,0,0,20,1,hash\n",
        b"    comment : lavfi.black_start=0\n    comment : lavfi.black_end=2\n"))
    assert scan(clips["black"], start_ms=0, end_ms=2000, metric="black_duration_ms")["value"] == 0


@pytest.mark.parametrize("setting", [
    {"black_picture_ratio": 0.1}, {"black_pixel_threshold": float("nan")},
    {"freeze_noise_db": float("inf")}, {"silence_noise_db": 0},
    {"freeze_min_duration_ms": 0}, {"black_min_duration_ms": True},
    {"silence_min_duration_ms": -1}, {"max_span_ms": 300001}, {"max_pixels": 0},
])
def test_invalid_settings(setting):
    with pytest.raises(ValueError):
        TechnicalQCSettings(**setting)


def test_frozen_settings():
    with pytest.raises(FrozenInstanceError):
        TechnicalQCSettings().max_span_ms = 1


@pytest.mark.parametrize("start,end", [(0, 0), (-1, 100), (1000, 999), (True, 1000), (0, 300001)])
def test_invalid_scope(start, end):
    with pytest.raises(ValueError):
        scan(Path("unused"), start_ms=start, end_ms=end, metric="black_duration_ms")


def test_unsupported_metric_and_stream_or_duration(clips):
    with pytest.raises(ValueError, match="unsupported"):
        scan(clips["black"], start_ms=0, end_ms=1000, metric="universal_quality")
    with pytest.raises(ValueError, match="exceeds media duration"):
        scan(clips["black"], start_ms=0, end_ms=2100, metric="black_duration_ms")
    with pytest.raises(ValueError, match="video stream required"):
        scan(clips["silent"], start_ms=0, end_ms=1000, metric="black_duration_ms")


@pytest.mark.parametrize("stdout,stderr", [
    (b"", b""),
    (b"#tb 0: 1/10\n0,0,0,1,1,hash\n", b""),
    (b"#tb 0: 1/10\n0,0,0,20,1,hash\n", b"[Parsed_metadata_1 @ 0x1] lavfi.black_end=1"),
    (b"#tb 0: 1/10\n0,0,0,20,1,hash\n", b"[Parsed_metadata_1 @ 0x1] lavfi.black_start=nan"),
])
def test_empty_incomplete_or_invalid_detector_output_is_error(clips, monkeypatch, stdout, stderr):
    monkeypatch.setattr(media, "probe", lambda _: media.Probe(2000, 64, 64, False, 0.0, 10.0))
    monkeypatch.setattr(media, "_run", lambda _: CompletedProcess([], 0, stdout, stderr))
    with pytest.raises(ValueError):
        scan(clips["black"], start_ms=0, end_ms=2000, metric="black_duration_ms")


def test_process_failure_and_timeout_propagate(clips, monkeypatch):
    monkeypatch.setattr(media, "probe", lambda _: media.Probe(2000, 64, 64, False, 0.0, 10.0))
    for error in [RuntimeError("decoder failure"), TimeoutExpired("ffmpeg", 300)]:
        def fail(_):
            raise error
        monkeypatch.setattr(media, "_run", fail)
        with pytest.raises(type(error)):
            scan(clips["black"], start_ms=0, end_ms=2000, metric="black_duration_ms")


def _cov_output(spans):
    lines = ["#tb 0: 1/1000"] + [f"0,0,{p},{d},0,0" for p, d in spans]
    return "\n".join(lines)


def test_coverage_tolerates_subframe_seam_jitter():
    from proofframe.verify.technical import _coverage
    out = _cov_output([(0, 40), (40, 40), (70, 40), (110, 40)])  # 10 ms overlap at a seam
    start, end = _coverage(out, 150)
    assert end == 150


def test_coverage_still_rejects_real_gap():
    from proofframe.verify.technical import _coverage
    out = _cov_output([(0, 40), (40, 40), (160, 40)])  # 80 ms hole in coverage
    with pytest.raises(ValueError):
        _coverage(out, 200)
