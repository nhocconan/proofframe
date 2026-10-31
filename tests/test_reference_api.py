"""Video-only API accepts one video plus an optional image reference (needs Postgres, like the other API tests)."""
import subprocess

import pytest

from .test_api_support import (AUTH, engine, client, pg_url, settings, store, upload,  # noqa: F401
                               video_bytes)


@pytest.fixture()
def still_bytes(tmp_path):
    p = tmp_path / "still.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=1:duration=1",
                    "-frames:v", "1", str(p)], check=True)
    return p.read_bytes()


def _post(client, assets, key):
    return client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": key},
                       json={"mode": "video_only", "assets": assets, "run_mode": "synthetic_fixture"})


def _upload_pair(client, video_bytes, still_bytes):
    v = upload(client, video_bytes, asset_id="clip").json()
    r = upload(client, still_bytes, asset_id="clip-reference", media_type="image", name="still.png")
    assert r.status_code == 201, r.text
    return v, r.json()


def test_video_only_with_reference_stores_bound_contract(client, video_bytes, still_bytes):
    v, r = _upload_pair(client, video_bytes, still_bytes)
    resp = _post(client, [{"asset_id": "clip", "sha256": v["sha256"]},
                          {"asset_id": "clip-reference", "sha256": r["sha256"]}], "ref-1")
    assert resp.status_code == 202, resp.text
    contract = client.get(f"/v1/contracts/{resp.json()['contract_sha256']}", headers=AUTH).json()
    ref = next(a for a in contract["assets"] if a["asset_id"] == "clip-reference")
    assert (ref["role"], ref["media_type"], ref["canonical_sha256"]) == ("canonical_reference", "image", r["sha256"])
    check = next(a for a in contract["assertions"] if a["assertion_id"] == "reference-match")
    assert check["reference_asset_ids"] == ["clip-reference"] and check["target_asset_id"] == "clip"


def test_video_only_without_reference_has_no_reference_check(client, video_bytes):
    v = upload(client, video_bytes, asset_id="clip").json()
    resp = _post(client, [{"asset_id": "clip", "sha256": v["sha256"]}], "ref-2")
    assert resp.status_code == 202, resp.text
    contract = client.get(f"/v1/contracts/{resp.json()['contract_sha256']}", headers=AUTH).json()
    assert "reference-match" not in {a["assertion_id"] for a in contract["assertions"]}


def test_video_only_rejects_image_alone_two_videos_and_two_images(client, video_bytes, still_bytes):
    v, r = _upload_pair(client, video_bytes, still_bytes)
    v2 = upload(client, video_bytes + b"\0", asset_id="clip2")
    r2 = upload(client, still_bytes + b"\0", asset_id="ref2", media_type="image", name="s2.png")
    ref, vid = {"asset_id": "clip-reference", "sha256": r["sha256"]}, {"asset_id": "clip", "sha256": v["sha256"]}
    assert _post(client, [ref], "bad-1").status_code == 422
    assert _post(client, [vid, vid], "bad-2").status_code == 422
    if v2.status_code == 201 and r2.status_code == 201:
        assert _post(client, [vid, {"asset_id": "clip2", "sha256": v2.json()["sha256"]}], "bad-3").status_code == 422
        assert _post(client, [vid, ref, {"asset_id": "ref2", "sha256": r2.json()["sha256"]}],
                     "bad-4").status_code == 422
