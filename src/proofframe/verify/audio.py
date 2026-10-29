"""Scoped, read-only FFmpeg EBU R128 measurements with decoded coverage."""
from __future__ import annotations

import math
import re
from pathlib import Path

from proofframe import media
from proofframe.verify.technical import _coverage

DETECTOR_VERSION = "pf-audio-0.1(ffmpeg-ebur128)"
MAX_SPAN_MS = 300_000
SUMMARY_RESOLUTION = 0.1


class UnmeasurableAudio(ValueError):
    """Decoded audio exists, but the meter cannot establish a finite measurement."""


def _summary(log: str) -> tuple[float, float]:
    headers = list(re.finditer(r"^\[Parsed_ebur128_\d+ @ [^\]\n]+\] Summary:\n", log, re.M))
    if len(headers) != 1:
        raise ValueError("missing or ambiguous EBU R128 summary")
    number = r"([+-]?\d+\.\d|[+-]?inf|nan)"
    pattern = (
        r"\n  Integrated loudness:\n    I:\s*" + number + r" LUFS\n"
        r"    Threshold:\s*" + number + r" LUFS\n\n"
        r"  Loudness range:\n    LRA:\s*" + number + r" LU\n"
        r"    Threshold:\s*" + number + r" LUFS\n"
        r"    LRA low:\s*" + number + r" LUFS\n"
        r"    LRA high:\s*" + number + r" LUFS\n\n"
        r"  True peak:\n    Peak:\s*" + number + r" dBFS(?:\n|$)"
    )
    match = re.match(pattern, log[headers[0].end():])
    if not match:
        raise ValueError("malformed or truncated EBU R128 summary")
    values = tuple(float(value) for value in match.groups())
    if any(not math.isfinite(value) for value in values[:-1]):
        raise ValueError("non-finite EBU R128 loudness summary")
    if not math.isfinite(values[-1]) and values[-1] != -math.inf:
        raise ValueError("invalid EBU R128 true peak")
    return values[0], values[-1]


def measure(path: Path, *, start_ms: int, end_ms: int, metric: str) -> dict:
    """Measure the first audio stream in playback-relative [start_ms, end_ms)."""
    if metric not in {"integrated_loudness_lufs", "true_peak_dbtp"}:
        raise ValueError("unsupported audio metric")
    if type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("scope must be positive integer milliseconds")
    span = end_ms - start_ms
    if span > MAX_SPAN_MS:
        raise ValueError("audio measurement exceeds configured span limit")
    info = media.probe(path)
    if not info.has_audio:
        raise ValueError("audio stream required for audio measurement")
    if end_ms > info.duration_ms:
        raise ValueError("audio scope exceeds media duration")
    # Coverage branches before the meter: its 100 ms reframing cannot hide gaps.
    graph = (f"[0:a:0]atrim=duration={span / 1000:.3f},asplit=2[coverage][meter];"
             "[meter]ebur128=peak=true:framelog=verbose:dualmono=false[measured]")
    proc = media._run([
        "ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-v", "info", "-xerror",
        "-threads", "1", "-filter_complex_threads", "1", "-ss", f"{start_ms / 1000:.3f}",
        "-i", str(path), "-filter_complex", graph,
        "-map", "[coverage]", "-c:a", "pcm_f64le", "-threads", "1", "-f", "framemd5", "-",
        "-map", "[measured]", "-c:a", "pcm_f64le", "-threads", "1", "-f", "null", "-",
    ])
    first, checked_end = _coverage(proc.stdout.decode(errors="strict"), span)
    if first > 1.0:
        raise ValueError("decoded audio does not cover requested start")
    loudness, peak = _summary(proc.stderr.decode(errors="strict"))
    if metric == "integrated_loudness_lufs" and (span < 400 or loudness <= -69.9):
        raise UnmeasurableAudio("integrated loudness unavailable below gating floor or 400 ms window")
    if metric == "true_peak_dbtp" and not math.isfinite(peak):
        raise UnmeasurableAudio("true peak unavailable for digital silence")
    unit = "LUFS" if metric == "integrated_loudness_lufs" else "dBTP"
    return {
        "value": loudness if metric == "integrated_loudness_lufs" else peak,
        "units": unit,
        "numeric_resolution": SUMMARY_RESOLUTION,
        "coverage": {"start_ms": start_ms + round(first), "end_ms": start_ms + round(checked_end)},
        "settings": {
            "meter": "ffmpeg ebur128", "stream": "0:a:0", "peak": "true",
            "dual_mono": False, "max_span_ms": MAX_SPAN_MS, "unit": unit,
            "numeric_resolution": SUMMARY_RESOLUTION, "scope": {"start_ms": start_ms, "end_ms": end_ms},
        },
        "limitations": [
            "First audio stream only; no normalization or media modification.",
            "Scoped meter history resets at requested start; mono is not treated as dual mono.",
            "Integrated loudness uses EBU R128 gating/channel weighting and excludes LFE; true peak covers all channels.",
            "True peak uses FFmpeg oversampling, not sample peak; no standard certification is claimed.",
            f"FFmpeg summary resolution is 0.1 {unit}; comparisons must account for rounding.",
        ],
        "detector_version": DETECTOR_VERSION,
    }
