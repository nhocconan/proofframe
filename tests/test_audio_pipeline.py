"""Decoded audio checks through the shared verifier; synthetic signals, no API calls."""
from __future__ import annotations

import subprocess

import pytest
from pydantic import ValidationError

from proofframe.interfaces import AssetInput
from proofframe.verify.compare import numeric_status
from proofframe.verify.pipeline import run_verification
from proofframe_contracts.models import ObservationSpec
from tests.test_core_pipeline import CapBudget, DirStore, HAS_FFMPEG


@pytest.mark.parametrize("actual,target,tolerance,relation,resolution,status", [
    (-23, "-23", 0.5, "equals", 0.1, "PASS"),
    (-22.4, "-23", 0.5, "equals", 0.1, "FAIL"),
    (-22.5, "-23", 0.5, "equals", 0.1, "UNCERTAIN"),
    (-2, "-1", 0, "at_most", 0.1, "PASS"),
    (0, "-1", 0, "at_most", 0.1, "FAIL"),
    (-1, "-1", 0, "at_most", 0.1, "UNCERTAIN"),
    (2, "1", 0.25, "at_least", 0.1, "PASS"),
    (0.5, "1", 0.25, "at_least", 0.1, "FAIL"),
    (0.75, "1", 0.25, "at_least", 0.1, "UNCERTAIN"),
    (0, "0", 0, "equals", 0, "PASS"),
    (1e30, "999999999999999999999999999999", 0, "at_most", 0, "FAIL"),
    (0.1, "0.100000000000000000000000000001", 0, "at_least", 0, "FAIL"),
])
def test_approved_numeric_limits_include_meter_resolution(actual, target, tolerance, relation, resolution, status):
    assert numeric_status(actual, target, tolerance, relation, resolution) == status


@pytest.mark.parametrize("actual,target,tolerance,resolution", [
    (float("inf"), "0", 0, 0), (1, "NaN", 0, 0), (1, "1", float("nan"), 0),
    (1, "1", -1, 0), (1, "1", 0, -0.1),
    (1, "1e1001", 0, 0),
])
def test_bad_numeric_configuration_never_passes(actual, target, tolerance, resolution):
    with pytest.raises(ValueError):
        numeric_status(actual, target, tolerance, resolution=resolution)


def test_fractional_tolerance_and_directional_contract_semantics():
    base = {"kind": "technical", "subject": "delivery", "attribute": "peak",
            "comparator": "technical", "technical_metric": "true_peak_dbtp", "tolerance": 0.5}
    spec = ObservationSpec.model_validate(base)
    assert "technical_relation" not in spec.model_dump(mode="json")
    upper = ObservationSpec.model_validate({**base, "technical_relation": "at_most"})
    assert upper.model_dump(mode="json")["technical_relation"] == "at_most"
    with pytest.raises(ValidationError):
        ObservationSpec.model_validate({**base, "tolerance": float("inf")})
    with pytest.raises(ValidationError):
        ObservationSpec.model_validate({**base, "technical_metric": "has_audio", "technical_relation": "at_most"})


def test_legacy_integral_float_tolerance_serializes_as_integer():
    base = {"kind": "technical", "subject": "delivery", "attribute": "duration",
            "comparator": "technical", "technical_metric": "duration_ms"}
    integral = ObservationSpec.model_validate({**base, "tolerance": 1.0})
    integer = ObservationSpec.model_validate({**base, "tolerance": 1})
    assert integral.model_dump_json() == integer.model_dump_json()
    assert type(integral.tolerance) is int


def _assertion(aid, metric, expected, relation="equals", tolerance=0):
    return {"assertion_id": aid, "source_pointer": "/delivery/audio", "target_asset_id": "v",
            "predicate": "approved audio limit", "expected": expected,
            "observation": {"kind": "technical", "subject": "audio", "attribute": metric,
                            "comparator": "technical", "technical_metric": metric,
                            "technical_relation": relation, "tolerance": tolerance}}


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("sound,status", [("sine=frequency=1000:sample_rate=48000:duration=2", "measured"),
                                         ("anullsrc=r=48000:cl=mono:d=2", "unmeasurable")])
def test_audio_pipeline_respects_limits_and_missing_measurements(tmp_path, monkeypatch, sound, status):
    monkeypatch.delenv("META_DEV_API", raising=False)
    clip = tmp_path / "clip.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=2",
                    "-f", "lavfi", "-i", sound, "-c:v", "ffv1", "-c:a", "pcm_s16le", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/x-matroska")
    assertions = [_assertion("loudness", "integrated_loudness_lufs", "-21", tolerance=1),
                  _assertion("peak-ok", "true_peak_dbtp", "-10", "at_most"),
                  _assertion("peak-high", "true_peak_dbtp", "-30", "at_most")]
    contract = {"contract_id": "audio", "revision": 1, "tenant_id": "t", "profile": "film",
                "profile_revision": "1", "assets": [{"asset_id": "v", "media_type": "video"}],
                "assertions": assertions}
    env = run_verification(run_id="audio", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(0)).envelope
    rows = {c["assertion_id"]: c for c in env["checks"]}
    assert env["traces"] == [] and env["cost"]["estimated_usd"] == 0
    if status == "unmeasurable":
        assert {c["status"] for c in rows.values()} == {"UNCERTAIN"}
        assert env["decision"]["decision"] == "REVIEW"
    else:
        assert {k: v["status"] for k, v in rows.items()} == {"loudness": "PASS", "peak-ok": "PASS", "peak-high": "FAIL"}
        assert env["decision"]["decision"] == "BLOCK"
        assert rows["loudness"]["observed"].endswith("LUFS")
        assert rows["peak-ok"]["observed"].endswith("dBTP")
        evidence = env["report"]["evidence"]
        assert all(e["kind"] == "scan" and e["asset_sha256"] == sha for e in evidence)
        assert all(e["start_ms"] == 0 and e["end_ms"] == 2000 for e in evidence)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_audio_only_asset_has_bound_duration_and_meter_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("META_DEV_API", raising=False)
    clip = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=1000:sample_rate=48000:duration=2", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="audio/wav")
    contract = {"contract_id": "voice", "revision": 1, "tenant_id": "t", "profile": "film",
                "profile_revision": "1", "assets": [{"asset_id": "v", "media_type": "audio"}],
                "assertions": [_assertion("peak", "true_peak_dbtp", "-10", "at_most")]}
    env = run_verification(run_id="voice", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("v", 1, sha, "audio")], store=store, budget=CapBudget(0)).envelope
    assert env["checks"][0]["status"] == "PASS"
    assert env["report"]["assets"][0]["duration_ms"] == 2000
    assert env["report"]["evidence"][0]["end_ms"] == 2000
