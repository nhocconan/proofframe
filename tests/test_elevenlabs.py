from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from proofframe.providers.elevenlabs import ElevenLabsScribe, SCRIBE_URL, scribe_language_code


class FakeClient:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.call = None

    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        request = httpx.Request("POST", url)
        return httpx.Response(self.status, json=self.payload, request=request,
                              headers={"request-id": "req-test"})


def _wav(tmp_path: Path) -> Path:
    path = tmp_path / "scope.wav"
    path.write_bytes(b"RIFF-test")
    return path


def test_scribe_request_shape_word_timestamps_and_external_cost(tmp_path):
    client = FakeClient({"text": "năm giờ mười bảy", "language_code": "vie",
                         "language_probability": 0.99, "words": [
        {"text": "năm", "start": 0.0, "end": 0.2, "type": "word"},
        {"text": " ", "start": None, "end": None, "type": "spacing"},
        {"text": "giờ", "start": 0.2, "end": 0.4, "type": "word"},
    ]})
    scribe = ElevenLabsScribe(api_key="test-key", client=client)
    result = scribe.transcribe_wav(audio=_wav(tmp_path), duration_ms=3_600_000,
                                   language_bias=["must-not-be-sent"], language_code="vie", purpose="test")

    assert result.ok and result.parsed["wordTimestampsAvailable"] is True
    assert result.trace["external_cost_usd"] == pytest.approx(0.22)
    assert result.trace["provider"] == "elevenlabs"
    url, kwargs = client.call
    assert url == SCRIBE_URL
    assert kwargs["headers"] == {"xi-api-key": "test-key"}
    assert kwargs["data"] == {"model_id": "scribe_v2", "language_code": "vie",
                               "timestamps_granularity": "word", "diarize": "false",
                               "tag_audio_events": "false"}
    assert kwargs["files"]["file"][2] == "audio/wav"
    assert "must-not-be-sent" not in json.dumps(kwargs["data"])
    assert not hasattr(scribe, "budget")  # external cost cannot reserve/settle the Meta ledger


def test_scribe_language_code_follows_contract_language_not_a_fixed_default(tmp_path):
    # pf-verify-0.18 sent language_code="vie" for every contract, so English dialogue was decoded as
    # Vietnamese. No declared language with a known code -> no field (Scribe auto-detects).
    assert scribe_language_code(["English"]) == "eng"
    assert scribe_language_code(("Vietnamese",)) == "vie"
    assert scribe_language_code(["Klingon", " english "]) == "eng"
    assert scribe_language_code(["Klingon"]) is None and scribe_language_code(None) is None
    client = FakeClient({"text": "hello", "language_code": "eng", "language_probability": 0.9, "words": []})
    ElevenLabsScribe(api_key="k", client=client).transcribe_wav(
        audio=_wav(tmp_path), duration_ms=1000, purpose="test")
    assert "language_code" not in client.call[1]["data"]


@pytest.mark.parametrize("payload", [
    {},
    {"text": "hello", "language_code": "vie", "language_probability": 0.9, "words": "not-an-array"},
    {"text": "hello", "language_code": "vie", "language_probability": 0.9,
     "words": [{"text": "hello", "type": "unknown", "start": 0, "end": 1}]},
    {"text": "hello", "language_code": "vie", "language_probability": 0.9,
     "words": [{"text": "hello", "type": "word", "start": 2, "end": 1}]},
])
def test_scribe_strict_response_validation(tmp_path, payload):
    result = ElevenLabsScribe(api_key="test-key", client=FakeClient(payload)).transcribe_wav(
        audio=_wav(tmp_path), duration_ms=1000, purpose="test")
    assert not result.ok and result.outcome == "invalid_output"
    assert result.trace["error"]


def test_scribe_disabled_when_key_missing(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert ElevenLabsScribe.from_env() is None
    monkeypatch.setenv("ELEVENLABS_API_KEY", "   ")
    assert ElevenLabsScribe.from_env() is None
