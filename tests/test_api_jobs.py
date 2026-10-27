import sys
import threading
import types

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from proofframe import worker
from proofframe.budget_pg import PgBudget
from proofframe.db import Run
from proofframe.interfaces import BudgetExhausted

from .test_api_support import (AUTH, TOKEN, budget, client, contract_json, engine, make_settings,  # noqa: F401
                               pg_url, post_run, queued_run, settings, store, upload, video_bytes)
from . import fake_verifier


def _run_row(engine, run_id):
    with Session(engine) as db:
        return db.get(Run, run_id)


def test_worker_end_to_end_with_fake_verifier(client, engine, settings, store, budget, queued_run, monkeypatch):
    run = queued_run[0]
    monkeypatch.setenv("PROOFFRAME_VERIFIER", "tests.fake_verifier:run")
    rid = worker.claim_one(engine, "w1", 60)
    assert rid == run["run_id"]
    assert worker.process(engine, settings, rid, "w1", store, budget) == "succeeded"
    r = client.get(f"/v1/verifications/{rid}", headers=AUTH).json()
    assert r["status"] == "succeeded" and r["decision"] == "REVIEW" and r["attempts"] == 1
    rep = client.get(f"/v1/verifications/{rid}/report", headers=AUTH).json()
    assert rep["run"]["run_mode"] == "synthetic_fixture" and rep["decision"]["publish_authorized"] is False
    ev_sha = rep["evidence"][0]["sha256"]  # artifact became servable
    m = client.get(f"/v1/media/{ev_sha}", headers=AUTH)
    assert m.status_code == 200 and m.headers["content-type"] == "image/png"
    assert worker.claim_one(engine, "w1", 60) is None  # nothing left


def test_operational_failure_is_failed_not_fail(client, engine, settings, store, budget, video_bytes):
    asha = upload(client, video_bytes).json()["sha256"]
    csha = client.post("/v1/contracts", headers=AUTH, json=contract_json(cid="boom-1")).json()["contract_sha256"]
    rid = post_run(client, csha, asha).json()["run_id"]
    worker.claim_one(engine, "w1", 60)
    assert worker.process(engine, settings, rid, "w1", store, budget, verifier=fake_verifier.run) == "failed"
    r = client.get(f"/v1/verifications/{rid}", headers=AUTH).json()
    assert r["status"] == "failed" and "exploded" in r["error"] and r["decision"] is None
    assert client.get(f"/v1/verifications/{rid}/report", headers=AUTH).status_code == 404


def test_missing_pipeline_fails_clearly(client, engine, settings, store, budget, queued_run, monkeypatch):
    monkeypatch.delenv("PROOFFRAME_VERIFIER", raising=False)
    monkeypatch.setitem(sys.modules, "proofframe.verify.pipeline", None)  # simulate absent core
    rid = worker.claim_one(engine, "w1", 60)
    assert worker.process(engine, settings, rid, "w1", store, budget) == "failed"
    assert "verification core unavailable" in _run_row(engine, rid).error


def test_concurrent_claimers_claim_once(client, engine, queued_run):
    got, barrier = [], threading.Barrier(8)

    def go(i):
        barrier.wait()
        got.append(worker.claim_one(engine, f"w{i}", 60))

    ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert [g for g in got if g] == [queued_run[0]["run_id"]]
    assert _run_row(engine, queued_run[0]["run_id"]).attempts == 1


def test_lease_expiry_reclaim_and_attempt_cap(client, engine, queued_run):
    rid = queued_run[0]["run_id"]
    assert worker.claim_one(engine, "w1", 300) == rid
    assert worker.claim_one(engine, "w2", 300) is None  # lease still valid
    for expected_attempts, owner in ((2, "w2"), (3, "w3")):
        with engine.begin() as c:
            c.execute(text("UPDATE runs SET lease_expires_at = now() - interval '1 second'"))
        assert worker.claim_one(engine, owner, 300) == rid
        row = _run_row(engine, rid)
        assert row.lease_owner == owner and row.attempts == expected_attempts
    with engine.begin() as c:
        c.execute(text("UPDATE runs SET lease_expires_at = now() - interval '1 second'"))
    assert worker.claim_one(engine, "w4", 300) is None
    row = _run_row(engine, rid)
    assert row.status == "failed" and "attempts" in row.error


def test_stale_worker_cannot_overwrite_after_reclaim(client, engine, settings, store, budget, queued_run):
    rid = queued_run[0]["run_id"]
    worker.claim_one(engine, "w1", 300)
    with engine.begin() as c:
        c.execute(text("UPDATE runs SET lease_expires_at = now() - interval '1 second'"))
    worker.claim_one(engine, "w2", 300)
    assert worker.process(engine, settings, rid, "w1", store, budget, verifier=fake_verifier.run) == "running"
    assert _run_row(engine, rid).lease_owner == "w2"


def test_cancel_requested_while_running_is_honoured(client, engine, settings, store, budget, queued_run):
    rid = queued_run[0]["run_id"]
    worker.claim_one(engine, "w1", 300)
    client.post(f"/v1/verifications/{rid}/cancel", headers=AUTH)
    assert worker.process(engine, settings, rid, "w1", store, budget, verifier=fake_verifier.run) == "cancelled"
    assert client.get(f"/v1/verifications/{rid}/report", headers=AUTH).status_code == 404


# -- budget -----------------------------------------------------------------------------------
def test_budget_atomic_across_threads(engine, settings):
    s = make_settings(settings.database_url, settings.data_dir, max_project_cost_usd=1.0, max_run_cost_usd=5.0)
    results, barrier = [], threading.Barrier(8)

    def go(i):
        b = PgBudget(engine, s)
        barrier.wait()
        try:
            results.append(b.reserve(run_id=f"r{i}", provider="meta", model="m", amount_usd=0.3, purpose="t"))
        except BudgetExhausted:
            results.append(None)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(r is not None for r in results) == 3  # 3 x 0.3 <= 1.0 < 4 x 0.3
    assert PgBudget(engine, s).summary()["reserved_open_usd"] == pytest.approx(0.9)


def test_two_threads_past_cap_exactly_one_refused(engine, settings):
    s = make_settings(settings.database_url, settings.data_dir, max_project_cost_usd=1.0, max_run_cost_usd=5.0)
    out, barrier = [], threading.Barrier(2)

    def go(i):
        barrier.wait()
        try:
            PgBudget(engine, s).reserve(run_id=f"r{i}", provider="meta", model="m", amount_usd=0.6, purpose="t")
            out.append("ok")
        except BudgetExhausted:
            out.append("refused")

    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out) == ["ok", "refused"]


def test_unknown_cost_settle_keeps_reservation_counted(engine, settings):
    s = make_settings(settings.database_url, settings.data_dir, max_project_cost_usd=1.0, max_run_cost_usd=1.0)
    b = PgBudget(engine, s)
    r1 = b.reserve(run_id="r", provider="meta", model="m", amount_usd=0.6, purpose="t")
    b.settle(r1, cost_usd=None, cost_basis="unknown", usage=None, remote_request_id=None, outcome="timeout")
    sm = b.summary()
    assert sm["unknown_cost_calls"] == 1 and sm["spent_settled_usd"] == pytest.approx(0.6)
    with pytest.raises(BudgetExhausted):
        b.reserve(run_id="r2", provider="meta", model="m", amount_usd=0.5, purpose="t")
    # a known, lower cost frees headroom; double-settle is ignored
    r3 = b.reserve(run_id="r3", provider="meta", model="m", amount_usd=0.4, purpose="t")
    b.settle(r3, cost_usd=0.01, cost_basis="usage*list_price", usage={"in": 1}, remote_request_id="x", outcome="ok")
    b.settle(r3, cost_usd=0.39, cost_basis="x", usage=None, remote_request_id=None, outcome="ok")
    assert b.summary()["spent_settled_usd"] == pytest.approx(0.61)


def test_run_cap_probe_seed_and_paid_flag(engine, settings):
    s = make_settings(settings.database_url, settings.data_dir, max_project_cost_usd=1.0,
                      max_run_cost_usd=0.5, probe_spend_usd=0.04597)
    b = PgBudget(engine, s)
    PgBudget(engine, s)  # re-seeding is idempotent
    assert b.summary()["spent_settled_usd"] == pytest.approx(0.04597)
    b.reserve(run_id="a", provider="p", model="m", amount_usd=0.4, purpose="t")
    with pytest.raises(BudgetExhausted):
        b.reserve(run_id="a", provider="p", model="m", amount_usd=0.2, purpose="t")  # run cap
    b.reserve(run_id="b", provider="p", model="m", amount_usd=0.5, purpose="t")
    with pytest.raises(BudgetExhausted):
        b.reserve(run_id="c", provider="p", model="m", amount_usd=0.2, purpose="t")  # project cap
    off = PgBudget(engine, make_settings(settings.database_url, settings.data_dir, allow_paid_calls=False))
    with pytest.raises(BudgetExhausted):
        off.reserve(run_id="d", provider="p", model="m", amount_usd=0.001, purpose="t")
    with pytest.raises(BudgetExhausted):
        b.reserve(run_id="d", provider="p", model="m", amount_usd=float("nan"), purpose="t")


# -- repair glue ------------------------------------------------------------------------------
def test_repair_routes_501_when_protocol_missing(client, engine, settings, store, budget, queued_run, monkeypatch):
    rid = queued_run[0]["run_id"]
    worker.claim_one(engine, "w1", 60)
    worker.process(engine, settings, rid, "w1", store, budget, verifier=fake_verifier.run)
    monkeypatch.setitem(sys.modules, "proofframe.repair.protocol", None)
    import proofframe.repair as pkg
    monkeypatch.delattr(pkg, "protocol", raising=False)
    assert client.post("/v1/repair-requests", headers=AUTH, json={"run_id": rid}).status_code == 501
    assert client.post("/v1/repair-receipts", headers=AUTH, json={"plan_sha256": "0" * 64,
                                                                   "replacements": []}).status_code == 501


def test_repair_request_and_receipt_persist_and_start_regression(client, engine, settings, store, budget,
                                                                  queued_run, video_bytes, monkeypatch, tmp_path):
    run, csha, asha = queued_run
    rid = run["run_id"]
    worker.claim_one(engine, "w1", 60)
    worker.process(engine, settings, rid, "w1", store, budget, verifier=fake_verifier.run)
    stub = types.ModuleType("proofframe.repair.protocol")
    stub.build_repair_request = lambda envelope, contract_json, attempt=1: {
        "request_id": f"rr-stub-{attempt}", "plan_id": "plan-1", "actions": [{"retest_assertions": ["wardrobe-01"], "preserve_assertions": []}]}
    stub.accept_receipt = lambda **kw: None
    import proofframe.repair as pkg
    monkeypatch.setitem(sys.modules, "proofframe.repair.protocol", stub)
    monkeypatch.setattr(pkg, "protocol", stub, raising=False)
    # dropbox is a tmp dir here
    r = client.post("/v1/repair-requests", headers=AUTH, json={"run_id": rid})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (settings.dropbox_dir / "requests" / f"{body['request_id']}.json").is_file()
    assert client.post("/v1/repair-requests", headers=AUTH, json={"run_id": rid}).json()["request_id"] == body["request_id"]
    new_sha = upload(client, video_bytes + b"", asset_id="shot-01").json()["sha256"]
    import subprocess
    p = tmp_path / "v2.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10", str(p)],
                   check=True)
    v2 = upload(client, p.read_bytes(), asset_id="shot-01").json()
    receipt = {"plan_sha256": body["plan_sha256"], "execution_mode": "staged_fixture",
               "replacements": [{"target_asset_id": "shot-01", "input_sha256": asha,
                                 "output": {"asset_id": "shot-01", "revision": v2["revision"],
                                            "sha256": v2["sha256"], "media_type": "video"}}]}
    rr = client.post("/v1/repair-receipts", headers=AUTH, json=receipt)
    assert rr.status_code == 202, rr.text
    new = rr.json()
    assert new["previous_run_id"] == rid and new["status"] == "queued" and new["assertion_ids"] == ["wardrobe-01"]
    assert new["assets"][0]["sha256"] == v2["sha256"]
    assert client.post("/v1/repair-receipts", headers=AUTH, json=receipt).json()["run_id"] == new["run_id"]
    assert client.post("/v1/repair-receipts", headers=AUTH,
                       json={**receipt, "plan_sha256": "1" * 64}).status_code == 404
