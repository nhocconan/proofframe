"""Shared fixtures for API tests: real Postgres (fresh database per session), real ffmpeg media."""
from __future__ import annotations

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient

from proofframe.api.app import create_app
from proofframe.budget_pg import PgBudget
from proofframe.config import Settings
from proofframe.db import get_engine, init_db
from proofframe.storage import LocalStore

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="session")
def pg_url():
    base = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://proofframe:proofframe@127.0.0.1:5432/proofframe")
    url = make_url(base)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = "pf_test_" + uuid.uuid4().hex[:10]
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as e:
        pytest.skip(f"no Postgres reachable: {e}")
    test_url = url.set(database=name).render_as_string(hide_password=False)
    yield test_url
    get_engine(test_url).dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def make_settings(pg_url, data_dir, **kw) -> Settings:
    base = dict(database_url=pg_url, data_dir=data_dir, dropbox_dir=data_dir / "dropbox",
                tenant_id="demo-tenant", api_token=TOKEN, allow_paid_calls=True,
                max_project_cost_usd=10.0, max_run_cost_usd=2.0, probe_spend_usd=0.0)
    base.update(kw)
    return Settings(**base)


@pytest.fixture()
def settings(pg_url, tmp_path):
    return make_settings(pg_url, tmp_path)


@pytest.fixture()
def engine(settings):
    eng = get_engine(settings.database_url)
    init_db(eng)
    with eng.begin() as c:  # isolate tests
        c.execute(text("TRUNCATE runs, envelopes, artifacts, blobs, asset_versions, contracts, "
                       "budget_ledger, budget_state, repair_requests, repair_receipts"))
    return eng


@pytest.fixture()
def client(settings, engine):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture()
def store(settings):
    return LocalStore(settings.data_dir)


@pytest.fixture()
def budget(engine, settings):
    return PgBudget(engine, settings)


@pytest.fixture(scope="session")
def video_bytes(tmp_path_factory):
    p = tmp_path_factory.mktemp("media") / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=24",
                    "-f", "lavfi", "-i", "sine=duration=3", "-shortest", "-pix_fmt", "yuv420p",
                    "-g", "12", str(p)], check=True)
    return p.read_bytes()


def upload(client, data: bytes, asset_id="shot-01", media_type="video", name="clip.mp4"):
    return client.post("/v1/assets", headers=AUTH, data={"asset_id": asset_id, "media_type": media_type},
                       files={"file": (name, data, "video/mp4")})


def contract_json(cid="film-1", revision=1, expected="Approved dark blue shirt"):
    return {"contract_id": cid, "revision": revision, "tenant_id": "demo-tenant", "profile": "film",
            "profile_revision": "test-v1",
            "assets": [{"asset_id": "shot-01", "media_type": "video"}],
            "assertions": [{"assertion_id": "wardrobe-01", "source_pointer": "/shots/01/wardrobe",
                            "target_asset_id": "shot-01", "predicate": "matches_wardrobe",
                            "expected": expected}]}


def post_run(client, csha, asset_sha, key="k1", **extra):
    body = {"contract_sha256": csha, "assets": [{"asset_id": "shot-01", "sha256": asset_sha}],
            "run_mode": "synthetic_fixture", **extra}
    return client.post("/v1/verifications", headers={**AUTH, "Idempotency-Key": key}, json=body)


@pytest.fixture()
def queued_run(client, video_bytes):
    """A contract + asset + queued run; returns (run_json, contract_sha, asset_sha)."""
    asha = upload(client, video_bytes).json()["sha256"]
    csha = client.post("/v1/contracts", headers=AUTH, json=contract_json()).json()["contract_sha256"]
    r = post_run(client, csha, asha)
    assert r.status_code == 202, r.text
    return r.json(), csha, asha
