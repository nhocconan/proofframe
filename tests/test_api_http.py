import hashlib

from sqlalchemy import text

from .test_api_support import (AUTH, contract_json, engine, client, post_run, queued_run,  # noqa: F401
                               settings, pg_url, store, upload, video_bytes)


def test_auth_required_and_healthz_open(client, queued_run):
    assert client.get("/healthz").json() == {"ok": True}
    for path in ("/v1/assets", "/v1/verifications", "/v1/budget", "/v1/capabilities"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get(path + "?token=test-token").status_code == 401  # query token only for media
    sha = queued_run[2]
    assert client.get(f"/v1/media/{sha}").status_code == 401
    assert client.get(f"/v1/media/{sha}?token=wrong").status_code == 401
    assert client.get(f"/v1/media/{sha}?token=test-token").status_code == 200
    assert client.get("/v1/capabilities", headers=AUTH).json()["models"]


def test_upload_hash_dedupe_and_revisions(client, video_bytes):
    r = upload(client, video_bytes)
    assert r.status_code == 201
    a = r.json()
    assert a["sha256"] == hashlib.sha256(video_bytes).hexdigest()
    assert (a["revision"], a["width"], a["height"], a["has_audio"]) == (1, 320, 240, True)
    assert 2900 <= a["duration_ms"] <= 3200 and a["url"] == f"/v1/media/{a['sha256']}"
    again = upload(client, video_bytes)
    assert again.status_code == 200 and again.json() == a  # identical bytes -> existing version
    r2 = upload(client, video_bytes + b"\0" * 0 + b"")  # same bytes again, still deduped
    assert r2.json()["revision"] == 1
    other = upload(client, video_bytes, asset_id="shot-02").json()  # blob deduped, new asset slot
    assert other["revision"] == 1 and other["sha256"] == a["sha256"]
    assert len(client.get("/v1/assets", headers=AUTH).json()) == 2


def test_new_bytes_bump_revision_and_reject_non_media(client, video_bytes, tmp_path):
    import subprocess
    p = tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                    str(p)], check=True)
    assert upload(client, video_bytes).json()["revision"] == 1
    v2 = upload(client, p.read_bytes()).json()
    assert v2["revision"] == 2 and v2["has_audio"] is False
    bad = upload(client, b"this is not media at all", name="x.mp4")
    assert bad.status_code == 422
    assert upload(client, b"x", media_type="bogus").status_code == 422


def test_range_requests(client, video_bytes):
    sha = upload(client, video_bytes).json()["sha256"]
    url = f"/v1/media/{sha}"
    full = client.get(url, headers=AUTH)
    assert full.status_code == 200 and full.content == video_bytes
    assert full.headers["content-type"] == "video/mp4" and full.headers["accept-ranges"] == "bytes"
    r = client.get(url, headers={**AUTH, "Range": "bytes=0-99"})
    n = len(video_bytes)
    assert r.status_code == 206 and len(r.content) == 100 and r.content == video_bytes[:100]
    assert r.headers["content-range"] == f"bytes 0-99/{n}"
    r = client.get(url, headers={**AUTH, "Range": "bytes=100-"})
    assert r.status_code == 206 and r.content == video_bytes[100:]
    assert r.headers["content-range"] == f"bytes 100-{n - 1}/{n}"
    r = client.get(url, headers={**AUTH, "Range": "bytes=-50"})
    assert r.status_code == 206 and r.content == video_bytes[-50:]
    assert client.get(url, headers={**AUTH, "Range": f"bytes={n}-"}).status_code == 416
    assert client.head(url, headers=AUTH).headers["content-length"] == str(n)
    assert client.get("/v1/media/" + "0" * 64, headers=AUTH).status_code == 404
    assert client.get("/v1/media/..%2f..%2fetc", headers=AUTH).status_code == 404


def test_contract_immutability(client):
    c = contract_json()
    r = client.post("/v1/contracts", headers=AUTH, json=c)
    assert r.status_code == 201
    sha = r.json()["contract_sha256"]
    assert client.post("/v1/contracts", headers=AUTH, json=c).status_code == 200  # identical: idempotent
    changed = contract_json(expected="Approved red shirt")
    assert client.post("/v1/contracts", headers=AUTH, json=changed).status_code == 409
    assert client.get(f"/v1/contracts/{sha}", headers=AUTH).json()["contract_id"] == "film-1"
    rev2 = client.post("/v1/contracts", headers=AUTH, json=contract_json(revision=2, expected="Approved red shirt"))
    assert rev2.status_code == 201 and rev2.json()["contract_sha256"] != sha
    assert client.post("/v1/contracts", headers=AUTH, json={"contract_id": "x"}).status_code == 422
    foreign = {**contract_json(cid="other"), "tenant_id": "someone-else"}
    assert client.post("/v1/contracts", headers=AUTH, json=foreign).status_code == 403


def test_idempotency_key(client, queued_run):
    run, csha, asha = queued_run
    assert run["status"] == "queued" and run["attempts"] == 0
    same = post_run(client, csha, asha)
    assert same.status_code == 200 and same.json()["run_id"] == run["run_id"]
    assert len(client.get("/v1/verifications", headers=AUTH).json()) == 1
    diff = post_run(client, csha, asha, assertion_ids=["wardrobe-01"])
    assert diff.status_code == 409
    other = post_run(client, csha, asha, key="k2")
    assert other.json()["run_id"] != run["run_id"]
    no_key = client.post("/v1/verifications", headers=AUTH, json={})
    assert no_key.status_code == 400
    assert post_run(client, "f" * 64, asha, key="k3").status_code == 422
    assert post_run(client, csha, asha, key="k4", assertion_ids=["nope"]).status_code == 422


def test_report_404_until_succeeded_and_cancel(client, queued_run):
    run = queued_run[0]
    assert client.get(f"/v1/verifications/{run['run_id']}/report", headers=AUTH).status_code == 404
    c = client.post(f"/v1/verifications/{run['run_id']}/cancel", headers=AUTH)
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and c.json()["cancel_requested"]
    assert client.post(f"/v1/verifications/{run['run_id']}/cancel", headers=AUTH).status_code == 409


def test_tenant_filter(client, engine, queued_run):
    run, csha, asha = queued_run
    with engine.begin() as c:
        c.execute(text("INSERT INTO asset_versions (tenant_id,asset_id,revision,sha256,media_type,mime,bytes,has_audio)"
                       " VALUES ('other','alien',1,:s,'video','video/mp4',1,false)"), {"s": "e" * 64})
        c.execute(text("INSERT INTO blobs (tenant_id,sha256,media_type,bytes) VALUES ('other',:s,'video/mp4',1)"),
                  {"s": "d" * 64})
        c.execute(text("UPDATE runs SET tenant_id='other'"))
        c.execute(text("UPDATE contracts SET tenant_id='other'"))
    assert [a["asset_id"] for a in client.get("/v1/assets", headers=AUTH).json()] == ["shot-01"]
    assert client.get("/v1/verifications", headers=AUTH).json() == []
    assert client.get(f"/v1/verifications/{run['run_id']}", headers=AUTH).status_code == 404
    assert client.get(f"/v1/contracts/{csha}", headers=AUTH).status_code == 404
    assert client.get("/v1/media/" + "d" * 64, headers=AUTH).status_code == 404  # other tenant's blob
    assert post_run(client, csha, asha, key="zz").status_code == 422  # contract not visible to this tenant


def test_capabilities_list_vendor_data_handling_with_sources():
    from proofframe.api.app import CAPABILITIES
    dh = CAPABILITIES["data_handling"]
    assert {"meta_muse_spark_standard", "elevenlabs_scribe_v2"} <= set(dh)
    assert all(v["sources"] and v["read_on"] == "2026-10-31" for v in dh.values())
    assert "Enterprise" in dh["elevenlabs_scribe_v2"]["retention"]
