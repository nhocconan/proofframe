from fractions import Fraction

import pytest
from pydantic import ValidationError

from proofframe_contracts.models import fingerprint
from proofframe_contracts.policy import validate_plan, validate_receipt
from proofframe_contracts.timeline import TimelineSpan
from tests.factories import change, repair_fixture


def test_valid_plan_and_receipt_have_no_success_claim():
    contract, report, plan, receipt = repair_fixture()
    assert validate_plan(contract, report, plan) is None
    assert validate_receipt(contract, report, plan, receipt, current_assets=report.assets) is None
    assert not hasattr(receipt, "fixed")


@pytest.mark.parametrize("field", ["contract_sha256", "based_on_report_sha256"])
def test_stale_plan_binding_rejected(field):
    contract, report, plan, _ = repair_fixture()
    with pytest.raises(ValueError):
        validate_plan(contract, report, change(plan, **{field: "f" * 64}))


def test_stale_target_rejected():
    contract, report, plan, _ = repair_fixture()
    plan = change(plan, actions=(change(plan.actions[0], expected_sha256="f" * 64),))
    with pytest.raises(ValueError, match="stale repair target"):
        validate_plan(contract, report, plan)


def test_uncertain_evidence_requires_human_review_not_regeneration():
    contract, report, plan, _ = repair_fixture()
    report = change(report, results=(change(report.results[0], status="UNCERTAIN"),))
    plan = change(plan, based_on_report_sha256=fingerprint(report))
    with pytest.raises(ValueError, match="uncertainty"):
        validate_plan(contract, report, plan)
    plan = change(plan, actions=(change(plan.actions[0], action="HUMAN_REVIEW"),))
    validate_plan(contract, report, plan)


def test_repair_cannot_remove_failed_retest():
    _, _, plan, _ = repair_fixture()
    with pytest.raises(ValidationError):
        change(plan.actions[0], retest_assertions=())


def test_plan_cannot_invent_shell_executor():
    _, _, plan, _ = repair_fixture()
    with pytest.raises(ValidationError):
        change(plan.actions[0], action="RUN_SHELL")


def test_receipt_rejected_after_concurrent_new_render():
    contract, report, plan, receipt = repair_fixture()
    current = (change(report.assets[0], revision=2, sha256="e" * 64), report.assets[1])
    with pytest.raises(ValueError, match="no longer the current"):
        validate_receipt(contract, report, plan, receipt, current_assets=current)


def test_stale_receipt_plan_rejected():
    contract, report, plan, receipt = repair_fixture()
    with pytest.raises(ValueError, match="stale repair plan"):
        validate_receipt(contract, report, plan, change(receipt, plan_sha256="e" * 64),
                         current_assets=report.assets)


@pytest.mark.parametrize("field,value", [("asset_id", "unrelated"), ("revision", 1),
                                          ("sha256", "a" * 64), ("media_type", "audio")])
def test_invalid_replacement_rejected(field, value):
    contract, report, plan, receipt = repair_fixture()
    replacement = receipt.replacements[0]
    replacement = change(replacement, output=change(replacement.output, **{field: value}))
    with pytest.raises(ValueError):
        validate_receipt(contract, report, plan, change(receipt, replacements=(replacement,)),
                         current_assets=report.assets)


def test_unapproved_reference_repair_rejected():
    contract, report, plan, _ = repair_fixture()
    action = change(plan.actions[0], target_asset_id="approved-reference", expected_sha256="b" * 64)
    with pytest.raises(ValueError, match="approved reference"):
        validate_plan(contract, report, change(plan, actions=(action,)))


def test_default_repair_attempt_limit_enforced():
    _, _, plan, _ = repair_fixture()
    with pytest.raises(ValidationError):
        change(plan, max_attempts_per_target=100)


def test_trimmed_and_slowed_span_preserves_time_mapping():
    span = TimelineSpan(source_start_ms=2000, source_end_ms=6000, timeline_start_ms=10000,
                        speed_numerator=1, speed_denominator=2)
    assert span.to_timeline(4000) == 14000
    assert span.to_source(14000) == 4000
    assert span.to_timeline(6000) == 18000


def test_rational_speed_has_no_rounding_drift():
    span = TimelineSpan(source_start_ms=0, source_end_ms=1000, timeline_start_ms=0,
                        speed_numerator=3, speed_denominator=2)
    assert span.to_timeline(1) == Fraction(2, 3)
    assert span.to_source(span.to_timeline(997)) == 997


@pytest.mark.parametrize("field,value", [("speed_numerator", 0), ("speed_numerator", -1),
                                        ("speed_denominator", 0), ("source_end_ms", 100)])
def test_unsupported_or_invalid_transforms_rejected(field, value):
    data = dict(source_start_ms=100, source_end_ms=1000, timeline_start_ms=0)
    data[field] = value
    with pytest.raises(ValidationError):
        TimelineSpan(**data)


def test_seek_outside_trimmed_source_rejected():
    span = TimelineSpan(source_start_ms=100, source_end_ms=200, timeline_start_ms=1000)
    with pytest.raises(ValueError):
        span.to_timeline(99)
    with pytest.raises(ValueError):
        span.to_source(1101)


def test_staged_receipt_cannot_complete_live_repair():
    contract, report, plan, receipt = repair_fixture()
    report = change(report, run_mode="live")
    plan = change(plan, based_on_report_sha256=fingerprint(report))
    receipt = change(receipt, plan_sha256=fingerprint(plan))
    with pytest.raises(ValueError, match="staged receipt"):
        validate_receipt(contract, report, plan, receipt, current_assets=report.assets)
