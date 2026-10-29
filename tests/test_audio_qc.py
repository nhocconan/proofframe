"""Owned synthetic signals test audio metering, not a certified meter benchmark."""
import math
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from proofframe import media
from proofframe.verify.audio import UnmeasurableAudio, measure


@pytest.fixture(scope="module")
def audio_clips(tmp_path_factory):
    directory = tmp_path_factory.mktemp("audio-qc")
    signals = {
        "tone": "sine=frequency=1000:sample_rate=48000:duration=2",
        "louder": "sine=frequency=1000:sample_rate=48000:duration=2,volume=6dB",
        "silence": "anullsrc=r=48000:cl=mono:d=2",
        "subgate": "sine=frequency=1000:sample_rate=48000:duration=2,volume=-60dB",
        "intersample": "aevalsrc=0.9*sin(2*PI*12000*t+PI/4):s=48000:d=2",
        "step": "sine=frequency=1000:sample_rate=48000:duration=2,volume=6dB:enable='gte(t,1)'",
        "lfe": "aevalsrc=0|0|0|0.5*sin(2*PI*1000*t)|0|0:s=48000:d=2:c=5.1",
    }
    clips = {}
    for name, signal in signals.items():
        path = directory / f"{name}.wav"
        media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", signal,
                    "-c:a", "pcm_f64le", "-y", str(path)])
        clips[name] = path
    return clips


@pytest.mark.parametrize("metric,reference,unit", [
    ("integrated_loudness_lufs", -21.1, "LUFS"), ("true_peak_dbtp", -18.1, "dBTP"),
])
def test_known_sine_and_six_db_gain(audio_clips, metric, reference, unit):
    before_hash = media.sha256_file(audio_clips["tone"])
    normal = measure(audio_clips["tone"], start_ms=0, end_ms=2000, metric=metric)
    louder = measure(audio_clips["louder"], start_ms=0, end_ms=2000, metric=metric)
    # FFmpeg sine's peak is 1/8 full scale; a 1 kHz mono sine meters near -21.1 LUFS.
    assert normal["value"] == pytest.approx(reference, abs=0.2)
    assert louder["value"] - normal["value"] == pytest.approx(6.0, abs=0.2)
    assert normal["coverage"] == {"start_ms": 0, "end_ms": 2000}
    assert normal["units"] == unit
    assert normal["numeric_resolution"] == 0.1
    assert normal["settings"]["stream"] == "0:a:0"
    assert math.isfinite(normal["value"])
    assert media.sha256_file(audio_clips["tone"]) == before_hash


def test_true_peak_detects_intersample_peak(audio_clips):
    result = measure(audio_clips["intersample"], start_ms=0, end_ms=2000, metric="true_peak_dbtp")
    sample_peak_db = 20 * math.log10(0.9 / math.sqrt(2))
    assert sample_peak_db == pytest.approx(-3.93, abs=0.01)
    assert -2 < result["value"] < 0
    assert result["value"] > sample_peak_db + 1.5


def test_scoped_audio_resets_meter_and_retains_source_coordinates(audio_clips):
    early = measure(audio_clips["step"], start_ms=50, end_ms=950, metric="integrated_loudness_lufs")
    late = measure(audio_clips["step"], start_ms=1100, end_ms=1950, metric="integrated_loudness_lufs")
    assert late["value"] - early["value"] == pytest.approx(6.0, abs=0.2)
    assert late["coverage"] == {"start_ms": 1100, "end_ms": 1950}
    assert late["settings"]["scope"] == late["coverage"]


@pytest.mark.parametrize("clip", ["silence", "subgate", "lfe"])
def test_silence_subgate_and_lfe_cannot_establish_integrated_loudness(audio_clips, clip):
    with pytest.raises(UnmeasurableAudio, match="gating floor"):
        measure(audio_clips[clip], start_ms=0, end_ms=2000, metric="integrated_loudness_lufs")


def test_true_peak_silence_unavailable_but_subgate_and_lfe_have_peaks(audio_clips):
    with pytest.raises(UnmeasurableAudio, match="digital silence"):
        measure(audio_clips["silence"], start_ms=0, end_ms=2000, metric="true_peak_dbtp")
    assert measure(audio_clips["subgate"], start_ms=0, end_ms=2000, metric="true_peak_dbtp")["value"] < -70
    assert measure(audio_clips["lfe"], start_ms=0, end_ms=2000, metric="true_peak_dbtp")["value"] == pytest.approx(-6.0, abs=0.2)
    with pytest.raises(UnmeasurableAudio):
        measure(audio_clips["tone"], start_ms=0, end_ms=300, metric="integrated_loudness_lufs")


def test_first_audio_stream_only(audio_clips, tmp_path):
    path = tmp_path / "two-streams.mkv"
    media._run(["ffmpeg", "-v", "error", "-i", str(audio_clips["tone"]), "-i", str(audio_clips["louder"]),
                "-map", "0:a", "-map", "1:a", "-c:a", "pcm_f64le", "-y", str(path)])
    result = measure(path, start_ms=0, end_ms=2000, metric="integrated_loudness_lufs")
    assert result["value"] == pytest.approx(-21.1, abs=0.2)


def test_missing_audio_and_short_audio_track(tmp_path, audio_clips):
    video = tmp_path / "video.mkv"
    short = tmp_path / "short-audio.mkv"
    media._run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=32x32:r=10:d=3",
                "-c:v", "ffv1", "-threads", "1", "-y", str(video)])
    with pytest.raises(ValueError, match="audio stream required"):
        measure(video, start_ms=0, end_ms=1000, metric="true_peak_dbtp")
    media._run(["ffmpeg", "-v", "error", "-i", str(video), "-i", str(audio_clips["tone"]),
                "-map", "0:v", "-map", "1:a", "-c", "copy", "-y", str(short)])
    with pytest.raises(ValueError, match="cover requested scope"):
        measure(short, start_ms=0, end_ms=3000, metric="true_peak_dbtp")


@pytest.mark.parametrize("start,end", [(0, 0), (-1, 100), (True, 100), (0, 300001)])
def test_invalid_scopes(start, end):
    with pytest.raises(ValueError):
        measure(Path("unused"), start_ms=start, end_ms=end, metric="true_peak_dbtp")


def test_unsupported_metric_and_duration(audio_clips):
    with pytest.raises(ValueError, match="unsupported"):
        measure(audio_clips["tone"], start_ms=0, end_ms=1000, metric="sample_peak")
    with pytest.raises(ValueError, match="exceeds media duration"):
        measure(audio_clips["tone"], start_ms=0, end_ms=2100, metric="true_peak_dbtp")


@pytest.mark.parametrize("mutation", ["truncated", "metadata", "nan", "inf", "bad_number", "coverage", "gap"])
def test_malformed_output_never_becomes_measurement(audio_clips, monkeypatch, mutation):
    original_run = media._run

    def corrupt(argv):
        proc = original_run(argv)
        if argv[0] != "ffmpeg":
            return proc
        stdout, stderr = proc.stdout, proc.stderr
        if mutation == "truncated":
            stderr = stderr.split(b"  True peak:")[0]
        elif mutation == "metadata":
            stderr = b"    comment : [Parsed_ebur128_2 @ 0x1] Summary:\n    I: -21.1 LUFS\n"
        elif mutation in {"nan", "inf", "bad_number"}:
            stderr = stderr.replace(b"-21.1 LUFS", {"nan": b"nan LUFS", "inf": b"inf LUFS", "bad_number": b"-21.1x LUFS"}[mutation])
        elif mutation == "coverage":
            stdout = b"#tb 0: 1/48000\n0,0,0,48000,1,hash\n"
        else:
            stdout = b"#tb 0: 1/48000\n0,0,0,48000,1,hash\n0,96000,96000,48000,1,hash\n"
        return CompletedProcess(argv, 0, stdout, stderr)

    monkeypatch.setattr(media, "_run", corrupt)
    with pytest.raises(ValueError):
        measure(audio_clips["tone"], start_ms=0, end_ms=2000, metric="integrated_loudness_lufs")


@pytest.mark.parametrize("error", [RuntimeError("decoder failure"), TimeoutExpired("ffmpeg", 300)])
def test_decoder_errors_and_timeouts_are_operational_errors(audio_clips, monkeypatch, error):
    monkeypatch.setattr(media, "probe", lambda _: media.Probe(2000, None, None, True, 0, None))

    def fail(_):
        raise error

    monkeypatch.setattr(media, "_run", fail)
    with pytest.raises(type(error)):
        measure(audio_clips["tone"], start_ms=0, end_ms=2000, metric="true_peak_dbtp")
