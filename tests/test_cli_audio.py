"""The CLI carries audio slots through the existing HTTP contract, never a second verifier."""
import json

import httpx
import pytest

from proofframe import cli


def test_audio_only_cli_upload_preserves_logical_media_type(tmp_path, monkeypatch):
    contract = tmp_path / "contract.json"
    contract.write_text("{}")
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFFfixture")
    submitted = {}

    def transport(request):
        if request.url.path == "/v1/contracts":
            return httpx.Response(201, json={"contract_sha256": "c" * 64})
        if request.url.path == "/v1/assets":
            body = request.read()
            assert b'name="media_type"\r\n\r\naudio\r\n' in body
            assert b"RIFFfixture" in body and b"audio/" in body
            return httpx.Response(201, json={"asset_id": "voice", "revision": 1, "sha256": "a" * 64})
        submitted.update(json.loads(request.content))
        return httpx.Response(202, json={"run_id": "r"})

    monkeypatch.setattr(cli, "_c", lambda: httpx.Client(base_url="https://test", transport=httpx.MockTransport(transport)))
    cli.main(["verify", "--contract", str(contract), "--audio", f"voice={audio}"])
    assert submitted["assets"] == [{"asset_id": "voice", "sha256": "a" * 64}]
    assert submitted["contract_sha256"] == "c" * 64


def test_missing_media_is_rejected_before_http(tmp_path, monkeypatch):
    def unexpected_http():
        pytest.fail("missing input must not contact API")
    monkeypatch.setattr(cli, "_c", unexpected_http)
    with pytest.raises(SystemExit) as exc:
        cli.main(["verify", "--contract", str(tmp_path / "missing.json")])
    assert exc.value.code == 2
