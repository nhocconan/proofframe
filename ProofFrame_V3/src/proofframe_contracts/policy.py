"""Fail-closed metadata policy. It cannot validate what a video actually shows."""
from __future__ import annotations

from .models import (AssetBinding, Contract, Evidence, PolicyDecision, RepairPlan, RepairReceipt,
                     Status, VerificationReport, fingerprint)


def _interval_covers(items: list[Evidence], start: int, end: int) -> bool:
    cursor = start
    intervals = sorted((e.start_ms, e.end_ms) for e in items
                       if e.kind == "scan" and e.inspection == "exhaustive"
                       and e.start_ms is not None)
    for lo, hi in intervals:
        if hi <= cursor:
            continue
        if lo > cursor:
            return False
        cursor = max(cursor, hi)
        if cursor >= end:
            return True
    return False


def evaluate(contract: Contract, report: VerificationReport) -> PolicyDecision:
    """Reject invalid evidence bindings; do not reinterpret execution errors as defects.

    Missing mandatory results remain REVIEW. Metadata-valid PASS is meaningful
    only if the actual detector, evidence files and audit trace are trustworthy.
    """
    if report.contract_sha256 != fingerprint(contract):
        raise ValueError("stale or different approved contract")
    specs = {a.asset_id: a for a in contract.assets}
    assets = {a.asset_id: a for a in report.assets}
    if assets.keys() != specs.keys():
        raise ValueError("report bindings do not cover the approved asset slots")
    for key, spec in specs.items():
        if assets[key].media_type != spec.media_type:
            raise ValueError("asset media type differs from approved slot")
        if spec.canonical_sha256 is not None and assets[key].sha256 != spec.canonical_sha256:
            raise ValueError("a canonical reference was replaced without approval")
    checks = {a.assertion_id: a for a in contract.assertions}
    results = {r.assertion_id: r for r in report.results}
    evidence = {e.evidence_id: e for e in report.evidence}
    if not results.keys() <= checks.keys():
        raise ValueError("unknown assertion in report")
    for item in report.evidence:
        bound = assets.get(item.asset_id)
        if bound is None or bound.sha256 != item.asset_sha256:
            raise ValueError("unknown or stale evidence asset")
        if item.end_ms is not None:
            if bound.duration_ms is None or item.end_ms > bound.duration_ms:
                raise ValueError("evidence exceeds source media duration")
    unresolved: list[str] = []
    failed: list[str] = []
    advisory: list[str] = []
    for check in contract.assertions:
        result = results.get(check.assertion_id)
        if result is None:
            (unresolved if check.blocking else advisory).append(check.assertion_id)
            continue
        if not set(result.evidence_ids) <= evidence.keys():
            raise ValueError("dangling evidence reference")
        selected = [evidence[key] for key in result.evidence_ids]
        allowed_assets = {check.target_asset_id, *check.reference_asset_ids}
        if any(e.asset_id not in allowed_assets for e in selected):
            raise ValueError("evidence belongs to an unrelated asset")
        if result.status in {Status.PASS, Status.FAIL}:
            if not any(e.asset_id == check.target_asset_id for e in selected):
                raise ValueError("reference alone is not evidence about the output")
        if result.status == Status.PASS:
            if check.coverage.kind == "interval_scan":
                duration = assets[check.target_asset_id].duration_ms
                if duration is None or check.coverage.end_ms > duration:
                    raise ValueError("coverage requirement exceeds available media")
            target_evidence = [e for e in selected if e.asset_id == check.target_asset_id]
            if len({e.artifact_sha256 for e in target_evidence}) < check.coverage.minimum_items:
                raise ValueError("insufficient distinct target evidence")
            if check.coverage.kind == "sampled" and not any(
                e.kind in {"frame", "clip", "audio", "scan"} for e in target_evidence
            ):
                raise ValueError("sampled observation cannot be satisfied by metadata")
            if check.coverage.kind == "interval_scan" and not _interval_covers(
                target_evidence, check.coverage.start_ms, check.coverage.end_ms
            ):
                raise ValueError("sparse or gapped evidence cannot claim full interval coverage")
            if any(dep not in results or results[dep].status != Status.PASS
                   for dep in check.depends_on):
                raise ValueError("dependent PASS without passed prerequisites")
        excluded = (result.status == Status.NOT_APPLICABLE
                    and check.approved_exclusion is not None)
        if check.blocking:
            if result.status == Status.FAIL:
                failed.append(check.assertion_id)
            elif result.status != Status.PASS and not excluded:
                unresolved.append(check.assertion_id)
        elif result.status != Status.PASS and not excluded:
            advisory.append(check.assertion_id)
    decision = "BLOCK" if failed else "REVIEW" if unresolved else "ELIGIBLE"
    return PolicyDecision(decision=decision, unresolved=tuple(unresolved),
                          blocking_failures=tuple(failed), advisory_findings=tuple(advisory),
                          run_mode=report.run_mode)


def validate_plan(contract: Contract, report: VerificationReport, plan: RepairPlan) -> None:
    evaluate(contract, report)
    if plan.contract_sha256 != fingerprint(contract):
        raise ValueError("repair cannot rewrite approved intent")
    if plan.based_on_report_sha256 != fingerprint(report):
        raise ValueError("stale report for repair")
    assets = {a.asset_id: a for a in report.assets}
    specs = {a.asset_id: a for a in contract.assets}
    checks = {a.assertion_id: a for a in contract.assertions}
    findings = {r.assertion_id: r for r in report.results}
    for action in plan.actions:
        current = assets.get(action.target_asset_id)
        spec = specs.get(action.target_asset_id)
        if spec is None or spec.role != "output":
            raise ValueError("repairs cannot rewrite approved reference assets")
        if current is None or current.sha256 != action.expected_sha256:
            raise ValueError("stale repair target")
        for key in (*action.preserve_assertions, *action.retest_assertions, *action.finding_ids):
            if key not in checks:
                raise ValueError("unknown repair check")
        for key in action.finding_ids:
            finding = findings.get(key)
            if finding is None or finding.status not in {Status.FAIL, Status.UNCERTAIN}:
                raise ValueError("repairs require an actual failure or unresolved observation")
            check = checks[key]
            if check.target_asset_id != action.target_asset_id:
                raise ValueError("this seed only authorizes repairs to the failed target")
            if finding.status == Status.UNCERTAIN and action.action != "HUMAN_REVIEW":
                raise ValueError("uncertainty cannot authorize a generative repair")
        if not set(action.finding_ids) <= set(action.retest_assertions):
            raise ValueError("repair cannot omit its failed assertions from retesting")


def validate_receipt(contract: Contract, report: VerificationReport, plan: RepairPlan,
                     receipt: RepairReceipt, *, current_assets: tuple[AssetBinding, ...]) -> None:
    validate_plan(contract, report, plan)
    if report.run_mode == "live" and receipt.execution_mode != "real":
        raise ValueError("a staged receipt cannot complete a live repair")
    if receipt.plan_sha256 != fingerprint(plan):
        raise ValueError("receipt uses a stale repair plan")
    assets = {a.asset_id: a for a in report.assets}
    current = {a.asset_id: a for a in current_assets}
    if len(current) != len(current_assets):
        raise ValueError("duplicate current asset binding")
    if assets != current:
        raise ValueError("repair base is no longer the current asset snapshot")
    permitted = {a.target_asset_id for a in plan.actions if a.action != "HUMAN_REVIEW"}
    for replacement in receipt.replacements:
        if replacement.target_asset_id not in permitted:
            raise ValueError("executor changed an unauthorized asset")
        previous = assets[replacement.target_asset_id]
        if replacement.input_sha256 != previous.sha256:
            raise ValueError("stale repair input")
        output = replacement.output
        if output.asset_id != previous.asset_id or output.revision <= previous.revision:
            raise ValueError("replacement must be a new revision of the same logical asset")
        if output.sha256 == previous.sha256:
            raise ValueError("unchanged bytes are not a new repair artifact")
        if output.media_type != previous.media_type:
            raise ValueError("replacement changed the expected media type")
    # A valid receipt is NOT proof that the repair succeeded. Reverification is mandatory.


def affected_assertions(contract: Contract, changed_asset_ids: set[str]) -> tuple[str, ...]:
    known = {a.asset_id for a in contract.assets}
    if not changed_asset_ids <= known:
        raise ValueError("unknown changed asset")
    selected = {a.assertion_id for a in contract.assertions if a.global_sentinel
                or a.target_asset_id in changed_asset_ids
                or set(a.reference_asset_ids) & changed_asset_ids}
    while True:
        expanded = selected | {a.assertion_id for a in contract.assertions
                               if set(a.depends_on) & selected}
        if expanded == selected:
            return tuple(sorted(selected))
        selected = expanded
