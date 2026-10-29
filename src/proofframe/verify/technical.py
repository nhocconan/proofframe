"""CPU decoded technical measurements; approved assertions determine their meaning."""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

from proofframe import media

DETECTOR_VERSION = "pf-technical-0.1(ffmpeg)"


@dataclass(frozen=True)
class TechnicalQCSettings:
    black_pixel_threshold: float = 0.10
    black_picture_ratio: float = 0.98
    black_min_duration_ms: int = 100
    freeze_noise_db: float = -60.0
    freeze_min_duration_ms: int = 500
    silence_noise_db: float = -50.0
    silence_min_duration_ms: int = 200
    max_span_ms: int = 300_000
    max_pixels: int = 3840 * 2160

    def __post_init__(self) -> None:
        for name, lo, hi in (
            ("black_pixel_threshold", 0.0, 1.0),
            ("black_picture_ratio", 0.5, 1.0),
            ("freeze_noise_db", -100.0, -20.0),
            ("silence_noise_db", -100.0, -10.0),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"{name} must be finite and in [{lo}, {hi}]")
        for name, lo, hi in (
            ("black_min_duration_ms", 1, 60_000),
            ("freeze_min_duration_ms", 1, 60_000),
            ("silence_min_duration_ms", 1, 60_000),
            ("max_span_ms", 1, 300_000),
            ("max_pixels", 1, 3840 * 2160),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{name} must be an integer in [{lo}, {hi}]")


def _coverage(output: str, span_ms: int) -> tuple[float, float]:
    match = re.search(r"^#tb 0: (\d+/\d+)$", output, re.M)
    if not match:
        raise ValueError("missing decoded timestamp timebase")
    timebase = Fraction(match[1]) * 1000
    frames = []
    for line in output.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 6 or parts[0].strip() != "0":
            raise ValueError("malformed decoded frame record")
        pts, duration = int(parts[2]) * timebase, int(parts[3]) * timebase
        if duration <= 0:
            raise ValueError("decoded frame has no positive duration")
        frames.append((float(pts), float(pts + duration), float(duration)))
    if not frames:
        raise ValueError("no decoded frames in requested scope")
    tolerance = max(1.0, frames[0][2])
    end = frames[0][1]
    for start, stop, _ in frames[1:]:
        if start < end - 1.0 or start > end + 1.0:
            raise ValueError("decoded timestamps overlap or leave unchecked gaps")
        end = max(end, stop)
    if frames[0][0] > tolerance or frames[0][0] < -tolerance or end < span_ms - 1.0:
        raise ValueError("decoded stream does not cover requested scope")
    return max(0.0, frames[0][0]), min(float(span_ms), end)


def _events(log: str, metric: str, end_ms: float) -> list[tuple[float, float]]:
    if metric == "black_duration_ms":
        pattern = r"^\[Parsed_metadata_\d+ @ [^\]\n]+\] lavfi\.black_(start|end)=([^\s]+)"
    elif metric == "freeze_duration_ms":
        pattern = r"^\[freezedetect @ [^\]\n]+\] lavfi\.freezedetect\.freeze_(start|end):\s*([^\s]+)"
    else:
        pattern = r"^\[silencedetect @ [^\]\n]+\] silence_(start|end):\s*([^\s|]+)"
    intervals, pending = [], None
    for match in re.finditer(pattern, log, re.M):
        value = float(match[2]) * 1000
        if not math.isfinite(value) or value < -1:
            raise ValueError("invalid detector timestamp")
        if match[1] == "start":
            if pending is not None:
                raise ValueError("detector emitted overlapping starts")
            pending = max(0.0, value)
        else:
            if pending is None or value < pending:
                raise ValueError("detector emitted an unmatched end")
            intervals.append((pending, min(value, end_ms)))
            pending = None
    if pending is not None:
        intervals.append((pending, end_ms))
    return intervals


def scan(path: Path, *, start_ms: int, end_ms: int, metric: str,
         settings: TechnicalQCSettings | None = None) -> dict:
    """Measure union duration in source-relative milliseconds in [start_ms, end_ms).

    FFmpeg's input seek is accurate after decoding; its reset timestamps map back by
    adding start_ms. Checksums carry decoded PTS and duration to verify coverage.
    """
    settings = settings or TechnicalQCSettings()
    if metric not in {"black_duration_ms", "freeze_duration_ms", "silence_duration_ms"}:
        raise ValueError("unsupported technical metric")
    if type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("scope must be positive integer milliseconds")
    span = end_ms - start_ms
    if span > settings.max_span_ms:
        raise ValueError("technical scan exceeds configured span limit")
    info = media.probe(path)
    if end_ms > info.duration_ms:
        raise ValueError("technical scope exceeds media duration")
    audio = metric == "silence_duration_ms"
    if audio and not info.has_audio:
        raise ValueError("audio stream required for silence measurement")
    if not audio and (not info.width or not info.height):
        raise ValueError("video stream required for visual measurement")
    if not audio and info.width * info.height > settings.max_pixels:
        raise ValueError("video exceeds configured pixel limit")
    minimum = getattr(settings, metric.replace("duration", "min_duration"))
    if audio:
        detector = f"silencedetect=n={settings.silence_noise_db}dB:d={minimum / 1000}"
    elif metric == "black_duration_ms":
        detector = (f"blackdetect=d=0:pix_th={settings.black_pixel_threshold}:"
                    f"pic_th={settings.black_picture_ratio},metadata=mode=print")
    else:
        detector = f"freezedetect=n={settings.freeze_noise_db}dB:d={minimum / 1000}"
    trim = f"{'a' if audio else ''}trim=duration={span / 1000:.3f}"
    argv = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-v", "info", "-xerror",
            "-threads", "1", "-filter_threads", "1", "-ss", f"{start_ms / 1000:.3f}", "-i", str(path),
            "-map", "0:a:0" if audio else "0:v:0", "-af" if audio else "-vf", f"{trim},{detector}"]
    if not audio:
        argv += ["-an", "-vsync", "0", "-enc_time_base", "-1"]
    argv += ["-threads", "1", "-f", "framemd5", "-"]
    proc = media._run(argv)
    first, checked_end = _coverage(proc.stdout.decode(errors="strict"), span)
    intervals = []
    for lo, hi in _events(proc.stderr.decode(errors="replace"), metric, checked_end):
        lo, hi = max(first, lo), min(checked_end, hi)
        if hi - lo + 0.001 < minimum:
            continue
        lo_ms, hi_ms = start_ms + round(lo), start_ms + round(hi)
        if intervals and lo_ms <= intervals[-1]["end_ms"]:
            intervals[-1]["end_ms"] = max(intervals[-1]["end_ms"], hi_ms)
        else:
            intervals.append({"start_ms": lo_ms, "end_ms": hi_ms})
    limitations = [
        "Decoded technical measurement; intentional black, stillness or silence may be approved.",
        f"Events shorter than {minimum} ms are excluded; scoped boundaries reset detector history.",
        "Only the first selected media stream is checked; detector thresholds are heuristic.",
    ]
    if first > 0:
        limitations.append(f"First decoded frame begins {first:.3f} ms after requested start.")
    return {"value": sum(item["end_ms"] - item["start_ms"] for item in intervals),
            "intervals": intervals, "limitations": limitations,
            "coverage": {"start_ms": start_ms + round(first), "end_ms": start_ms + round(checked_end)},
            "settings": asdict(settings), "detector_version": DETECTOR_VERSION}
