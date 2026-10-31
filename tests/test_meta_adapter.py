"""Meta adapter failure semantics with a mocked transport (no network, no spend)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from proofframe.providers.meta import MetaObserver
from tests.test_core_pipeline import CapBudget


class LedgerBudget(CapBudget):
    def __init__(self, cap=1.0):
        super().__init__(cap)
        self.settled = []

    def settle(self, rid, *, cost_usd, cost_basis, usage, remote_request_id, outcome):
        self.settled.append((cost_usd, outcome))
        super().settle(rid, cost_usd=cost_usd)


def obs_with(handler, budget=None):
    b = budget or LedgerBudget()
    return MetaObserver(api_key="k", budget=b, run_id="r", base_url="https://x/v1",
                        client=httpx.Client(transport=httpx.MockTransport(handler))), b


def ok_body(text, status="completed"):
    return {"id": "resp_1", "status": status, "usage": {"input_tokens": 1000, "output_tokens": 100},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "incomplete_details": None, "error": None}


def call(o, tmp_path, schema=None):
    img = tmp_path / "f.png"
    img.write_bytes(b"\x89PNG")
    return o.observe_images(images=[("F1", img)], question="q", schema=schema or {}, schema_name="s", purpose="confirm:x")


def test_invalid_json_is_invalid_output_and_still_costed(tmp_path):
    o, b = obs_with(lambda req: httpx.Response(200, json=ok_body("not json")))
    r = call(o, tmp_path, schema={"type": "object", "additionalProperties": False,
                                 "required": ["frames"], "properties": {"frames": {"type": "array"}}})
    assert r.outcome == "invalid_output" and not r.ok and b.settled[0][0] > 0


@pytest.mark.parametrize("text", ['{"verdict":"bogus"}', '{}', '[]',
                                  '{"verdict":"confirmed","extra":1}',
                                  '{"verdict":"confirmed","score":NaN}',
                                  '{"verdict":"confirmed","score":1e999}'])
def test_schema_invalid_output_never_ok_and_still_costed(tmp_path, text):
    o, b = obs_with(lambda req: httpx.Response(200, json=ok_body(text)))
    image = tmp_path / "f.png"
    image.write_bytes(b"image")
    schema = {"type": "object", "additionalProperties": False, "required": ["verdict"],
              "properties": {"verdict": {"type": "string", "enum": ["confirmed", "rejected"]}}}
    result = o.observe_images(images=[("F1", image)], question="q", schema=schema,
                              schema_name="judge", purpose="confirm:x")
    assert not result.ok and result.outcome == "invalid_output" and result.parsed is None
    assert b.settled[0][0] > 0


def test_incomplete_response_is_not_ok(tmp_path):
    o, _ = obs_with(lambda req: httpx.Response(200, json=ok_body("{}", status="incomplete")))
    assert call(o, tmp_path).outcome == "incomplete"


def test_timeout_holds_reservation_as_unknown_cost(tmp_path):
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)
    o, b = obs_with(boom)
    r = call(o, tmp_path)
    assert r.outcome == "timeout" and b.settled == [(None, "timeout")] and b.spent > 0


def test_http_400_is_error_not_retried(tmp_path):
    calls = []
    def bad(req):
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad schema"}})
    o, _ = obs_with(bad)
    r = call(o, tmp_path)
    assert r.outcome == "http_error" and len(calls) == 1


def test_budget_exhausted_makes_no_request(tmp_path):
    calls = []
    o, _ = obs_with(lambda req: calls.append(1) or httpx.Response(200, json=ok_body("{}")), LedgerBudget(0.0))
    assert call(o, tmp_path).outcome == "budget_exhausted" and calls == []


def test_media_bytes_not_in_request_digest(tmp_path):
    seen = {}
    def cap(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_body('{"frames": []}'))
    o, _ = obs_with(cap)
    r = call(o, tmp_path, schema={"type": "object", "additionalProperties": False,
                                 "required": ["frames"], "properties": {"frames": {"type": "array"}}})
    assert r.ok and "data:image/png;base64" in json.dumps(seen["body"])
    assert "base64" not in json.dumps(r.trace)


def test_asr_strict_response_and_budget_path(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    o, b = obs_with(lambda req: httpx.Response(200, json={"sessionId": "s", "transcript": "xin chào",
                                                          "audioDurationMs": 1000, "turns": []}))
    result = o.transcribe_wav(audio=wav, duration_ms=1000, language_bias=["Vietnamese"], purpose="dialogue:x")
    assert result.ok and result.parsed["transcript"] == "xin chào" and b.settled[0][0] > 0


@pytest.mark.parametrize("body", [{"audioDurationMs": 1000},
                                   {"sessionId": "s", "transcript": 3, "audioDurationMs": 1000, "turns": []},
                                   {"sessionId": "s", "transcript": "x", "audioDurationMs": 1.5,
                                    "turns": []}])
def test_asr_invalid_transcript_or_duration_is_error(tmp_path, body):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    o, _ = obs_with(lambda req: httpx.Response(200, json=body))
    assert o.transcribe_wav(audio=wav, duration_ms=1000, language_bias=None,
                            purpose="dialogue:x").outcome == "invalid_output"
