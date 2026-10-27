"""Run creation / serialisation shared by the API routes and the repair glue."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import AssetVersion, ContractRow, Run


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


def canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def asset_dict(a: AssetVersion) -> dict[str, Any]:
    return {"asset_id": a.asset_id, "revision": a.revision, "sha256": a.sha256,
            "media_type": a.media_type, "bytes": a.bytes, "duration_ms": a.duration_ms,
            "width": a.width, "height": a.height, "has_audio": a.has_audio,
            "created_at": iso(a.created_at), "url": f"/v1/media/{a.sha256}"}


def run_dict(db: Session, r: Run) -> dict[str, Any]:
    assets = []
    for ref in r.assets:
        a = db.scalar(select(AssetVersion).where(
            AssetVersion.tenant_id == r.tenant_id, AssetVersion.asset_id == ref["asset_id"],
            AssetVersion.sha256 == ref["sha256"]))
        assets.append(asset_dict(a) if a else dict(ref))
    return {"run_id": r.run_id, "status": r.status, "run_mode": r.run_mode,
            "contract_sha256": r.contract_sha256, "assets": assets,
            "assertion_ids": r.assertion_ids, "previous_run_id": r.previous_run_id,
            "created_at": iso(r.created_at), "started_at": iso(r.started_at),
            "finished_at": iso(r.finished_at), "error": r.error, "decision": r.decision,
            "cost_usd_estimated": r.cost_usd_estimated, "attempts": r.attempts,
            "cancel_requested": r.cancel_requested}


RUN_MODES = ("live", "recorded_replay", "synthetic_fixture")


def create_run(db: Session, *, tenant: str, idempotency_key: str, contract_sha256: str,
               assets: list[dict[str, Any]], assertion_ids: list[str] | None, run_mode: str,
               previous_run_id: str | None) -> tuple[Run, bool]:
    """Insert a queued run. Returns (run, created). Same key + same body -> existing run;
    same key + different body -> Conflict. Caller commits."""
    if run_mode not in RUN_MODES:
        raise Invalid(f"run_mode must be one of {RUN_MODES}")
    contract = db.scalar(select(ContractRow).where(
        ContractRow.tenant_id == tenant, ContractRow.sha256 == contract_sha256))
    if contract is None:
        raise Invalid("unknown contract_sha256")
    spec_assets = {a["asset_id"] for a in contract.body.get("assets", [])}
    resolved = []
    for ref in assets:
        av = db.scalar(select(AssetVersion).where(
            AssetVersion.tenant_id == tenant, AssetVersion.asset_id == ref["asset_id"],
            AssetVersion.sha256 == ref["sha256"]).order_by(AssetVersion.revision.desc()))
        if av is None:
            raise Invalid(f"unknown asset version {ref['asset_id']}@{ref['sha256'][:12]}")
        if ref["asset_id"] not in spec_assets:
            raise Invalid(f"asset_id {ref['asset_id']} not in contract")
        resolved.append({"asset_id": av.asset_id, "revision": av.revision, "sha256": av.sha256})
    if assertion_ids:
        known = {a["assertion_id"] for a in contract.body.get("assertions", [])}
        bad = sorted(set(assertion_ids) - known)
        if bad:
            raise Invalid(f"unknown assertion_ids: {bad}")
    if previous_run_id is not None and db.scalar(select(Run.run_id).where(
            Run.tenant_id == tenant, Run.run_id == previous_run_id)) is None:
        raise Invalid("unknown previous_run_id")
    req_hash = canonical_hash({"c": contract_sha256, "a": sorted(
        resolved, key=lambda x: x["asset_id"]), "ids": assertion_ids, "m": run_mode,
        "p": previous_run_id})
    existing = db.scalar(select(Run).where(Run.tenant_id == tenant,
                                           Run.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.request_hash != req_hash:
            raise Conflict("Idempotency-Key reused with a different request body")
        return existing, False
    run = Run(run_id="run-" + uuid.uuid4().hex[:20], tenant_id=tenant, status="queued",
              run_mode=run_mode, contract_sha256=contract_sha256, assets=resolved,
              assertion_ids=assertion_ids or None, previous_run_id=previous_run_id,
              idempotency_key=idempotency_key, request_hash=req_hash, attempts=0)
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(Run).where(Run.tenant_id == tenant,
                                               Run.idempotency_key == idempotency_key))
        if existing is None:
            raise
        if existing.request_hash != req_hash:
            raise Conflict("Idempotency-Key reused with a different request body")
        return existing, False
    return run, True
