"""Deterministic motion and camera measurements from decoded frames. Zero model cost, pure Python.

These are measurements, not perception: they say how much the picture changed, not whether the change
was wanted. The approved assertion (e.g. `at_most 25`, `at_least 3`) gives them meaning.

Metrics (all over the approved scope, sampled at SAMPLE_FPS on 96 px grey frames):
  motion_mean_abs_diff  mean |last - first| grey level (0-255). ~1 = a still sold as video.
  motion_max_step       largest mean |frame[i+1] - frame[i]| between consecutive samples (0-255).
  global_motion_px      camera move first->last: best scale+translation fit of the whole frame, reported as the
                        largest corner displacement in pixels of a 240 px-wide frame. Resolution ~4 px.
                        A zoom/dolly counts; subject motion mostly does not (it is a minority of the frame).
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from proofframe import media

DETECTOR_VERSION = "pf-motion-0.1(ffmpeg,pure-python)"
METRICS = ("motion_mean_abs_diff", "motion_max_step", "global_motion_px")
SAMPLE_FPS = 4.0          # >= 4 fps so sub-second events are not skipped by a 1 fps grid
DIFF_WIDTH = 96
CAM_WIDTH = 64
REF_WIDTH = 240           # global_motion_px is reported in this frame width
MAX_SPAN_MS = 120_000
MAX_FRAMES = 480
_SCALES = (0.8, 0.87, 0.93, 1.0, 1.07, 1.15, 1.25)
_SHIFT = 8


@dataclass(frozen=True)
class Frames:
    width: int
    height: int
    data: list[bytes]      # one grey frame each
    times_ms: list[int]    # absolute source time of each frame


def _grey_frames(path: Path, lo: int, hi: int, *, fps: float, width: int) -> Frames:
    span = hi - lo
    info = media.probe(path)
    if not info.width or not info.height:
        raise ValueError("video stream required for motion measurement")
    vlimit = info.video_duration_ms or info.duration_ms
    if hi > vlimit + 1:
        # never ask for time the picture does not have; the check becomes UNCERTAIN upstream
        raise ValueError("motion scope extends beyond the video stream duration")
    height = int(round(width * info.height / info.width / 2)) * 2
    argv = ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{lo / 1000:.3f}", "-i", str(path),
            "-t", f"{span / 1000:.3f}", "-map", "0:v:0", "-an",
            "-vf", f"fps={fps},scale={width}:{height}:flags=area,format=gray",
            "-f", "rawvideo", "-"]
    proc = subprocess.run(argv, capture_output=True, timeout=media.TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[-400:]}")
    size = width * height
    n = len(proc.stdout) // size
    if n < 2:
        raise ValueError("fewer than two decoded frames in motion scope")
    if n > MAX_FRAMES:
        raise ValueError("motion scope yields too many frames")
    data = [proc.stdout[i * size:(i + 1) * size] for i in range(n)]
    return Frames(width, height, data, [int(lo + i * 1000 / fps) for i in range(n)])


def _mad(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _warp_sad(a: bytes, b: bytes, w: int, h: int, s: float, dx: int, dy: int) -> float:
    """Mean abs error of `a` against `b` sampled through x' = s*(x-cx)+cx+dx (nearest, every 2nd pixel)."""
    cx, cy = w / 2, h / 2
    total = count = 0
    for y in range(4, h - 4, 2):
        sy = int(round(s * (y - cy) + cy + dy))
        if not 0 <= sy < h:
            continue
        row_a, row_b = y * w, sy * w
        for x in range(4, w - 4, 2):
            sx = int(round(s * (x - cx) + cx + dx))
            if 0 <= sx < w:
                total += abs(a[row_a + x] - b[row_b + sx])
                count += 1
    return total / count if count > (w * h) // 16 else math.inf


def _camera_move_px(first: bytes, last: bytes, w: int, h: int) -> float:
    best, best_cost = (1.0, 0, 0), math.inf
    for s in _SCALES:
        for dy in range(-_SHIFT, _SHIFT + 1):
            for dx in range(-_SHIFT, _SHIFT + 1):
                cost = _warp_sad(first, last, w, h, s, dx, dy)
                # prefer the identity on ties so noise does not read as motion
                if cost < best_cost - 1e-9 or (abs(cost - best_cost) <= 1e-9 and (s, dx, dy) == (1.0, 0, 0)):
                    best, best_cost = (s, dx, dy), cost
    s, dx, dy = best
    cx, cy = w / 2, h / 2
    shift = 0.0
    for x, y in ((0, 0), (w, 0), (0, h), (w, h)):
        shift = max(shift, math.hypot(s * (x - cx) + cx + dx - x, s * (y - cy) + cy + dy - y))
    return shift * REF_WIDTH / w


def peak_times(path: Path, lo: int, hi: int, k: int = 4) -> list[int]:
    """Times (ms) of the k largest frame-to-frame changes, strongest first, sampled at the native frame rate
    (capped at 24 fps / MAX_FRAMES). Free; feeds sampling."""
    if k <= 0 or hi - lo < 500:
        return []
    hi = min(hi, lo + MAX_SPAN_MS)
    native = media.probe(path).fps or SAMPLE_FPS
    # sample at least at the native rate (every source frame seen once) while staying under MAX_FRAMES
    fps = max(1.0, min(max(native, SAMPLE_FPS), 24.0, (MAX_FRAMES - 2) / ((hi - lo) / 1000)))
    fr = _grey_frames(path, lo, hi, fps=fps, width=DIFF_WIDTH)
    steps = sorted(((_mad(fr.data[i], fr.data[i + 1]), fr.times_ms[i + 1]) for i in range(len(fr.data) - 1)),
                   reverse=True)
    out: list[int] = []
    for score, t in steps:
        if score <= 0.5:
            break
        if all(abs(t - u) >= 500 for u in out):
            out.append(media.clamp_to_video(path, t))
        if len(out) == k:
            break
    return out


def measure(path: Path, *, start_ms: int, end_ms: int, metric: str) -> dict:
    if metric not in METRICS:
        raise ValueError("unsupported motion metric")
    if type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or end_ms <= start_ms:
        raise ValueError("scope must be positive integer milliseconds")
    if end_ms - start_ms > MAX_SPAN_MS:
        raise ValueError("motion scan exceeds configured span limit")
    fr = _grey_frames(path, start_ms, end_ms, fps=SAMPLE_FPS, width=CAM_WIDTH if metric == "global_motion_px" else DIFF_WIDTH)
    limits = [f"Decoded measurement on {fr.width}x{fr.height} grey frames sampled at {SAMPLE_FPS:g} fps "
              f"({len(fr.data)} frames); intended motion or camera moves may be approved.",
              "Measures change, not defects: it cannot tell a wanted move from an unwanted one."]
    if metric == "motion_mean_abs_diff":
        value, res = _mad(fr.data[0], fr.data[-1]), 0.1
        limits.append("First vs last sampled frame only; a subject that returns to its start reads as no motion.")
        units = "grey levels (0-255)"
    elif metric == "motion_max_step":
        value, res = max(_mad(a, b) for a, b in zip(fr.data, fr.data[1:])), 0.1
        limits.append(f"Steps are {1000 / SAMPLE_FPS:.0f} ms apart; a one-frame flash between samples can be missed.")
        units = "grey levels (0-255)"
    else:
        value, res = _camera_move_px(fr.data[0], fr.data[-1], fr.width, fr.height), 4.0
        limits.append("Scale+translation fit between first and last sample; rotation and parallax are not modelled; "
                      "reported in px of a 240 px-wide frame, resolution about 4 px.")
        units = "px @240w"
    value = round(float(value), 2)
    return {"value": value, "units": units, "numeric_resolution": res, "limitations": limits,
            "intervals": [], "coverage": {"start_ms": start_ms, "end_ms": end_ms},
            "settings": {"sample_fps": SAMPLE_FPS, "width": fr.width, "frames": len(fr.data)},
            "detector_version": DETECTOR_VERSION}
