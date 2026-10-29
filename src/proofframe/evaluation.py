"""Offline diagnostics; these scores alone do not qualify model quality.

Labels: defects [{id, class, t: [start_s,end_s], accept_categories, keywords?}].
Optional fully_annotated=true asserts all unmatched findings are false positives.
Otherwise adjudications maps finding id (fallback assertion_id:index) to
false_positive, true_positive (human-confirmed label gap), or uncertain.
Adjudications constrain matching even when a finding overlaps a label.
Every member of a duplicate root needs consistent adjudication. Unresolved
roots withhold precision and TP/FP/FN. Recall covers supplied labels only;
adjudicated label gaps add precision positives, never labelled recall.
Reference-shot spans are validated but cannot localize a defect event.
Duplicate roots require the same category/entity, overlapping spans and either
the same explicit root_cause_id or identical normalized descriptions. Similar
phrasing alone cannot establish a shared root cause.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

EVALUATOR_VERSION = "1.1"


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("times must be finite numbers")
    return float(value)


def _span(values: Any) -> tuple[float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise ValueError("span needs two boundaries")
    start, end = map(_number, values)
    if start < 0 or end <= start:
        raise ValueError("span must be nonnegative and strictly increasing")
    return start, end


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _identity(finding: dict) -> tuple:
    entity = str(finding.get("entity") or "").strip().casefold()
    description = " ".join(str(finding.get("description", "")).casefold().split())
    root_id = finding.get("root_cause_id")
    if root_id is not None and (not isinstance(root_id, str) or not root_id.strip()):
        raise ValueError("root_cause_id must be a nonempty string")
    return finding["category"], entity, "root" if root_id is not None else "description", root_id or description


def _roots(report: dict) -> tuple[list[list[dict]], dict]:
    roots: list[list[dict]] = []
    verdicts, ids = Counter(), set()
    for check in report["checks"]:
        for index, raw in enumerate(check.get("findings") or []):
            finding = dict(raw)
            finding["span"] = tuple(v / 1000 for v in _span([raw["start_ms"], raw["end_ms"]]))
            if "ref_start_ms" in raw or "ref_end_ms" in raw:
                _span([raw.get("ref_start_ms"), raw.get("ref_end_ms")])
            verdict = raw["verdict"]
            if verdict not in {"confirmed", "review", "unclear", "rejected", "error"}:
                raise ValueError(f"unknown finding verdict: {verdict}")
            verdicts[verdict] += 1
            finding["evaluation_id"] = str(raw.get("id", f'{check["assertion_id"]}:{index}'))
            if finding["evaluation_id"] in ids:
                raise ValueError("finding IDs must be unique")
            ids.add(finding["evaluation_id"])
            if verdict not in {"confirmed", "review", "unclear"}:
                continue
            identity = _identity(finding)
            # Require pairwise overlap: chained duplicates cannot bridge two events.
            group = next((g for g in roots if identity[-1] and all(
                _identity(member) == identity and _overlap(member["span"], finding["span"])
                for member in g)), None)
            if group is None:
                roots.append([finding])
            else:
                group.append(finding)
    return roots, dict(verdicts)


def _root_adjudication(root: list[dict], adjudications: dict) -> str | None:
    decisions = [adjudications.get(f["evaluation_id"]) for f in root]
    if not any(decisions):
        return None
    # Partial or conflicting decisions cannot certify the whole root.
    return decisions[0] if len(set(decisions)) == 1 else "uncertain"


def _matches(finding: dict, label: dict, tolerance: float) -> bool:
    text = f'{finding.get("entity", "")} {finding.get("description", "")}'.casefold()
    start, end = label["t"]
    return (finding["category"] in label["accept_categories"]
            and _overlap(finding["span"], (start - tolerance, end + tolerance))
            and (not label.get("keywords") or any(k.casefold() in text for k in label["keywords"])))


def _maximum_matching(edges: list[list[int]]) -> dict[int, int]:
    owners: dict[int, int] = {}

    def augment(root: int, seen: set[int]) -> bool:
        for label in edges[root]:
            if label in seen:
                continue
            seen.add(label)
            if label not in owners or augment(owners[label], seen):
                owners[label] = root
                return True
        return False

    for root in range(len(edges)):
        augment(root, set())
    return {root: label for label, root in owners.items()}


def score_findings(report: dict, labels: dict, *, tolerance_s: float = 1.0) -> dict:
    """Independently match confirmed-only and surfaced confirmed/review/unclear."""
    tolerance = _number(tolerance_s)
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    defects = [dict(label, t=_span(label["t"])) for label in labels["defects"]]
    if len({label["id"] for label in defects}) != len(defects):
        raise ValueError("label IDs must be unique")
    if "fully_annotated" in labels and not isinstance(labels["fully_annotated"], bool):
        raise ValueError("fully_annotated must be a boolean")
    adjudications = labels.get("adjudications", {})
    if any(v not in {"false_positive", "true_positive", "uncertain"} for v in adjudications.values()):
        raise ValueError("unknown adjudication")
    roots, verdicts = _roots(report)
    known_ids = {f["evaluation_id"] for root in roots for f in root}
    if set(adjudications) - known_ids:
        raise ValueError("adjudication refers to an unknown or excluded finding")
    result = {"scope": "development diagnostic; recall covers supplied labels only",
              "evaluator_version": EVALUATOR_VERSION, "tolerance_s": tolerance,
              "assumptions": {"fully_annotated": labels.get("fully_annotated", False),
                              "adjudications": dict(adjudications),
                              "adjudications_constrain_matching": True,
                              "deduplication": "same category/entity and pairwise-overlapping spans; explicit root_cause_id or exact normalized description",
                              "reference_spans_match_events": False,
                              "surfaced_verdicts": ["confirmed", "review", "unclear"]},
              "labels": len(defects), "raw_verdict_counts": verdicts,
              "root_causes": len(roots), "duplicates_removed": sum(map(len, roots)) - len(roots)}
    for track in ("confirmed", "surfaced"):
        track_roots = [([f for f in root if track == "surfaced" or f["verdict"] == "confirmed"],
                        _root_adjudication(root, adjudications)) for root in roots]
        track_roots = [(root, decision) for root, decision in track_roots if root]
        active = [root for root, _ in track_roots]
        edges = [[i for i, label in enumerate(defects) if any(_matches(f, label, tolerance) for f in root)]
                 if decision in {None, "true_positive"} else [] for root, decision in track_roots]
        matching = _maximum_matching(edges)
        unmatched = [i for i in range(len(active)) if i not in matching]
        outcomes = {}
        for i in unmatched:
            decision = track_roots[i][1]
            if decision is not None:
                outcomes[i] = decision
            elif labels.get("fully_annotated", False):
                outcomes[i] = "false_positive"
            else:
                outcomes[i] = "uncertain"
        unresolved = sum(v == "uncertain" for v in outcomes.values())
        extra_tp = sum(v == "true_positive" for v in outcomes.values())
        fp = sum(v == "false_positive" for v in outcomes.values())
        tp = len(matching) + extra_tp
        by_class = {}
        for cls in sorted({label["class"] for label in defects}):
            class_ids = {i for i, label in enumerate(defects) if label["class"] == cls}
            matched = len(class_ids & set(matching.values()))
            by_class[cls] = {"labels": len(class_ids), "matched_labels": matched,
                             "missed_labels": len(class_ids) - matched, "recall": matched / len(class_ids)}
        result[track] = {
            "findings": len(active), "matched_labels": len(matching),
            "missed_labels": len(defects) - len(matching),
            "recall": len(matching) / len(defects) if defects else None,
            "tp": tp if not unresolved else None, "fp": fp if not unresolved else None,
            "fn": len(defects) - len(matching) if not unresolved else None,
            "precision": tp / (tp + fp) if not unresolved and tp + fp else None,
            "unmatched_findings": len(unmatched), "unresolved_findings": unresolved,
            "adjudicated_label_gaps": extra_tp, "adjudicated_false_positives": fp,
            "matches": [{"finding_ids": [f["evaluation_id"] for f in active[i]],
                         "label_id": defects[j]["id"]} for i, j in sorted(matching.items())],
            "unmatched": [{"finding_ids": [f["evaluation_id"] for f in active[i]],
                           "adjudication": outcomes[i]} for i in unmatched],
            "per_class": by_class,
        }
    return result


def analyze_judge_controls(order_records: list[dict], identical_records: list[dict]) -> dict:
    """Analyze offline pair_id/order/verdict records; never call a provider.

    order is AB or BA; verdict is same/different/abstain/error. Pair IDs must
    bind the same evidence, prompt, model and settings (caller responsibility).
    Identical controls need pair_id/verdict. Abstention/error pairs can overlap;
    rates use decisive trials only and report all excluded denominators.
    """
    valid = {"same", "different", "abstain", "error"}
    pairs: dict[str, dict[str, str]] = {}
    for record in order_records:
        pair = pairs.setdefault(record["pair_id"], {})
        order, verdict = record["order"], record["verdict"]
        if order not in {"AB", "BA"} or verdict not in valid or order in pair:
            raise ValueError("invalid or duplicate order control")
        pair[order] = verdict
    if any(r["verdict"] not in valid for r in identical_records):
        raise ValueError("invalid identical control verdict")
    if len({r["pair_id"] for r in identical_records}) != len(identical_records):
        raise ValueError("duplicate identical control")
    complete = [p for p in pairs.values() if set(p) == {"AB", "BA"}]
    decisive = [p for p in complete if all(v in {"same", "different"} for v in p.values())]
    disagreement = sum(p["AB"] != p["BA"] for p in decisive)
    identical = Counter(r["verdict"] for r in identical_records)
    denominator = identical["same"] + identical["different"]
    return {
        "order": {"pairs": len(pairs), "record_verdict_counts": dict(Counter(r["verdict"] for r in order_records)),
                  "complete_pairs": len(complete),
                  "incomplete_pairs": len(pairs) - len(complete), "decisive_pairs": len(decisive),
                  "abstention_pairs": sum("abstain" in p.values() for p in complete),
                  "error_pairs": sum("error" in p.values() for p in complete),
                  "disagreements": disagreement,
                  "disagreement_rate": disagreement / len(decisive) if decisive else None},
        "identical": {"trials": len(identical_records), "decisive_trials": denominator,
                      "abstentions": identical["abstain"], "errors": identical["error"],
                      "false_differences": identical["different"],
                      "false_difference_rate": identical["different"] / denominator if denominator else None},
    }
