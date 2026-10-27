"""DB persistence for the repair-request / repair-receipt routes.

Request building and receipt validation live in proofframe.repair.protocol (lead-owned):
  build_repair_request(envelope: dict, contract_json: dict) -> dict
  accept_receipt(*, receipt: dict, request: dict, envelope: dict, contract_json: dict) -> dict | None
      raises ValueError on rejection; may return {"assertion_ids": [...]} to override the retest set.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs
from ..config import Settings
from ..db import (AssetVersion, ContractRow, Envelope, RepairReceiptRow, RepairRequestRow, Run)


def _protocol():
    try:
        from . import protocol  # lead-owned
    except ImportError as e:
        raise NotImplementedError(f"proofframe.repair.protocol not available: {e}")
    return protocol


def _drop(settings: Settings, sub: str, name: str, payload: dict[str, Any]) -> str | None:
    """Write to the file-drop directory atomically; returns path or None if not writable."""
    try:
        d = settings.dropbox_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{name}.tmp"
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2))
        os.replace(tmp, d / f"{name}.json")
        return str(d / f"{name}.json")
    except OSError:
        return None


def create_repair_request(db: Session, settings: Settings, tenant: str, run_id: str) -> dict[str, Any]:
    proto = _protocol()
    run = db.scalar(select(Run).where(Run.tenant_id == tenant, Run.run_id == run_id))
    env = db.get(Envelope, run_id)
    if run is None:
        raise LookupError("run not found")
    if run.status != "succeeded" or env is None or env.tenant_id != tenant:
        raise jobs.Conflict(f"run is {run.status}; a repair request needs a succeeded run")
    contract = db.scalar(select(ContractRow).where(
        ContractRow.tenant_id == tenant, ContractRow.sha256 == run.contract_sha256))
    # attempt number = repair requests already issued along this run's lineage (cap enforced in protocol)
    chain, cur = [], run
    while cur is not None:
        chain.append(cur.run_id)
        cur = (db.scalar(select(Run).where(Run.tenant_id == tenant, Run.run_id == cur.previous_run_id))
               if cur.previous_run_id else None)
    prior = db.scalars(select(RepairRequestRow).where(RepairRequestRow.tenant_id == tenant,
                                                      RepairRequestRow.run_id.in_(chain))).all()
    prior_other = [r for r in prior if r.run_id != run_id]
    try:
        request = proto.build_repair_request(env.envelope, contract.body, attempt=len(prior_other) + 1)
    except ValueError as e:
        raise jobs.Conflict(str(e))
    plan_sha = request.get("plan_sha256") or jobs.canonical_hash(request)
    existing = db.scalar(select(RepairRequestRow).where(
        RepairRequestRow.tenant_id == tenant, RepairRequestRow.run_id == run_id,
        RepairRequestRow.plan_sha256 == plan_sha))
    if existing is None:
        existing = RepairRequestRow(request_id=request["request_id"], tenant_id=tenant,
                                    run_id=run_id, plan_sha256=plan_sha, request=request)
        db.add(existing)
        db.flush()
    path = _drop(settings, "requests", existing.request_id, request)
    return {"request_id": existing.request_id, "run_id": run_id, "plan_sha256": plan_sha,
            "request": existing.request, "dropped_to": path}


def accept_repair_receipt(db: Session, settings: Settings, tenant: str, receipt: dict[str, Any],
                          idempotency_key: str | None) -> dict[str, Any]:
    proto = _protocol()
    envelope_doc = receipt if "receipt" in receipt else None  # executor wraps {request_id, receipt, executor}
    if envelope_doc is not None:
        receipt = envelope_doc["receipt"]
    try:
        plan_sha = receipt["plan_sha256"]
        replacements = receipt["replacements"]
    except (KeyError, TypeError):
        raise ValueError("receipt needs plan_sha256 and replacements")
    req = db.scalar(select(RepairRequestRow).where(
        RepairRequestRow.tenant_id == tenant, RepairRequestRow.plan_sha256 == plan_sha))
    if req is None:
        raise LookupError("no repair request with that plan_sha256")
    prev = db.scalar(select(Run).where(Run.tenant_id == tenant, Run.run_id == req.run_id))
    env = db.get(Envelope, req.run_id)
    contract = db.scalar(select(ContractRow).where(
        ContractRow.tenant_id == tenant, ContractRow.sha256 == prev.contract_sha256))
    # current snapshot: latest revision per asset, ignoring the receipt's own new outputs.
    new_shas = {r["output"]["sha256"] for r in replacements}
    report_bind = {a["asset_id"]: a for a in env.envelope["report"]["assets"]}
    current = []
    for aid, bound in report_bind.items():
        latest = db.scalar(select(AssetVersion).where(
            AssetVersion.tenant_id == tenant, AssetVersion.asset_id == aid,
            AssetVersion.sha256.not_in(new_shas)).order_by(AssetVersion.revision.desc()).limit(1))
        if latest is None:
            raise ValueError(f"asset {aid} has no stored version")
        current.append({"asset_id": aid, "revision": latest.revision, "sha256": latest.sha256,
                        "media_type": bound["media_type"],
                        # duration is a property of the bytes; reuse the report's value only for identical bytes
                        "duration_ms": bound["duration_ms"] if latest.sha256 == bound["sha256"] else latest.duration_ms})
    verdict = proto.accept_receipt(receipt_json=receipt, request=req.request, envelope=env.envelope,
                                   contract_json=contract.body, current_assets=current) or {}
    if envelope_doc is not None:
        receipt = {**receipt, "_executor": envelope_doc.get("executor")}

    # regression asset set = previous run's assets with the receipt's replacements applied
    assets = {a["asset_id"]: {"asset_id": a["asset_id"], "sha256": a["sha256"]} for a in prev.assets}
    for rep in replacements:
        out = rep["output"]
        av = db.scalar(select(AssetVersion).where(
            AssetVersion.tenant_id == tenant, AssetVersion.asset_id == out["asset_id"],
            AssetVersion.revision == out["revision"], AssetVersion.sha256 == out["sha256"]))
        if av is None:
            raise ValueError(f"replacement output {out['asset_id']}@{out['sha256'][:12]} was not uploaded")
        assets[rep["target_asset_id"]] = {"asset_id": av.asset_id, "sha256": av.sha256}
    ids = verdict.get("assertion_ids")
    if ids is None:
        ids = sorted({i for a in req.request.get("actions", [])
                      for i in list(a.get("retest_assertions", [])) + list(a.get("preserve_assertions", []))})
    receipt_hash = jobs.canonical_hash(receipt)
    run, _created = jobs.create_run(
        db, tenant=tenant, idempotency_key=idempotency_key or f"receipt:{receipt_hash}",
        contract_sha256=prev.contract_sha256, assets=list(assets.values()),
        assertion_ids=ids or None, run_mode=prev.run_mode, previous_run_id=prev.run_id)
    row = db.scalar(select(RepairReceiptRow).where(
        RepairReceiptRow.tenant_id == tenant, RepairReceiptRow.receipt_id == "rc-" + receipt_hash[:20]))
    if row is None:
        db.add(RepairReceiptRow(receipt_id="rc-" + receipt_hash[:20], tenant_id=tenant,
                                request_id=req.request_id, new_run_id=run.run_id, receipt=receipt))
    db.flush()
    return jobs.run_dict(db, run)
