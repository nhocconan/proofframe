import json

import httpx
import pytest

from proofframe import cli
from proofframe.verify.autocontract import build_auto_contract
from proofframe_contracts.models import Contract, fingerprint

from .test_api_support import (AUTH, contract_json, engine, client, post_run, queued_run,  # noqa: F401
                               settings, pg_url, store, upload, video_bytes)


def test_auto_contract_is_deterministic_and_advisories_do_not_block():
    probe = {"sha256": "a" * 64, "duration_ms": 60_000, "has_audio": True}
    first = build_auto_contract("episode", probe, "demo-tenant")
    second = build_auto_contract("episode", dict(probe), "demo-tenant")
    a, b = Contract.model_validate(first), Contract.model_validate(second)
    assert a.contract_id == b.contract_id == build_auto_contract(
        "episode", probe, "demo-tenant")["contract_id"]
    assert fingerprint(a) == fingerprint(b)
    assert all(not item.blocking for item in a.assertions if item.assertion_id.startswith("qc-"))
    assert {item.observation.kind for item in a.assertions if item.blocking} == {
        "generation_artifact_scan", "cross_shot_continuity"
    }


def test_long_auto_contract_chunks_generic_audits():
    contract = Contract.model_validate(build_auto_contract(
        "episode", {"sha256": "b" * 64, "duration_ms": 181_000, "has_audio": False}, "demo-tenant"))
    audits = [item for item in contract.assertions if item.blocking]
    assert len(audits) == 6
    assert all(item.scope and item.scope.end_ms - item.scope.start_ms <= 90_000 for item in audits)


def test_video_only_api_creates_run_and_stores_auto_contract(client, video_bytes):
    asset = upload(client, video_bytes, asset_id="episode").json()
    response = client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": "video-only-1"},
                           json={"mode": "video_only", "assets": [
                               {"asset_id": "episode", "sha256": asset["sha256"]}],
                               "run_mode": "synthetic_fixture"})
    assert response.status_code == 202, response.text
    run = response.json()
    contract = client.get(f"/v1/contracts/{run['contract_sha256']}", headers=AUTH)
    assert contract.status_code == 200
    assert contract.json()["contract_id"].startswith("auto-")
    assert contract.json()["profile_revision"] == "video-only-no-brief-v1"


def test_video_only_cli_submits_without_contract(tmp_path, monkeypatch):
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"video-fixture")
    submitted = {}

    def transport(request):
        if request.url.path == "/v1/contracts":
            pytest.fail("video-only mode must not submit a client contract")
        if request.url.path == "/v1/assets":
            return httpx.Response(201, json={"asset_id": "episode", "revision": 1,
                                             "sha256": "a" * 64})
        submitted.update(json.loads(request.content))
        return httpx.Response(202, json={"run_id": "run-1"})

    monkeypatch.setattr(cli, "_c", lambda: httpx.Client(
        base_url="https://test", transport=httpx.MockTransport(transport)))
    cli.main(["verify", "--video-only", "--video", f"episode={video}"])
    assert submitted == {"mode": "video_only", "assets": [
        {"asset_id": "episode", "sha256": "a" * 64}], "run_mode": "live"}


@pytest.mark.parametrize("args", [
    ["verify", "--video", "episode=x.mp4"],
    ["verify", "--contract", "contract.json", "--video-only", "--video", "episode=x.mp4"],
    ["verify", "--video-only", "--audio", "episode=x.wav"],
])
def test_cli_rejects_missing_or_conflicting_contract_mode(args, monkeypatch):
    monkeypatch.setattr(cli, "_c", lambda: pytest.fail("invalid arguments must not contact API"))
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_long_auto_contract_chunks_decoded_qc_advisories():
    # Decoded-QC detectors cap a scope at 300 s: past that, advisories must be
    # scoped (reusing the audit chunks) instead of whole-video ERRORs.
    contract = Contract.model_validate(build_auto_contract(
        "episode", {"sha256": "c" * 64, "duration_ms": 486_000, "has_audio": True}, "demo-tenant"))
    advisories = [item for item in contract.assertions if not item.blocking]
    assert advisories, "expected decoded-QC advisories"
    assert all(item.scope and item.scope.end_ms - item.scope.start_ms <= 90_000
               for item in advisories)
    metrics = {item.observation.technical_metric for item in advisories}
    assert {"black_duration_ms", "freeze_duration_ms", "silence_duration_ms",
            "integrated_loudness_lufs", "true_peak_dbtp"} <= metrics
