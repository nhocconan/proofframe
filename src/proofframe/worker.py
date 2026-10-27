"""Job worker: python -m proofframe.worker. Claims queued runs with SKIP LOCKED + lease."""
from __future__ import annotations

import importlib
import logging
import os
import socket
import threading
import time
import traceback
import uuid
from typing import Any, Callable

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .budget_pg import PgBudget
from .config import Settings
from .db import Artifact, AssetVersion, Blob, ContractRow, Envelope, Run, get_engine, init_db
from .interfaces import AssetInput
from .storage import LocalStore

log = logging.getLogger("proofframe.worker")


def load_verifier() -> Callable[..., Any]:
    spec = os.environ.get("PROOFFRAME_VERIFIER")  # "module:attr" test/injection hook
    if spec:
        mod, _, attr = spec.partition(":")
        return getattr(importlib.import_module(mod), attr or "run")
    try:
        return importlib.import_module("proofframe.verify.pipeline").run_verification
    except ImportError as e:
        raise RuntimeError(f"verification core unavailable (proofframe.verify.pipeline): {e}")


def claim_one(engine: Engine, owner: str, lease_s: int, max_attempts: int = 3) -> str | None:
    """Atomically claim one runnable run; returns run_id or None. Safe under concurrent claimers."""
    with Session(engine) as db, db.begin():
        # reap: cancelled-before-start and attempts exhausted
        db.execute(update(Run).where(Run.status == "queued", Run.cancel_requested.is_(True))
                   .values(status="cancelled", finished_at=func.now()))
        db.execute(update(Run).where(Run.status == "running", Run.lease_expires_at < func.now(),
                                     Run.attempts >= max_attempts)
                   .values(status="failed", finished_at=func.now(), lease_owner=None,
                           error=f"lease expired after {max_attempts} attempts (worker crashed or hung)"))
        run = db.scalar(
            select(Run).where(or_(Run.status == "queued",
                                  and_(Run.status == "running", Run.lease_expires_at < func.now())))
            .order_by(Run.created_at).limit(1).with_for_update(skip_locked=True))
        if run is None:
            return None
        run.status = "running"
        run.lease_owner = owner
        run.lease_expires_at = func.now() + func.make_interval(0, 0, 0, 0, 0, 0, lease_s)
        run.heartbeat_at = func.now()
        run.attempts = run.attempts + 1
        run.error = None
        if run.started_at is None:
            run.started_at = func.now()
        return run.run_id


class Heartbeat(threading.Thread):
    def __init__(self, engine: Engine, run_id: str, owner: str, lease_s: int):
        super().__init__(daemon=True)
        self.engine, self.run_id, self.owner, self.lease_s = engine, run_id, owner, lease_s
        self.stop_evt = threading.Event()

    def run(self):
        while not self.stop_evt.wait(max(self.lease_s / 3, 0.2)):
            try:
                with Session(self.engine) as db, db.begin():
                    db.execute(update(Run).where(Run.run_id == self.run_id, Run.lease_owner == self.owner)
                               .values(heartbeat_at=func.now(),
                                       lease_expires_at=func.now() + func.make_interval(0, 0, 0, 0, 0, 0, self.lease_s)))
            except Exception:
                log.exception("heartbeat failed")


def _register_blob(db: Session, store: LocalStore, tenant: str, run_id: str, sha: str,
                   media_type: str | None, kind: str | None, meta: dict | None = None) -> None:
    if not isinstance(sha, str) or not store.exists(sha):
        return
    mime = media_type or store.media_type_for(sha) or "application/octet-stream"
    if "/" not in mime:
        mime = store.media_type_for(sha) or "application/octet-stream"
    size = store.path_for(sha).stat().st_size
    db.execute(pg_insert(Blob).values(tenant_id=tenant, sha256=sha, media_type=mime, bytes=size)
               .on_conflict_do_nothing())
    db.execute(pg_insert(Artifact).values(tenant_id=tenant, run_id=run_id, sha256=sha, media_type=mime,
                                          kind=kind, meta=meta or {}).on_conflict_do_nothing())


def process(engine: Engine, settings: Settings, run_id: str, owner: str, store: LocalStore,
            budget: PgBudget, verifier: Callable[..., Any] | None = None,
            lease_s: int | None = None) -> str:
    """Execute one claimed run. Returns the final status. Operational failure -> 'failed'."""
    lease_s = lease_s or settings.lease_seconds
    hb = Heartbeat(engine, run_id, owner, lease_s)
    hb.start()
    try:
        with Session(engine) as db:
            run = db.get(Run, run_id)
            contract = db.scalar(select(ContractRow).where(
                ContractRow.tenant_id == run.tenant_id, ContractRow.sha256 == run.contract_sha256))
            assets = []
            for ref in run.assets:
                av = db.scalar(select(AssetVersion).where(
                    AssetVersion.tenant_id == run.tenant_id, AssetVersion.asset_id == ref["asset_id"],
                    AssetVersion.sha256 == ref["sha256"]))
                assets.append(AssetInput(asset_id=av.asset_id, revision=av.revision,
                                         sha256=av.sha256, media_type=av.media_type))
            tenant, run_mode, ids, contract_json = run.tenant_id, run.run_mode, run.assertion_ids, contract.body
            prev_env = None
            if run.previous_run_id:
                pe = db.get(Envelope, run.previous_run_id)
                prev_env = pe.envelope if pe is not None and pe.tenant_id == run.tenant_id else None
        fn = verifier or load_verifier()
        kwargs = {"previous_envelope": prev_env} if prev_env is not None else {}
        outcome = fn(run_id=run_id, run_mode=run_mode, contract_json=contract_json, assets=assets,
                     store=store, budget=budget, assertion_ids=ids, **kwargs)
        env = outcome.envelope
        decision = (env.get("decision") or {}).get("decision")
        if decision not in ("BLOCK", "REVIEW", "ELIGIBLE"):
            raise RuntimeError("verifier returned an envelope without a valid decision")
        cost = (env.get("cost") or {}).get("estimated_usd")
        with Session(engine) as db, db.begin():
            cur = db.scalar(select(Run).where(Run.run_id == run_id).with_for_update())
            if cur.lease_owner != owner or cur.status != "running":
                return cur.status  # lease lost to another worker; do not overwrite
            if cur.cancel_requested:
                cur.status, cur.finished_at, cur.lease_owner = "cancelled", func.now(), None
                return "cancelled"
            db.merge(Envelope(run_id=run_id, tenant_id=tenant, envelope=env,
                              report_sha256=env.get("report_sha256")))
            for art in outcome.artifacts or []:
                _register_blob(db, store, tenant, run_id, art.get("sha256"),
                               art.get("media_type") or art.get("mime"), art.get("kind"),
                               {k: v for k, v in art.items() if k not in ("sha256",)})
            for ev in env.get("evidence") or []:
                _register_blob(db, store, tenant, run_id, ev.get("sha256"), None, ev.get("kind"))
            cur.status, cur.decision = "succeeded", decision
            cur.cost_usd_estimated = float(cost) if isinstance(cost, (int, float)) else None
            cur.finished_at, cur.lease_owner = func.now(), None
        return "succeeded"
    except BaseException as e:  # operational failure != content FAIL
        log.error("run %s failed: %s", run_id, traceback.format_exc())
        with Session(engine) as db, db.begin():
            db.execute(update(Run).where(Run.run_id == run_id, Run.lease_owner == owner,
                                         Run.status == "running")
                       .values(status="failed", error=f"{type(e).__name__}: {e}"[:4000],
                               finished_at=func.now(), lease_owner=None))
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return "failed"
    finally:
        hb.stop_evt.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    engine = get_engine(settings.database_url)
    for _ in range(60):
        try:
            init_db(engine)
            break
        except Exception as e:
            log.warning("db not ready: %s", e)
            time.sleep(1)
    store = LocalStore(settings.data_dir)
    budget = PgBudget(engine, settings)
    owner = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    log.info("worker %s started", owner)
    while True:
        try:
            run_id = claim_one(engine, owner, settings.lease_seconds, settings.max_attempts)
        except Exception:
            log.exception("claim failed")
            time.sleep(2)
            continue
        if run_id is None:
            time.sleep(1)
            continue
        log.info("claimed %s", run_id)
        log.info("run %s -> %s", run_id, process(engine, settings, run_id, owner, store, budget))


if __name__ == "__main__":
    main()
