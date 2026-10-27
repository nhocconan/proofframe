"""FFmpeg/FFprobe wrappers. argv lists only — never a shell string. CPU only."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

EXTRACTOR_VERSION = "pf-media-0.1(ffmpeg)"
TIMEOUT_S = 300


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{argv[0]} failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[-800:]}")
    return proc


@dataclass(frozen=True)
class Probe:
    duration_ms: int
    width: int | None
    height: int | None
    has_audio: bool
    start_time_s: float
    fps: float | None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def probe(path: Path) -> Probe:
    out = _run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration,start_time:stream=codec_type,width,height,avg_frame_rate",
                "-of", "json", str(path)]).stdout
    data = json.loads(out)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    fps = None
    if video.get("avg_frame_rate") and "/" in video["avg_frame_rate"]:
        n, d = video["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else None
    return Probe(duration_ms=int(round(float(fmt.get("duration", 0)) * 1000)),
                 width=video.get("width"), height=video.get("height"),
                 has_audio=any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
                 start_time_s=float(fmt.get("start_time") or 0.0), fps=fps)


def extract_frame(src: Path, at_ms: int, out: Path, width: int = 960) -> Path:
    """Decode the frame displayed at `at_ms`. Input seeking (-ss before -i) is frame-accurate when
    decoding and avoids decoding from t=0 (290 s into a 5-min file: 0.12 s vs 6.5 s, identical PNG)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-ss", f"{at_ms / 1000:.3f}", "-i", str(src), "-frames:v", "1",
          "-vf", f"scale={width}:-2", "-y", str(out)])
    return out


def make_proxy(src: Path, start_ms: int, end_ms: int, out: Path, width: int = 640,
               keep_audio: bool = True) -> Path:
    """Re-encoded window [start,end) whose t=0 equals source start_ms (timestamps reset)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ffmpeg", "-v", "error", "-ss", f"{start_ms / 1000:.3f}", "-i", str(src),
            "-t", f"{(end_ms - start_ms) / 1000:.3f}", "-vf", f"scale={width}:-2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "26", "-pix_fmt", "yuv420p"]
    argv += ["-c:a", "aac", "-b:a", "64k"] if keep_audio else ["-an"]
    argv += ["-movflags", "+faststart", "-avoid_negative_ts", "make_zero", "-y", str(out)]
    _run(argv)
    return out


def windows(start_ms: int, end_ms: int, max_ms: int = 60_000, overlap_ms: int = 3_000) -> list[tuple[int, int]]:
    """Split [start,end) into windows ≤ max_ms with overlap so boundary events are seen whole."""
    if end_ms <= start_ms:
        raise ValueError("empty window")
    out, cur = [], start_ms
    while True:
        # absorb a short tail (<= 10 s) into the current window instead of paying for a tiny extra call
        hi = end_ms if end_ms - cur <= max_ms + 10_000 else cur + max_ms
        out.append((cur, hi))
        if hi >= end_ms:
            return out
        cur = hi - overlap_ms


def composite_caption(src: Path, out: Path, *, text_file: Path, start_ms: int, end_ms: int,
                      font: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                      drop_audio: bool = False, fontsize: int = 34) -> Path:
    """Burn a lower-third caption read from `text_file` (no filtergraph text escaping/injection)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    for p in (str(text_file), font):
        if any(c in p for c in ":,;'[]\\="):
            raise ValueError("unsafe path for filtergraph")
    vf = (f"drawtext=fontfile={font}:textfile={text_file}:fontsize={fontsize}:fontcolor=white:"
          f"box=1:boxcolor=black@0.6:boxborderw=14:x=(w-text_w)/2:y=h-text_h-40:"
          f"enable=between(t\\,{start_ms / 1000:.3f}\\,{end_ms / 1000:.3f})")
    argv = ["ffmpeg", "-v", "error", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "medium",
            "-crf", "20", "-pix_fmt", "yuv420p"]
    argv += ["-an"] if drop_audio else ["-c:a", "copy"]
    argv += ["-movflags", "+faststart", "-y", str(out)]
    _run(argv)
    return out


def detect_shots(src: Path, duration_ms: int, threshold: float = 0.3, min_shot_ms: int = 400) -> list[tuple[int, int]]:
    """Hard-cut shot boundaries from FFmpeg's scene-change score (downscaled for speed).

    Returns [(start_ms, end_ms)] covering the whole file. Dissolves/fades are not modelled:
    a gradual transition may be missed or split; callers treat shots as approximate.
    """
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-an", "-vf",
                           f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                          capture_output=True, timeout=TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"shot detection failed: {proc.stderr.decode(errors='replace')[-400:]}")
    cuts = sorted({int(round(float(m) * 1000)) for m in
                   __import__("re").findall(r"pts_time:([0-9.]+)", proc.stderr.decode(errors="replace"))})
    bounds = [0]
    for c in cuts:
        if min_shot_ms <= c - bounds[-1] and duration_ms - c >= min_shot_ms:
            bounds.append(c)
    bounds.append(duration_ms)
    return list(zip(bounds[:-1], bounds[1:]))
