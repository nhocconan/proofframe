"""Real decoded measurements through policy; synthetic fixtures, no perception claim."""
from __future__ import annotations

import subprocess

import pytest

from proofframe.interfaces import AssetInput
from proofframe.verify.pipeline import run_verification
from tests.test_core_pipeline import CapBudget, DirStore, HAS_FFMPEG


def contract(metric, scope=None):
    assertion = {"assertion_id": "qc", "source_pointer": "/delivery/qc", "target_asset_id": "v",
                 "predicate": "approved maximum decoded defect duration", "expected": "0",
                 "observation": {"kind": "technical", "subject": "delivery", "attribute": metric,
                                 "comparator": "technical", "technical_metric": metric}}
    if scope:
        assertion["scope"] = scope
    return {"contract_id": "decoded", "revision": 1, "tenant_id": "t", "profile": "film",
            "profile_revision": "1", "assets": [{"asset_id": "v", "media_type": "video"}],
            "assertions": [assertion]}


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("black,expected", [(False, "PASS"), (True, "FAIL")])
def test_decoded_qc_localizes_real_media_without_provider(tmp_path, monkeypatch, black, expected):
    monkeypatch.delenv("META_DEV_API", raising=False)
    clip = tmp_path / "clip.mp4"
    source = "color=c=black:size=160x90:rate=24:duration=2" if black else "testsrc2=size=160x90:rate=24:duration=2"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-c:v", "libx264", str(clip)],
                   check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    env = run_verification(run_id="qc", run_mode="live", contract_json=contract("black_duration_ms"),
                           assets=[AssetInput("v", 1, sha, "video")], store=store,
                           budget=CapBudget(0)).envelope
    check = env["checks"][0]
    assert check["status"] == expected
    assert env["decision"]["decision"] == ("BLOCK" if black else "ELIGIBLE")
    assert env["cost"]["estimated_usd"] == 0 and env["traces"] == []
    ev = env["report"]["evidence"][0]
    assert ev["kind"] == "scan" and ev["inspection"] == "exhaustive"
    assert ev["asset_sha256"] == sha and (ev["start_ms"], ev["end_ms"]) == (0, 2000)
    if black:
        assert int(check["observed"]) >= 1900
        assert check["focus"]["start_ms"] == 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_qc_invalid_scope_is_error_never_pass(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=white:size=160x90:duration=1", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    env = run_verification(run_id="scope", run_mode="synthetic_fixture",
                           contract_json=contract("black_duration_ms", {"start_ms": 0, "end_ms": 2000}),
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(0)).envelope
    assert env["checks"][0]["status"] == "ERROR"
    assert env["decision"]["decision"] == "REVIEW"


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_qc_non_aligned_scope_does_not_claim_unchecked_prefix(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=160x90:rate=10:duration=2", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    env = run_verification(run_id="gap", run_mode="synthetic_fixture",
                           contract_json=contract("black_duration_ms", {"start_ms": 150, "end_ms": 1850}),
                           assets=[AssetInput("v", 1, sha, "video")], store=store, budget=CapBudget(0)).envelope
    assert env["checks"][0]["status"] == "UNCERTAIN"
    assert env["decision"]["decision"] == "REVIEW"
    assert env["report"]["evidence"][0]["start_ms"] == 200
