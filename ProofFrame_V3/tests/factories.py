from proofframe_contracts.models import (
    AssetBinding, AssetSpec, Assertion, Contract, Evidence, CheckResult,
    VerificationReport, RepairAction, RepairPlan, Replacement, RepairReceipt,
    fingerprint,
)


def change(record, **updates):
    data = record.model_dump(mode="json")
    data.update(updates)
    return type(record).model_validate(data)


def fixture(status="PASS", profile="film"):
    asset = AssetBinding(asset_id="shot-01", revision=1, sha256="a" * 64,
                         media_type="video", duration_ms=8000)
    ref = AssetBinding(asset_id="approved-reference", revision=1, sha256="b" * 64,
                       media_type="image")
    check = Assertion(assertion_id="wardrobe-01", source_pointer="/shots/01/wardrobe",
                      target_asset_id=asset.asset_id, reference_asset_ids=(ref.asset_id,),
                      predicate="matches_approved_wardrobe", expected="Approved dark blue shirt")
    contract = Contract(contract_id="synthetic-demo", revision=1, tenant_id="demo-tenant",
                        profile=profile, profile_revision="example-not-calibrated-v1",
                        assets=(AssetSpec(asset_id=asset.asset_id, media_type="video"),
                                AssetSpec(asset_id=ref.asset_id, media_type="image",
                                          role="canonical_reference", canonical_sha256=ref.sha256)),
                        assertions=(check,))
    frame = Evidence(evidence_id="frame-01", asset_id=asset.asset_id,
                     asset_sha256=asset.sha256, artifact_sha256="c" * 64,
                     kind="frame", inspection="sampled", uri="fixture://not-real-media/frame-01",
                     extractor_version="synthetic-fixture-v1", trace_id="fixture-trace",
                     start_ms=2000, end_ms=2040)
    result = CheckResult(assertion_id=check.assertion_id, status=status,
                         evidence_ids=(frame.evidence_id,), rationale="Illustrative fixture only; no model ran.",
                         evaluator_version="synthetic-policy-test-v1")
    report = VerificationReport(run_id="fixture-run", run_mode="synthetic_fixture",
                                contract_sha256=fingerprint(contract), assets=(asset, ref),
                                evidence=(frame,), results=(result,))
    return contract, report


def repair_fixture():
    contract, report = fixture(status="FAIL")
    action = RepairAction(action_id="repair-01", action="REGENERATE_SHOT",
                          target_asset_id="shot-01", expected_sha256=report.assets[0].sha256,
                          requested_change="Restore the approved shirt; preserve camera, dialogue and duration.",
                          finding_ids=("wardrobe-01",), retest_assertions=("wardrobe-01",))
    plan = RepairPlan(plan_id="plan-01", contract_sha256=fingerprint(contract),
                      based_on_report_sha256=fingerprint(report), actions=(action,))
    replacement = Replacement(target_asset_id="shot-01", input_sha256=report.assets[0].sha256,
                              output=change(report.assets[0], revision=2, sha256="d" * 64))
    receipt = RepairReceipt(plan_sha256=fingerprint(plan), replacements=(replacement,),
                            execution_mode="staged_fixture")
    return contract, report, plan, receipt
