import pytest
from pydantic import ValidationError

from proofframe_contracts.models import (
    Assertion, Contract, Coverage, Evidence, VerificationReport, CheckResult, fingerprint,
)
from proofframe_contracts.policy import evaluate, affected_assertions
from tests.factories import fixture, change


def rebound(contract, report):
    return change(report, contract_sha256=fingerprint(contract))


def test_eligible_is_not_permission_to_publish():
    contract, report = fixture()
    result = evaluate(contract, report)
    assert result.decision == "ELIGIBLE"
    assert result.publish_authorized is False
    assert result.run_mode == "synthetic_fixture"


def test_blocking_failure_blocks():
    contract, report = fixture("FAIL")
    assert evaluate(contract, report).decision == "BLOCK"


@pytest.mark.parametrize("status", ["UNCERTAIN", "NOT_CHECKED", "ERROR", "NOT_APPLICABLE"])
def test_unresolved_is_never_pass(status):
    contract, report = fixture(status)
    result = evaluate(contract, report)
    assert result.decision == "REVIEW"
    assert result.unresolved == ("wardrobe-01",)


def test_silent_omission_requires_review():
    contract, report = fixture()
    assert evaluate(contract, change(report, results=())).decision == "REVIEW"


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_evidence_required_for_conclusive_status(status):
    with pytest.raises(ValidationError):
        CheckResult(assertion_id="a", status=status, rationale="unproven", evaluator_version="v1")


def test_uncertain_can_have_no_evidence():
    contract, report = fixture("UNCERTAIN")
    report = change(report, results=(change(report.results[0], evidence_ids=()),), evidence=())
    assert evaluate(contract, report).decision == "REVIEW"


def test_approved_exclusion_is_recorded():
    contract, report = fixture("NOT_APPLICABLE")
    contract = change(contract, assertions=(change(contract.assertions[0], approved_exclusion="Approved offscreen shot"),))
    assert evaluate(contract, rebound(contract, report)).decision == "ELIGIBLE"


def test_exclusion_does_not_hide_actual_failure():
    contract, report = fixture("FAIL")
    contract = change(contract, assertions=(change(contract.assertions[0], approved_exclusion="Approved exception"),))
    assert evaluate(contract, rebound(contract, report)).decision == "BLOCK"


def test_advisory_finding_does_not_become_a_hard_block():
    contract, report = fixture("FAIL")
    contract = change(contract, assertions=(change(contract.assertions[0], blocking=False),))
    decision = evaluate(contract, rebound(contract, report))
    assert decision.decision == "ELIGIBLE"
    assert decision.advisory_findings == ("wardrobe-01",)


@pytest.mark.parametrize("field,value", [("asset_sha256", "f" * 64), ("asset_id", "unknown"), ("end_ms", 9000)])
def test_invalid_evidence_binding_rejected(field, value):
    contract, report = fixture()
    bad = change(report.evidence[0], **{field: value})
    with pytest.raises(ValueError):
        evaluate(contract, change(report, evidence=(bad,)))


def test_unknown_evidence_identifier_rejected():
    contract, report = fixture()
    report = change(report, evidence=())
    with pytest.raises(ValueError, match="dangling"):
        evaluate(contract, report)


def test_reference_alone_cannot_prove_rendered_output():
    contract, report = fixture()
    item = change(report.evidence[0], asset_id="approved-reference", asset_sha256="b" * 64,
                  kind="reference", inspection="artifact", start_ms=None, end_ms=None)
    with pytest.raises(ValueError, match="reference alone"):
        evaluate(contract, change(report, evidence=(item,)))


def test_replacing_canonical_reference_requires_new_approval():
    contract, report = fixture()
    report = change(report, assets=(report.assets[0], change(report.assets[1], sha256="e" * 64)))
    with pytest.raises(ValueError, match="canonical reference"):
        evaluate(contract, report)


def test_changing_approved_contract_invalidates_report():
    contract, report = fixture()
    with pytest.raises(ValueError, match="approved contract"):
        evaluate(change(contract, revision=2), report)


def test_new_render_can_use_same_approved_contract():
    contract, report = fixture()
    original_hash = fingerprint(contract)
    report = change(report, assets=(change(report.assets[0], revision=2, sha256="d" * 64), report.assets[1]),
                    evidence=(change(report.evidence[0], asset_sha256="d" * 64, artifact_sha256="e" * 64),))
    assert evaluate(contract, report).decision == "ELIGIBLE"
    assert fingerprint(contract) == original_hash


def test_missing_asset_binding_rejected():
    contract, report = fixture()
    with pytest.raises(ValueError, match="asset slots"):
        evaluate(contract, change(report, assets=(report.assets[0],)))


def test_unknown_schema_fields_rejected():
    contract, _ = fixture()
    with pytest.raises(ValidationError):
        change(contract, execute_shell="rm -rf /")


def test_duplicate_report_results_rejected():
    _, report = fixture()
    with pytest.raises(ValidationError):
        change(report, results=(report.results[0], report.results[0]))


def test_duplicate_evidence_references_rejected():
    _, report = fixture()
    with pytest.raises(ValidationError):
        change(report.results[0], evidence_ids=("frame-01", "frame-01"))


def test_unknown_dependency_rejected():
    contract, _ = fixture()
    with pytest.raises(ValidationError):
        change(contract, assertions=(change(contract.assertions[0], depends_on=("unknown",)),))


def test_cyclic_dependency_rejected():
    contract, _ = fixture()
    with pytest.raises(ValidationError):
        change(contract, assertions=(change(contract.assertions[0], depends_on=("wardrobe-01",)),))


def test_parent_failure_cannot_allow_dependent_pass():
    contract, report = fixture()
    parent = change(contract.assertions[0], assertion_id="parent")
    child = change(contract.assertions[0], depends_on=("parent",))
    contract = change(contract, assertions=(parent, child))
    parent_result = change(report.results[0], assertion_id="parent", status="UNCERTAIN")
    report = change(rebound(contract, report), results=(parent_result, report.results[0]))
    with pytest.raises(ValueError, match="prerequisites"):
        evaluate(contract, report)


def test_two_ids_of_same_artifact_do_not_count_twice():
    contract, report = fixture()
    check = change(contract.assertions[0], coverage=Coverage(minimum_items=2))
    contract = change(contract, assertions=(check,))
    repeated = change(report.evidence[0], evidence_id="another-id")
    report = change(rebound(contract, report), evidence=(report.evidence[0], repeated),
                    results=(change(report.results[0], evidence_ids=("frame-01", "another-id")),))
    with pytest.raises(ValueError, match="distinct"):
        evaluate(contract, report)


def test_metadata_is_not_a_visual_sample():
    contract, report = fixture()
    item = change(report.evidence[0], kind="metadata", inspection="artifact", start_ms=None, end_ms=None)
    with pytest.raises(ValueError, match="metadata"):
        evaluate(contract, change(report, evidence=(item,)))


def interval_case(intervals):
    contract, report = fixture()
    check = change(contract.assertions[0], coverage=Coverage(kind="interval_scan", start_ms=0, end_ms=8000))
    contract = change(contract, assertions=(check,))
    items = tuple(change(report.evidence[0], evidence_id=f"scan-{i}", kind="scan", inspection="exhaustive",
                         start_ms=lo, end_ms=hi, artifact_sha256=f"{i + 1:064x}")
                  for i, (lo, hi) in enumerate(intervals))
    report = change(rebound(contract, report), evidence=items,
                    results=(change(report.results[0], evidence_ids=tuple(e.evidence_id for e in items)),))
    return contract, report


def test_contiguous_scans_cover_required_interval():
    contract, report = interval_case([(0, 4000), (4000, 8000)])
    assert evaluate(contract, report).decision == "ELIGIBLE"


def test_scan_gap_does_not_pass():
    contract, report = interval_case([(0, 3900), (4000, 8000)])
    with pytest.raises(ValueError, match="gapped"):
        evaluate(contract, report)


def test_sparse_frame_cannot_be_promoted_to_full_interval():
    contract, report = fixture()
    contract = change(contract, assertions=(change(contract.assertions[0],
                      coverage=Coverage(kind="interval_scan", start_ms=0, end_ms=8000)),))
    with pytest.raises(ValueError, match="sparse"):
        evaluate(contract, rebound(contract, report))


def test_native_video_upload_is_not_an_exhaustive_scan():
    _, report = fixture()
    with pytest.raises(ValidationError):
        change(report.evidence[0], kind="clip", inspection="exhaustive")


def test_short_render_cannot_satisfy_longer_scan_requirement():
    contract, report = interval_case([(0, 8000)])
    contract = change(contract, assertions=(change(contract.assertions[0],
                      coverage=Coverage(kind="interval_scan", start_ms=0, end_ms=9000)),))
    with pytest.raises(ValueError, match="available media"):
        evaluate(contract, rebound(contract, report))


def test_transitive_dependencies_and_global_sentinels_retested():
    contract, _ = fixture()
    base = contract.assertions[0]
    dependent = change(base, assertion_id="later-scene", target_asset_id="approved-reference",
                       reference_asset_ids=(), depends_on=(base.assertion_id,))
    final = change(dependent, assertion_id="callback", depends_on=("later-scene",))
    sentinel = change(dependent, assertion_id="release-check", depends_on=(), global_sentinel=True)
    contract = change(contract, assertions=(base, dependent, final, sentinel))
    assert set(affected_assertions(contract, {"shot-01"})) == {
        "wardrobe-01", "later-scene", "callback", "release-check"}


def test_unknown_changed_asset_rejected():
    contract, _ = fixture()
    with pytest.raises(ValueError):
        affected_assertions(contract, {"nonexistent"})
