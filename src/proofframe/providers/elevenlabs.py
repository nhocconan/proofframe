"""Bounded ElevenLabs Scribe v2 speech-to-text adapter."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .meta import CallResult

SCRIBE_MODEL = "scribe_v2"
SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
SCRIBE_USD_PER_HOUR = 0.22
# Contract language names (ObservationSpec.language_bias) -> ISO 639-3 codes Scribe accepts.
# Unknown names send no code (Scribe auto-detects); free-text bias is never forwarded.
LANGUAGE_CODES = {"vietnamese": "vie", "english": "eng"}


def scribe_language_code(language_bias) -> str | None:
    """First contract language with a known ISO 639-3 code, else None (auto-detect)."""
    for name in language_bias or ():
        code = LANGUAGE_CODES.get(str(name).strip().lower())
        if code:
            return code
    return None


@dataclass
class ElevenLabsScribe:
    api_key: str
    base_url: str = SCRIBE_URL
    timeout_s: float = 600.0
    traces: list[dict[str, Any]] = field(default_factory=list)
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("ELEVENLABS_API_KEY is empty; Scribe is disabled")
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout_s)

    @classmethod
    def from_env(cls, **kwargs) -> "ElevenLabsScribe | None":
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        return cls(api_key=key, **kwargs) if key else None

    def transcribe_wav(self, *, audio: Path, duration_ms: int,
                       language_bias: list[str] | None = None, language_code: str | None = None,
                       purpose: str) -> CallResult:
        """Transcribe one already-scoped WAV; approved text and free-text bias are never sent.

        `language_code` is the contract's declared language as an ISO 639-3 code (see
        scribe_language_code); None lets Scribe auto-detect. It was hard-coded to "vie" before
        pf-verify-0.19, which forced English dialogue through a Vietnamese decoder."""
        fields = {"model_id": SCRIBE_MODEL, "timestamps_granularity": "word", "diarize": "false",
                  "tag_audio_events": "false"}
        if language_code:
            fields["language_code"] = language_code
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:12]}", "provider": "elevenlabs",
                 "model": SCRIBE_MODEL, "endpoint": "/v1/speech-to-text", "purpose": purpose,
                 "request_digest": digest, "media": ["audio/wav"], "external_cost": True}
        started = time.monotonic()
        cost = duration_ms / 3_600_000 * SCRIBE_USD_PER_HOUR
        try:
            with open(audio, "rb") as fh:
                response = self.client.post(
                    self.base_url, headers={"xi-api-key": self.api_key}, data=fields,
                    files={"file": (audio.name, fh, "audio/wav")}, timeout=self.timeout_s)
        except httpx.TimeoutException as exc:
            return self._finish(trace, "timeout", None, None, f"timeout: {exc}", started)
        except httpx.HTTPError as exc:
            return self._finish(trace, "http_error", None, None, f"connection error: {exc}", started)
        try:
            data = response.json()
        except ValueError:
            data = None
        remote = response.headers.get("request-id") or response.headers.get("x-request-id")
        if response.status_code != 200:
            message = data.get("detail") if isinstance(data, dict) else response.text[:300]
            return self._finish(trace, "http_error", None, cost,
                                f"HTTP {response.status_code}: {message}", started, remote)
        error = _validate_response(data)
        if error:
            return self._finish(trace, "invalid_output", None, cost, error, started, remote)
        assert isinstance(data, dict)
        words = data["words"]
        parsed = {"transcript": data["text"], "audioDurationMs": duration_ms, "turns": [],
                  "words": words, "languageCode": data.get("language_code"),
                  "wordTimestampsAvailable": any(_has_timestamp(word) for word in words)}
        trace["raw_output"] = parsed
        usage = {"audioDurationMs": duration_ms}
        return self._finish(trace, "ok", parsed, cost, None, started, remote, usage)

    def _finish(self, trace: dict, outcome: str, parsed: dict | None, cost: float | None,
                error: str | None, started: float, remote: str | None = None,
                usage: dict | None = None) -> CallResult:
        trace.update(outcome=outcome, latency_s=round(time.monotonic() - started, 2),
                     usage=usage, cost_usd=cost, external_cost_usd=cost,
                     cost_basis="audio_duration*$0.22/hour" if cost is not None else "unknown",
                     remote_request_id=remote, error=error)
        self.traces.append(trace)
        return CallResult(outcome == "ok", parsed, trace, outcome)


def _has_timestamp(word: dict) -> bool:
    return isinstance(word.get("start"), (int, float)) and isinstance(word.get("end"), (int, float))


def _validate_response(data: Any) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        return "Scribe response must contain string text and a words array"
    probability = data.get("language_probability")
    if (not isinstance(data.get("language_code"), str) or not data["language_code"]
            or isinstance(probability, bool) or not isinstance(probability, (int, float))
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        return "Scribe response must contain a language code and finite probability from 0 through 1"
    words = data.get("words")
    if not isinstance(words, list):
        return "Scribe response must contain string text and a words array"
    for index, word in enumerate(words):
        if not isinstance(word, dict) or not isinstance(word.get("text"), str):
            return f"Scribe word {index} must contain string text"
        if word.get("type") not in {"word", "spacing", "audio_event"}:
            return f"Scribe word {index} has unsupported type"
        for field_name in ("start", "end"):
            value = word.get(field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                return f"Scribe word {index} has invalid {field_name} timestamp"
        if _has_timestamp(word) and word["end"] < word["start"]:
            return f"Scribe word {index} ends before it starts"
    return None
