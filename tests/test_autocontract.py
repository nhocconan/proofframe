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


def test_no_audio_clip_gets_no_audio_qc_assertions():
    contract = Contract.model_validate(build_auto_contract(
        "v", {"sha256": "d" * 64, "duration_ms": 5_000, "has_audio": False}, "demo-tenant"))
    metrics = {item.observation.technical_metric for item in contract.assertions if item.observation.technical_metric}
    assert metrics == {"black_duration_ms", "freeze_duration_ms"}


def test_auto_contract_id_changes_with_the_generated_checks():
    """A clip scanned under an older template must not collide (409) with its old contract id."""
    from proofframe.verify.autocontract import build_auto_contract
    base = {"sha256": "b" * 64, "duration_ms": 4000}
    a = build_auto_contract("v", {**base, "has_audio": False}, "t")["contract_id"]
    b = build_auto_contract("v", {**base, "has_audio": True}, "t")["contract_id"]
    assert a != b and a.startswith("auto-bbbbbbbbbbbb-t")
    assert a == build_auto_contract("v", {**base, "has_audio": False}, "t")["contract_id"]


def test_auto_contract_without_brief_is_byte_identical_and_with_brief_carries_context():
    probe = {"sha256": "a" * 64, "duration_ms": 60_000, "has_audio": True}
    no_brief = build_auto_contract("episode", probe, "demo-tenant")
    none_brief = build_auto_contract("episode", probe, "demo-tenant", brief_text=None)
    blank_brief = build_auto_contract("episode", probe, "demo-tenant", brief_text="   \n  ")
    raw_no_brief = json.dumps(no_brief, sort_keys=True, separators=(",", ":"))
    assert raw_no_brief == json.dumps(none_brief, sort_keys=True, separators=(",", ":"))
    assert raw_no_brief == json.dumps(blank_brief, sort_keys=True, separators=(",", ":"))
    assert no_brief["contract_id"] == "auto-aaaaaaaaaaaa-t626ba870" or no_brief["profile_revision"] == "video-only-no-brief-v1"
    assert fingerprint(Contract.model_validate(no_brief)) == fingerprint(Contract.model_validate(blank_brief))

    brief = "A Vietnamese sci-fi short teaser: a young woman discovers a mysterious radio signal."
    with_brief = build_auto_contract("episode", probe, "demo-tenant", brief_text=brief)
    validated = Contract.model_validate(with_brief)
    assert with_brief["profile_revision"] == "video-only-brief-v1"
    assert with_brief["contract_id"] != no_brief["contract_id"]
    assert fingerprint(validated) != fingerprint(Contract.model_validate(no_brief))
    scan_subjects = [a.observation.subject for a in validated.assertions if a.blocking]
    assert len(scan_subjects) == 2 and all(brief in s for s in scan_subjects)

    for invalid in (123, True, ["brief"], {"text": "brief"}, "x" * 20_001):
        with pytest.raises(ValueError):
            build_auto_contract("episode", probe, "demo-tenant", brief_text=invalid)  # type: ignore[arg-type]


def test_video_only_api_accepts_brief_text_and_rejects_invalid_brief(client, video_bytes):
    asset = upload(client, video_bytes, asset_id="teaser").json()
    base_body = {"mode": "video_only", "assets": [{"asset_id": "teaser", "sha256": asset["sha256"]}],
                 "run_mode": "synthetic_fixture"}

    # First scan without a brief, then scan the exact same asset with a brief (must not 409).
    r0 = client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": "brief-none"}, json=base_body)
    assert r0.status_code == 202, r0.text

    brief = "A Vietnamese sci-fi short teaser: a young woman discovers a mysterious radio signal."
    r1 = client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": "brief-ok"},
                     json={**base_body, "brief_text": brief})
    assert r1.status_code == 202, r1.text
    run = r1.json()
    assert run["contract_sha256"] != r0.json()["contract_sha256"]
    stored = client.get(f"/v1/contracts/{run['contract_sha256']}", headers=AUTH)
    assert stored.status_code == 200
    body = stored.json()
    assert body["profile_revision"] == "video-only-brief-v1"
    assert brief in json.dumps(body)

    for idx, bad in enumerate((42, True, ["not-a-string"], {"x": 1}, "x" * 20_001)):
        resp = client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": f"brief-bad-{idx}"},
                           json={**base_body, "brief_text": bad})
        assert resp.status_code == 422


def test_brief_text_reaches_anomaly_and_continuity_prompts(tmp_path):
    from jsonschema import Draft202012Validator
    from proofframe.interfaces import AssetInput
    from proofframe.providers.meta import CallResult
    from proofframe.verify.pipeline import run_verification
    from tests.test_continuity import _three_shot_clip
    from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore

    if not HAS_FFMPEG:
        pytest.skip("needs ffmpeg")

    class RecordingObserver:
        model = "fake-observer"

        def __init__(self):
            self.traces, self.by_purpose = [], {}

        def _ok(self, purpose, question, schema, parsed):
            Draft202012Validator(schema).validate(parsed)
            self.by_purpose.setdefault(purpose.split(":")[0], []).append(question)
            t = {"trace_id": f"tr-{len(self.traces)}", "purpose": purpose, "outcome": "ok", "cost_usd": 0.0}
            self.traces.append(t)
            return CallResult(ok=True, parsed=parsed, trace=t, outcome="ok")

        def observe_video(self, *, question, schema, purpose, **_):
            return self._ok(purpose, question, schema, {"defects": [
                {"start_s": 1, "end_s": 2, "category": "object", "severity": "minor", "description": "flicker"}
            ]})

        def observe_images(self, *, images, question, schema, purpose, **_):
            labels = [lab for lab, _ in images]
            kind = purpose.split(":")[0]
            if kind == "grid":
                parsed = {"frames": [{"label": lab, "defects": []} for lab in labels]}
            elif kind == "adjudicate":
                parsed = {"verdict": "rejected", "severity": "minor", "innocent_explanation_considered": "ok",
                          "evidence_labels": [labels[0]], "explanation": "clear", "limb_continues_off_frame": "unclear"}
            elif kind == "continuity_log":
                parsed = {"log": [{"entity": "radio", "kind": "prop", "appearances": [
                    {"frame": labels[0], "description": "on desk"}, {"frame": labels[-1], "description": "on desk"}]}],
                          "errors": [{"entity": "radio", "kind": "prop_design", "frame_a": labels[0],
                                      "frame_b": labels[-1], "description": "dial", "severity": "minor"}]}
            elif kind == "continuity_pair":
                parsed = ({"observations": "ok", "discrepancies": []} if "observations" in schema["properties"]
                          else {"same_scene": "yes", "people_a": "", "people_b": "", "discrepancies": []})
            else:
                parsed = {"shot_a_description": "same", "shot_b_description": "same", "same_entity": "yes",
                          "verdict": "rejected", "severity": "minor", "innocent_explanation_considered": "angle",
                          "explanation": "same prop", "framing_comparable": "yes", "opposite_face_possible": "no"}
            return self._ok(purpose, question, schema, parsed)

    clip = tmp_path / "three.mp4"
    _three_shot_clip(clip)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    probe = {"sha256": sha, "duration_ms": 9_000, "has_audio": False}
    brief = "A Vietnamese sci-fi short teaser: a young woman discovers a mysterious radio signal."

    obs_brief = RecordingObserver()
    env_brief = run_verification(
        run_id="r-brief", run_mode="synthetic_fixture",
        contract_json=build_auto_contract("clip", probe, "t", brief_text=brief),
        assets=[AssetInput("clip", 1, sha, "video")], store=store, budget=CapBudget(1.0), observer=obs_brief,
    ).envelope
    for stage in ("hunt", "grid", "adjudicate", "continuity_log", "continuity_pair", "continuity_adjudicate"):
        assert obs_brief.by_purpose.get(stage), f"expected calls for {stage}"
        assert all(brief in q for q in obs_brief.by_purpose[stage]), f"brief missing in {stage}"
    assert "VIDEO_ONLY_WITH_BRIEF" in env_brief["labels"]

    obs_plain = RecordingObserver()
    run_verification(
        run_id="r-plain", run_mode="synthetic_fixture",
        contract_json=build_auto_contract("clip", probe, "t"),
        assets=[AssetInput("clip", 1, sha, "video")], store=store, budget=CapBudget(1.0), observer=obs_plain,
    )
    assert all("<context>" not in q for qs in obs_plain.by_purpose.values() for q in qs)
