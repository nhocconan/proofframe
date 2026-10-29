"""Synthetic scorer/control behavior tests; not a perception benchmark."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from proofframe.evaluation import analyze_judge_controls, score_findings


def finding(start=1000, end=2000, **kwargs):
    return {"category": "wardrobe", "verdict": "confirmed", "start_ms": start,
            "end_ms": end, "entity": "alice", "description": "wrong shirt", **kwargs}


def report(*findings):
    return {"checks": [{"assertion_id": "audit", "findings": list(findings)}]}


def label(id="a", t=(1, 2), **kwargs):
    return {"id": id, "class": "must_catch", "t": list(t),
            "accept_categories": ["wardrobe"], **kwargs}


def score(findings, defects, **metadata):
    return score_findings(report(*findings), {"defects": defects, **metadata}, tolerance_s=0)


def test_duplicate_root_cannot_inflate_true_positives():
    result = score([finding(), finding(description=" WRONG  SHIRT ")], [label(), label("b")])
    assert result["duplicates_removed"] == 1
    assert result["confirmed"]["matched_labels"] == 1
    assert result["confirmed"]["fn"] == 1


def test_true_shirt_and_false_hat_same_entity_do_not_hide_false_positive():
    result = score([finding(), finding(description="wrong hat")],
                   [label(keywords=["shirt"])], fully_annotated=True)
    assert result["root_causes"] == 2 and result["duplicates_removed"] == 0
    for track in ("confirmed", "surfaced"):
        assert (result[track]["tp"], result[track]["fp"], result[track]["precision"]) == (1, 1, 0.5)


def test_independent_same_entity_defects_can_match_two_labels():
    result = score([finding(), finding(description="wrong hat")],
                   [label(keywords=["shirt"]), label("b", keywords=["hat"])])
    assert result["confirmed"]["matched_labels"] == 2


def test_paraphrases_need_explicit_shared_root_cause_id_to_merge():
    assert score([finding(), finding(description="shirt has changed")], [])["root_causes"] == 2
    result = score([finding(root_cause_id="shirt-1"),
                    finding(root_cause_id="shirt-1", description="shirt has changed")], [])
    assert result["root_causes"] == 1


def test_same_root_id_requires_same_entity_category_and_overlapping_interval():
    result = score([finding(root_cause_id="shared"),
                    finding(root_cause_id="shared", entity="bob"),
                    finding(root_cause_id="shared", category="prop"),
                    finding(3000, 4000, root_cause_id="shared")], [])
    assert result["root_causes"] == 4


def test_overlapping_human_false_positive_cannot_match_label():
    result = score([finding()], [label()], adjudications={"audit:0": "false_positive"})
    for track in ("confirmed", "surfaced"):
        assert (result[track]["tp"], result[track]["fp"], result[track]["fn"]) == (0, 1, 1)
        assert result[track]["recall"] == result[track]["precision"] == 0


@pytest.mark.parametrize("fully_annotated", [False, True])
def test_overlapping_uncertain_adjudication_blocks_match_and_precision(fully_annotated):
    result = score([finding()], [label()], fully_annotated=fully_annotated,
                   adjudications={"audit:0": "uncertain"})
    for track in ("confirmed", "surfaced"):
        assert result[track]["matched_labels"] == 0
        assert result[track]["unresolved_findings"] == 1
        assert all(result[track][key] is None for key in ("tp", "fp", "fn", "precision"))


def test_partial_or_conflicting_duplicate_adjudication_blocks_overlapping_match():
    for decisions in ({"audit:0": "false_positive"},
                      {"audit:0": "false_positive", "audit:1": "true_positive"}):
        metrics = score([finding(), finding()], [label()], adjudications=decisions)["confirmed"]
        assert metrics["matched_labels"] == 0
        assert metrics["precision"] is None and metrics["unresolved_findings"] == 1


def test_duplicate_review_adjudication_cannot_disappear_from_confirmed_track():
    result = score([finding(), finding(verdict="review")], [label()],
                   adjudications={"audit:1": "uncertain"})
    assert result["confirmed"]["precision"] is None
    assert result["confirmed"]["matched_labels"] == 0


def test_human_true_positive_can_match_an_existing_label():
    metrics = score([finding()], [label()], adjudications={"audit:0": "true_positive"})["confirmed"]
    assert metrics["tp"] == metrics["precision"] == metrics["recall"] == 1
    assert metrics["adjudicated_label_gaps"] == 0


def test_one_finding_can_match_only_one_label():
    metrics = score([finding()], [label(), label("b")])["surfaced"]
    assert (metrics["tp"], metrics["fn"], metrics["precision"]) == (1, 1, 1)


def test_maximum_matching_reassigns_first_flexible_finding():
    result = score([finding(description="coat scarf", entity="alice"),
                    finding(description="coat", entity="bob")],
                   [label(keywords=["coat"]), label("b", keywords=["scarf"])])
    assert result["confirmed"]["matched_labels"] == 2
    assert {m["label_id"]: m["finding_ids"] for m in result["confirmed"]["matches"]} == {
        "a": ["audit:1"], "b": ["audit:0"]}


def test_confirmed_and_surfaced_are_independent_maximum_matchings():
    result = score([finding(description="coat scarf", entity="alice"),
                    finding(description="coat", entity="bob", verdict="review")],
                   [label(keywords=["coat"]), label("b", keywords=["scarf"])])
    assert result["confirmed"]["matched_labels"] == 1
    assert result["surfaced"]["matched_labels"] == 2


def test_unanswered_adjudication_withholds_precision_and_confusion_counts():
    metrics = score([finding(6000, 7000)], [label()])["confirmed"]
    assert metrics["unmatched_findings"] == metrics["unresolved_findings"] == 1
    assert metrics["matched_labels"] == 0 and metrics["missed_labels"] == 1
    assert all(metrics[key] is None for key in ("precision", "tp", "fp", "fn"))


@pytest.mark.parametrize("metadata", [{"fully_annotated": True},
                                      {"adjudications": {"audit:0": "false_positive"}}])
def test_explicit_negative_adjudication_allows_false_positive_counts(metadata):
    metrics = score([finding(6000, 7000)], [label()], **metadata)["confirmed"]
    assert (metrics["tp"], metrics["fp"], metrics["fn"], metrics["precision"]) == (0, 1, 1, 0)


def test_human_confirmed_label_gap_does_not_inflate_label_recall():
    metrics = score([finding(6000, 7000)], [label()],
                    adjudications={"audit:0": "true_positive"})["confirmed"]
    assert metrics["tp"] == 1 and metrics["adjudicated_label_gaps"] == 1
    assert metrics["recall"] == 0 and metrics["precision"] == 1


def test_uncertain_adjudication_remains_unknown_even_if_fully_annotated():
    metrics = score([finding(6000, 7000)], [label()], fully_annotated=True,
                    adjudications={"audit:0": "uncertain"})["confirmed"]
    assert metrics["precision"] is None


def test_partial_duplicate_adjudication_cannot_silently_resolve_root():
    metrics = score([finding(6000, 7000), finding(6000, 7000)], [label()],
                    adjudications={"audit:0": "false_positive"})["confirmed"]
    assert metrics["unresolved_findings"] == 1


def test_reference_context_cannot_catch_wrong_event_interval():
    metrics = score([finding(6000, 7000, ref_start_ms=1000, ref_end_ms=2000)], [label()])["confirmed"]
    assert metrics["matched_labels"] == 0


@pytest.mark.parametrize("span", [(2, 1), (1, 1), (-1, 1), (float("nan"), 2),
                                  (1, float("inf")), (True, 2)])
def test_invalid_label_span_rejected(span):
    with pytest.raises(ValueError):
        score([], [label(t=span)])


@pytest.mark.parametrize("start,end", [(2000, 1000), (1000, 1000), (-1, 1000),
                                       (float("nan"), 2000), (1000, float("inf"))])
def test_invalid_finding_span_rejected(start, end):
    with pytest.raises(ValueError):
        score([finding(start, end)], [])


def test_invalid_reference_span_rejected_even_when_not_used_for_matching():
    with pytest.raises(ValueError):
        score([finding(ref_start_ms=1000)], [])


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf")])
def test_invalid_tolerance_rejected(tolerance):
    with pytest.raises(ValueError):
        score_findings(report(), {"defects": []}, tolerance_s=tolerance)


def test_per_class_counts_and_category_and_keyword_constraints():
    result = score([finding(), finding(4000, 5000, category="prop", entity="bob")],
                   [label(), label("b", (4, 5), **{"class": "advisory", "keywords": ["bob"]}),
                    label("c", (1, 2), keywords=["carol"])])["confirmed"]
    assert result["per_class"]["must_catch"]["matched_labels"] == 1
    assert result["per_class"]["must_catch"]["missed_labels"] == 1
    assert result["per_class"]["advisory"]["matched_labels"] == 0


def test_dedup_requires_overlap_and_preserves_distinct_entities():
    result = score([finding(), finding(3000, 4000), finding(entity="bob")], [])
    assert result["root_causes"] == 3


def test_duplicate_bridge_does_not_merge_nonoverlapping_events():
    result = score([finding(1000, 3000), finding(2000, 5000), finding(4000, 6000)], [])
    assert result["root_causes"] == 2


def test_missing_entity_only_deduplicates_exact_normalized_description():
    result = score([finding(entity=None), finding(entity=None, description=" WRONG  SHIRT "),
                    finding(entity=None, description="wrong hat")], [])
    assert result["root_causes"] == 2


def test_rejected_and_error_findings_are_not_detections():
    result = score([finding(verdict="rejected"), finding(verdict="error")], [label()])
    assert result["surfaced"]["matched_labels"] == 0
    assert result["raw_verdict_counts"] == {"rejected": 1, "error": 1}


def test_judge_controls_separate_decisive_abstention_error_and_missing():
    orders = [{"pair_id": id, "order": order, "verdict": verdict}
              for id, ab, ba in [("a", "same", "different"), ("b", "same", "same"),
                                ("c", "abstain", "different"), ("d", "error", "same")]
              for order, verdict in [("AB", ab), ("BA", ba)]]
    orders.append({"pair_id": "missing", "order": "AB", "verdict": "abstain"})
    identical = [{"pair_id": str(i), "verdict": v}
                 for i, v in enumerate(["different", "same", "abstain", "error"])]
    result = analyze_judge_controls(orders, identical)
    assert result["order"]["disagreement_rate"] == 0.5
    assert result["order"]["decisive_pairs"] == 2
    assert result["order"]["incomplete_pairs"] == 1
    assert result["order"]["abstention_pairs"] == result["order"]["error_pairs"] == 1
    assert result["order"]["record_verdict_counts"]["abstain"] == 2
    assert result["identical"] == {"trials": 4, "decisive_trials": 2, "abstentions": 1,
                                   "errors": 1, "false_differences": 1, "false_difference_rate": 0.5}


def test_judge_controls_without_decisions_have_unknown_rates():
    result = analyze_judge_controls([], [{"pair_id": "a", "verdict": "abstain"}])
    assert result["order"]["disagreement_rate"] is None
    assert result["identical"]["false_difference_rate"] is None


def test_duplicate_judge_controls_rejected():
    record = {"pair_id": "a", "order": "AB", "verdict": "same"}
    with pytest.raises(ValueError):
        analyze_judge_controls([record, record], [])


def test_cli_machine_output_binds_exact_inputs_and_controls(tmp_path):
    report_path, label_path, controls_path = [tmp_path / name for name in ("report.json", "labels.json", "controls.json")]
    report_path.write_text(json.dumps(report(finding())), encoding="utf-8")
    label_path.write_text(json.dumps({"defects": [label()], "fully_annotated": True}), encoding="utf-8")
    controls_path.write_text('{"order_records": [], "identical_records": []}', encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_findings.py"
    completed = subprocess.run([sys.executable, str(script), str(report_path), str(label_path),
                                "--tolerance-s", "0", "--json", "--controls", str(controls_path)],
                               check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["confirmed"]["tp"] == 1
    assert result["tolerance_s"] == 0 and result["evaluator_version"]
    assert result["assumptions"]["fully_annotated"] is True
    assert result["input_hashes"]["labels_sha256"] == hashlib.sha256(label_path.read_bytes()).hexdigest()
    assert result["input_hashes"]["report_sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert "judge_controls" in result
