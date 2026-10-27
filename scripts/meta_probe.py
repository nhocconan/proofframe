"""Gate 0 live capability probes against the Meta developer API.

Usage (inside the media container):
    python scripts/meta_probe.py <probe> [args]
Probes: text | video <mp4> | sam <mp4> | asr <wav>

Every paid call goes through a file ledger with a conservative pre-call
reservation; the run stops if the project cap would be exceeded.
The API key is read from META_DEV_API and never printed.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("META_BASE_URL", "https://api.meta.ai/v1")
KEY = os.environ["META_DEV_API"]
CAP = float(os.environ.get("PROOFFRAME_MAX_PROJECT_COST_USD", "0"))
LEDGER = Path(os.environ.get("PROBE_LEDGER", "validation/probe_ledger.jsonl"))
PRICE = {"muse-spark-1.3": (1.25, 4.25)}  # USD per 1M input/output tokens, pricing page 2026-10-27
H = {"Authorization": f"Bearer {KEY}"}


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    total = 0.0
    for line in LEDGER.read_text().splitlines():
        row = json.loads(line)
        total += row.get("cost_usd") if row.get("cost_usd") is not None else row["reserved_usd"]
    return total


def ledger(row: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def reserve(amount: float) -> None:
    if CAP <= 0:
        sys.exit("paid calls disabled: PROOFFRAME_MAX_PROJECT_COST_USD not set")
    if spent() + amount > CAP:
        sys.exit(f"budget exhausted: spent {spent():.4f} + reserve {amount} > cap {CAP}")


def token_cost(model: str, usage: dict | None) -> float | None:
    if not usage or model not in PRICE:
        return None
    pin, pout = PRICE[model]
    return usage.get("input_tokens", 0) / 1e6 * pin + usage.get("output_tokens", 0) / 1e6 * pout


def responses(body: dict, reserve_usd: float, probe: str) -> dict:
    reserve(reserve_usd)
    t0 = time.monotonic()
    r = httpx.post(f"{BASE}/responses", headers=H, json=body, timeout=600)
    dt = time.monotonic() - t0
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
    cost = token_cost(body["model"], data.get("usage"))
    ledger({"probe": probe, "model": body["model"], "http": r.status_code, "latency_s": round(dt, 2),
            "usage": data.get("usage"), "reserved_usd": reserve_usd, "cost_usd": cost,
            "cost_basis": "usage*list_price" if cost is not None else "unknown(reservation held)",
            "response_id": data.get("id"), "ts": time.time()})
    print(f"HTTP {r.status_code} {dt:.1f}s usage={data.get('usage')} cost={cost}")
    return data


def output_text(data: dict) -> str:
    out = []
    for item in data.get("output", []):
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text":
                out.append(part.get("text", ""))
    return "".join(out)


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["observations"],
    "properties": {"observations": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["start_s", "end_s", "description", "on_screen_text"],
        "properties": {"start_s": {"type": "number"}, "end_s": {"type": "number"},
                       "description": {"type": "string"},
                       "on_screen_text": {"type": "string"}}}}},
}


def probe_text() -> None:
    body = {"model": "muse-spark-1.3", "input": "Return the colors of a standard traffic light.",
            "max_output_tokens": 800, "reasoning": {"effort": "low"},
            "text": {"format": {"type": "json_schema", "name": "colors", "strict": True, "schema": {
                "type": "object", "additionalProperties": False, "required": ["colors"],
                "properties": {"colors": {"type": "array", "items": {"type": "string"}}}}}}}
    data = responses(body, 0.01, "text_structured")
    print("status", data.get("status"), "text", output_text(data)[:300], "error", data.get("error"))


def upload(path: str) -> str:
    t0 = time.monotonic()
    with open(path, "rb") as fh:
        r = httpx.post(f"{BASE}/files", headers=H, data={"purpose": "user_data"},
                       files={"file": (Path(path).name, fh, "video/mp4")}, timeout=600)
    print(f"upload HTTP {r.status_code} {time.monotonic()-t0:.1f}s", {k: v for k, v in r.json().items() if k != "filename"})
    r.raise_for_status()
    return r.json()["id"]


def probe_video(path: str, fps: str | None) -> None:
    fid = upload(path)
    part = {"type": "input_video", "file_id": fid}
    if fps:
        part["fps"] = float(fps)
    body = {"model": "muse-spark-1.3", "max_output_tokens": 6000, "reasoning": {"effort": "low"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": (
                    "Segment this video into its distinct shots. For each shot give start_s and end_s "
                    "(seconds from the start of this file), a neutral visual description including "
                    "visible people's clothing colors, and any on-screen text verbatim (empty if none).")},
                part]}],
            "text": {"format": {"type": "json_schema", "name": "shots", "strict": True, "schema": SCHEMA}}}
    data = responses(body, 0.25, f"video_native_fps={fps}")
    print("status", data.get("status"), "incomplete", data.get("incomplete_details"), "error", data.get("error"))
    print(output_text(data)[:4000])
    httpx.delete(f"{BASE}/files/{fid}", headers=H, timeout=60)


def probe_sam(path: str, concept: str) -> None:
    reserve(0.01)
    fid = upload(path)
    body = {"model": "sam-3.1", "stream": True, "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": concept}, {"type": "input_video", "file_id": fid}]}]}
    t0 = time.monotonic()
    lines, usage, events = [], None, set()
    with httpx.stream("POST", f"{BASE}/responses", headers={**H, "Accept": "text/event-stream"},
                      json=body, timeout=600) as r:
        status = r.status_code
        for raw in r.iter_lines():
            if not raw.startswith("data:"):
                continue
            ev = json.loads(raw[5:].strip()) if raw[5:].strip() not in ("", "[DONE]") else {}
            events.add(ev.get("type"))
            if ev.get("type") == "response.output_text.delta":
                lines.append(ev.get("delta", ""))
            if ev.get("type") == "response.output_text.done" and not lines:
                lines.extend(x for x in ev.get("text", "").splitlines() if x)
            if ev.get("type") == "response.completed":
                usage = ev.get("response", {}).get("usage")
    dt = time.monotonic() - t0
    frames = (usage or {}).get("video_frames_processed")
    cost = max(frames, 50) * 0.20 / 1000 if frames is not None else None
    ledger({"probe": "sam_video", "model": "sam-3.1", "http": status, "latency_s": round(dt, 2), "usage": usage,
            "reserved_usd": 0.01, "cost_usd": cost, "ts": time.time()})
    print(f"HTTP {status} {dt:.1f}s events={sorted(e for e in events if e)} usage={usage} lines={len(lines)}")
    for ln in lines[:3]:
        print(ln[:300])
    httpx.delete(f"{BASE}/files/{fid}", headers=H, timeout=60)


def probe_asr(path: str, lang: str) -> None:
    reserve(0.01)
    req = {"mode": "ENDPOINTING", "model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV",
           "languageBias": [lang]}
    t0 = time.monotonic()
    with open(path, "rb") as fh:
        r = httpx.post(f"{BASE}/asr/transcribe", headers=H, timeout=600,
                       files={"request": (None, json.dumps(req), "application/json"),
                              "audio": (Path(path).name, fh, "audio/wav")})
    dt = time.monotonic() - t0
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
    dur = data.get("audioDurationMs")
    cost = (dur // 1000) * 0.18 / 3600 if dur else None
    ledger({"probe": f"asr_{lang}", "model": "muse-voice-transcribe-1.0", "http": r.status_code,
            "latency_s": round(dt, 2), "usage": {"audioDurationMs": dur}, "reserved_usd": 0.01,
            "cost_usd": cost, "ts": time.time()})
    print(f"HTTP {r.status_code} {dt:.1f}s", json.dumps(data, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    name, *args = sys.argv[1:]
    {"text": lambda: probe_text(),
     "video": lambda: probe_video(args[0], args[1] if len(args) > 1 else None),
     "sam": lambda: probe_sam(args[0], args[1]),
     "asr": lambda: probe_asr(args[0], args[1] if len(args) > 1 else "Vietnamese")}[name]()
    print(f"ledger total so far: {spent():.5f} USD (cap {CAP})")
