"""Source-aware repair requests and receipt acceptance, built on the seed policy functions.

A repair request never changes approved intent: it names the failed findings, the unchanged
contract hash, the exact target input hash, the source stage to change, what must be preserved,
which executor capability may run it, the cost basis and the retest scope. A receipt is an
execution record only; acceptance just authorizes reverification of the new bytes.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from proofframe_contracts.models import (AssetBinding, Contract, RepairAction, RepairPlan, RepairReceipt,
                                         VerificationReport, fingerprint)
from proofframe_contracts.policy import affected_assertions, validate_plan, validate_receipt

MAX_ATTEMPTS = int(os.environ.get("PROOFFRAME_MAX_REPAIR_ATTEMPTS", "2"))

# Typed action -> (source stage, allowlisted executor capability). Nothing else is executable.
ACTION_FOR_KIND = {
    "on_screen_text": ("FIX_COMPOSITE", "compositing/lower_third", "ffmpeg_drawtext_composite"),
    "visual_attribute": ("REGENERATE_SHOT", "generation/shot", "external_generator_file_drop"),
}


def build_repair_request(envelope: dict[str, Any], contract_json: dict[str, Any], *,
                         attempt: int = 1) -> dict[str, Any]:
    if attempt > MAX_ATTEMPTS:
        raise ValueError(f"repair attempt cap reached ({MAX_ATTEMPTS}) — stop and escalate to HUMAN_REVIEW")
    if envelope["run"]["run_mode"] != "live":
        raise ValueError("repairs are only requested from live runs")
    contract = Contract.model_validate(contract_json)
    report = VerificationReport.model_validate(envelope["report"])
    checks = {a.assertion_id: a for a in contract.assertions}
    rows = {c["assertion_id"]: c for c in envelope["checks"]}
    assets = {a.asset_id: a for a in report.assets}
    actions, stages = [], []
    for r in report.results:
        a = checks[r.assertion_id]
        if r.status.value not in ("FAIL", "UNCERTAIN") or not a.blocking:
            continue
        kind = a.observation.kind if a.observation else None
        if r.status.value == "UNCERTAIN" or kind not in ACTION_FOR_KIND:
            action, stage, capability = "HUMAN_REVIEW", "review", "owner"
        else:
            action, stage, capability = ACTION_FOR_KIND[kind]
        retest = affected_assertions(contract, {a.target_asset_id})
        preserve = tuple(x for x in retest if x != a.assertion_id and rows.get(x, {}).get("status") == "PASS")
        actions.append(RepairAction(
            action_id=f"act-{a.assertion_id}", action=action, target_asset_id=a.target_asset_id,
            expected_sha256=assets[a.target_asset_id].sha256,
            requested_change=(f"At source stage '{stage}', set {a.source_pointer} to the approved value; "
                              f"re-render only {a.target_asset_id} {_scope(a)}."),
            finding_ids=(a.assertion_id,), preserve_assertions=preserve, retest_assertions=retest))
        stages.append({"action_id": f"act-{a.assertion_id}", "source_stage": stage,
                       "executor_capability": capability, "source_pointer": a.source_pointer,
                       "set_to": a.expected, "scope": a.scope.model_dump() if a.scope else None,
                       "observed_defect": rows[a.assertion_id].get("observed"),
                       "evidence_ids": list(r.evidence_ids)})
    if not actions:
        raise ValueError("no blocking FAIL/UNCERTAIN findings — nothing to repair")
    plan = RepairPlan(plan_id=f"plan-{uuid.uuid4().hex[:10]}", contract_sha256=fingerprint(contract),
                      based_on_report_sha256=fingerprint(report), max_attempts_per_target=MAX_ATTEMPTS,
                      actions=tuple(actions))
    validate_plan(contract, report, plan)  # seed: stale/unauthorized/uncertain-generative repairs rejected
    return {
        "schema_version": "proofframe.repair-request.v0.1",
        "request_id": f"rr-{uuid.uuid4().hex[:10]}",
        "run_id": envelope["run"]["run_id"],
        "contract_sha256": plan.contract_sha256,
        "report_sha256": plan.based_on_report_sha256,
        "attempt": attempt,
        "plan": plan.model_dump(mode="json"),
        "plan_sha256": fingerprint(plan),
        "stages": stages,
        "current_assets": [b.model_dump(mode="json") for b in report.assets],
        "estimated_cost_basis": ("executor: local CPU ffmpeg composite, $0 provider spend; "
                                 "reverification: Meta muse-spark-1.3 ≈ $0.01–0.03 per visual check "
                                 "(usage × list price, CAPABILITY_PROBES.md)"),
        "stop_conditions": [f"max {MAX_ATTEMPTS} attempts per target", "same failure recurs",
                            "new critical regression", "budget exhausted"],
        "forbidden": ["changing approved contract or canonical references", "dropping retests",
                      "shortening duration", "editing other assets", "arbitrary commands"],
    }


def _scope(a) -> str:
    return f"within {a.scope.start_ms}-{a.scope.end_ms} ms" if a.scope else "(whole asset)"


def accept_receipt(*, receipt_json: dict[str, Any], request: dict[str, Any], envelope: dict[str, Any],
                   contract_json: dict[str, Any], current_assets: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate an executor receipt. Returns {assets, assertion_ids} for the regression run.

    `current_assets` = the asset versions currently bound for this contract (to reject stale bases).
    """
    contract = Contract.model_validate(contract_json)
    report = VerificationReport.model_validate(envelope["report"])
    plan = RepairPlan.model_validate(request["plan"])
    receipt = RepairReceipt.model_validate(receipt_json)
    current = tuple(AssetBinding.model_validate(a) for a in current_assets)
    validate_receipt(contract, report, plan, receipt, current_assets=current)
    changed = {r.target_asset_id for r in receipt.replacements}
    new_assets = {a.asset_id: a for a in report.assets}
    for r in receipt.replacements:
        new_assets[r.target_asset_id] = r.output
    return {"assets": [{"asset_id": a.asset_id, "sha256": a.sha256, "revision": a.revision}
                       for a in new_assets.values()],
            "assertion_ids": list(affected_assertions(contract, changed))}
