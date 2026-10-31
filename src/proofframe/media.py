"""FFmpeg/FFprobe wrappers. argv lists only — never a shell string. CPU only."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

EXTRACTOR_VERSION = "pf-media-0.1(ffmpeg)"
TIMEOUT_S = 300
ASR_MAX_SCOPE_MS = 600_000  # Meta file endpoint rejects audio over 10 minutes.


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
    # Duration of the first VIDEO stream. Containers whose audio outlasts the picture report the
    # longer format duration; seeking a frame past the video stream yields no frame at all.
    video_duration_ms: int | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _video_packet_end_ms(path: Path) -> int | None:
    """End of the first video stream from packet timestamps (demux only, no decode)."""
    try:
        out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                    "packet=pts_time,duration_time", "-of", "csv=p=0", str(path)]).stdout.decode()
    except (RuntimeError, subprocess.SubprocessError):
        return None
    end = None
    for line in out.splitlines():
        parts = line.split(",")
        try:
            t = float(parts[0]) + (float(parts[1]) if len(parts) > 1 and parts[1] not in ("", "N/A") else 0.0)
        except ValueError:
            continue
        end = t if end is None else max(end, t)
    return None if end is None else int(round(end * 1000))


def probe(path: Path) -> Probe:
    out = _run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration,start_time:stream=codec_type,width,height,avg_frame_rate,duration",
                "-of", "json", str(path)]).stdout
    data = json.loads(out)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    fps = None
    if video.get("avg_frame_rate") and "/" in video["avg_frame_rate"]:
        n, d = video["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else None
    video_ms = None
    try:
        if video.get("duration") not in (None, "N/A"):
            video_ms = int(round(float(video["duration"]) * 1000))
    except (TypeError, ValueError):
        video_ms = None
    if video_ms is None and video:
        video_ms = _video_packet_end_ms(path)  # mkv & co. carry no per-stream duration
    return Probe(duration_ms=int(round(float(fmt.get("duration", 0)) * 1000)),
                 video_duration_ms=video_ms,
                 width=video.get("width"), height=video.get("height"),
                 has_audio=any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
                 start_time_s=float(fmt.get("start_time") or 0.0), fps=fps)


@lru_cache(maxsize=256)
def _video_limit_ms(src: str, mtime_ns: int, size: int) -> int | None:
    """Last decodable instant of the video stream (cached per file version), or None if unknown."""
    p = probe(Path(src))
    if not p.width:  # no video stream
        return None
    dur = p.video_duration_ms if p.video_duration_ms else p.duration_ms
    if dur <= 0:
        return None
    frame_ms = int(round(1000 / p.fps)) if p.fps and p.fps > 0 else 40
    return max(0, dur - max(frame_ms, 1))


def clamp_to_video(src: Path, at_ms: int) -> int:
    """Clamp a sample time into the VIDEO stream: [0, last frame start]."""
    try:
        st = src.stat()
        limit = _video_limit_ms(str(src), st.st_mtime_ns, st.st_size)
    except (OSError, RuntimeError, ValueError):
        limit = None
    at_ms = max(0, int(at_ms))
    return at_ms if limit is None else min(at_ms, limit)


def extract_frame(src: Path, at_ms: int, out: Path, width: int = 960) -> Path:
    """Decode the frame displayed at `at_ms`, clamped to the video stream's own duration. Input seeking
    (-ss before -i) is frame-accurate when decoding and avoids decoding from t=0 (290 s into a 5-min
    file: 0.12 s vs 6.5 s, identical PNG). A seek past the end of the picture exits 0 with no file
    (container duration is longer when audio outlasts video), hence the clamp and the existence check."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    at_ms = clamp_to_video(src, at_ms)
    _run(["ffmpeg", "-v", "error", "-ss", f"{at_ms / 1000:.3f}", "-i", str(src), "-frames:v", "1",
          "-vf", f"scale={width}:-2", "-y", str(out)])
    if not out.exists():  # last resort: the final decodable frame
        _run(["ffmpeg", "-v", "error", "-sseof", "-0.2", "-i", str(src), "-update", "1", "-frames:v", "1",
              "-vf", f"scale={width}:-2", "-y", str(out)])
    if not out.exists():
        raise RuntimeError(f"no video frame decodable at {at_ms} ms from {src.name}")
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


def extract_audio_wav(src: Path, start_ms: int, end_ms: int, out: Path) -> Path:
    """Extract first audio stream from [start,end) as mono 16 kHz PCM WAV for ASR."""
    if end_ms <= start_ms:
        raise ValueError("empty audio scope")
    if end_ms - start_ms > ASR_MAX_SCOPE_MS:
        raise ValueError(f"dialogue scope exceeds ASR limit of {ASR_MAX_SCOPE_MS} ms; split it explicitly")
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-v", "error", "-ss", f"{start_ms / 1000:.3f}", "-i", str(src),
          "-t", f"{(end_ms - start_ms) / 1000:.3f}", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
          "-c:a", "pcm_s16le", "-y", str(out)])
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
