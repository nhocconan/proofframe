"""Offline frozen-cohort comparison; no provider execution or qualification verdict.

Manifest JSON (schema_version=1): baselines is a nonempty list of unique names;
cases is a nonempty list of objects with case_id, source_group, split
(development|calibration|holdout), media_path, media_sha256, target_asset_id,
contract_sha256, annotation_provenance (human_adjudicated|agent_draft|synthetic),
labels={path,sha256}, reports={baseline_name:{path,sha256}}. Every case must
include exactly the declared baselines. Paths are relative to the manifest's
directory, must remain inside it after resolving symlinks, and name local files.
SHA-256 values are lowercase hex. The emitted manifest hash covers exact bytes.
Labels use evaluation.score_findings' format. Multi-baseline adjudications use
adjudications_by_baseline={baseline:{finding_id:decision}}; shared nonempty
adjudications are rejected for multiple baselines. Shared and scoped keys cannot
coexist. Missing scoped baseline maps provide no adjudications. Reports are pipeline envelopes
with run.contract_sha256, assets[{asset_id,sha256}], checks[{target_asset_id,...}].
Optional report.contract_sha256 must agree too. Costs use envelope cost fields
estimated_usd and unknown_cost_calls; absent costs remain unknown. Optional
owner_review_minutes is measured human time; absence is not zero.

All cases and files are validated before split selection. Group/hash separation
and frozen bytes do not establish that a holdout was locked before tuning.
Human provenance is a declaration, not independently verified adjudication.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from proofframe.evaluation import EVALUATOR_VERSION, score_findings

SCHEMA_VERSION = "proofframe.dataset_evaluation.v1"
SPLITS = {"development", "calibration", "holdout"}
PROVENANCE = {"human_adjudicated", "agent_draft", "synthetic"}


def _json(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"nonfinite JSON: {value}")))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SHA-256 must be 64 lowercase hex characters")
    return value


def _local_path(root: Path, path: Any) -> Path:
    path = _text(path, "path")
    relative = Path(path)
    if relative.is_absolute() or ":" in path or "\\" in path:
        raise ValueError("paths must be local and relative to the manifest directory")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("path escapes manifest directory")
    return resolved


def _read(root: Path, path: Any, sha: Any) -> bytes:
    raw = _local_path(root, path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != _hash(sha):
        raise ValueError(f"SHA-256 mismatch: {path}")
    return raw


def _verify_media(root: Path, path: Any, sha: Any) -> None:
    expected = _hash(sha)
    with _local_path(root, path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")


def _amount(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("cost/review amounts must be finite nonnegative numbers")
    return float(value)


def _resources(report: dict) -> dict:
    cost = report.get("cost")
    if cost is not None and not isinstance(cost, dict):
        raise ValueError("cost must be an object")
    cost = cost or {}
    known = cost.get("estimated_usd")
    if known is not None:
        known = _amount(known)
    unknown = cost.get("unknown_cost_calls")
    if unknown is not None and (type(unknown) is not int or unknown < 0):
        raise ValueError("unknown_cost_calls must be a nonnegative integer")
    review = report.get("owner_review_minutes")
    return {"known_estimated_usd": known, "unknown_cost_calls": unknown,
            "cost_complete": known is not None and unknown == 0,
            "owner_review_minutes": _amount(review) if review is not None else None}


def _binding(report: dict, case: dict) -> None:
    if report["run"]["contract_sha256"] != case["contract_sha256"]:
        raise ValueError("report contract binding mismatch")
    if "report" in report and report["report"]["contract_sha256"] != case["contract_sha256"]:
        raise ValueError("nested report contract binding mismatch")
    assets = report["assets"]
    if not isinstance(assets, list) or len({a["asset_id"] for a in assets}) != len(assets):
        raise ValueError("report assets must have unique asset IDs")
    target = next((a for a in assets if a["asset_id"] == case["target_asset_id"]), None)
    if target is None or target["sha256"] != case["media_sha256"]:
        raise ValueError("report asset binding mismatch")
    if not isinstance(report["checks"], list):
        raise ValueError("report checks must be a list")
    if any(c["target_asset_id"] != case["target_asset_id"] for c in report["checks"]):
        raise ValueError("report check target asset binding mismatch")


def _baseline_labels(labels: dict, baselines: list[str], baseline: str) -> dict:
    scoped = labels.get("adjudications_by_baseline")
    if "adjudications_by_baseline" in labels:
        if "adjudications" in labels:
            raise ValueError("shared and baseline-scoped adjudications cannot coexist")
        if not isinstance(scoped, dict) or set(scoped) - set(baselines):
            raise ValueError("adjudications_by_baseline must map known baseline names")
        if any(not isinstance(decisions, dict) for decisions in scoped.values()):
            raise ValueError("baseline adjudications must be objects")
    shared = labels.get("adjudications", {})
    if not isinstance(shared, dict):
        raise ValueError("adjudications must be an object")
    if len(baselines) > 1 and shared:
        raise ValueError("shared adjudications are ambiguous for multiple baselines")
    selected = dict(labels)
    selected.pop("adjudications_by_baseline", None)
    selected["adjudications"] = scoped.get(baseline, {}) if scoped is not None else shared
    return selected


def _aggregate(rows: list[dict]) -> dict:
    result = {"cases": len(rows), "labels": sum(r["score"]["labels"] for r in rows)}
    result["raw_verdict_counts"] = dict(sum((Counter(r["score"]["raw_verdict_counts"]) for r in rows), Counter()))
    for track in ("confirmed", "surfaced"):
        metrics = [row["score"][track] for row in rows]
        counts = {key: sum(m[key] for m in metrics) for key in (
            "findings", "matched_labels", "missed_labels", "unmatched_findings",
            "unresolved_findings", "adjudicated_label_gaps", "adjudicated_false_positives")}
        counts["recall"] = counts["matched_labels"] / result["labels"] if result["labels"] else None
        resolved = not counts["unresolved_findings"]
        for key in ("tp", "fp", "fn"):
            counts[key] = sum(m[key] for m in metrics) if resolved else None
        counts["precision"] = (counts["tp"] / (counts["tp"] + counts["fp"])
                               if resolved and counts["tp"] + counts["fp"] else None)
        result[track] = counts
    resources = [r["resources"] for r in rows]
    unknown_reports = sum(r["unknown_cost_calls"] is None or r["known_estimated_usd"] is None for r in resources)
    known_cost = sum(r["known_estimated_usd"] for r in resources if r["known_estimated_usd"] is not None)
    review_missing = sum(r["owner_review_minutes"] is None for r in resources)
    review_known = sum(r["owner_review_minutes"] for r in resources if r["owner_review_minutes"] is not None)
    result["resources"] = {
        "known_estimated_usd": known_cost,
        "estimated_total_usd": known_cost if all(r["cost_complete"] for r in resources) else None,
        "unknown_cost_calls": sum(r["unknown_cost_calls"] or 0 for r in resources) if not unknown_reports else None,
        "reported_unknown_cost_calls": sum(r["unknown_cost_calls"] or 0 for r in resources),
        "unknown_cost_reports": unknown_reports,
        "review_not_measured_cases": review_missing,
        "known_owner_review_minutes": review_known,
        "owner_review_minutes": review_known if not review_missing else None,
        "cost_basis": "report estimates; not independently verified invoices or end-to-end completeness"}
    return result


def evaluate_dataset(manifest_path: str | Path, *, split: str = "holdout") -> dict:
    """Validate the complete manifest, then compare every baseline on one split."""
    if split not in SPLITS:
        raise ValueError("unknown split")
    path = Path(manifest_path).resolve()
    raw = path.read_bytes()
    manifest = _json(raw)
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("manifest schema_version must be 1")
    baselines = manifest["baselines"]
    if not isinstance(baselines, list) or not baselines:
        raise ValueError("baselines must be a nonempty list")
    for name in baselines:
        _text(name, "baseline")
    if len(set(baselines)) != len(baselines):
        raise ValueError("duplicate baseline")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    ids, groups, media_splits = set(), {}, {}
    selected = {name: [] for name in baselines}
    provenance = Counter()
    holdout_provenance = Counter()
    for case in cases:
        cid = _text(case["case_id"], "case_id")
        if cid in ids:
            raise ValueError(f"duplicate case ID: {cid}")
        ids.add(cid)
        source = _text(case["source_group"], "source_group")
        case_split = case["split"]
        if case_split not in SPLITS:
            raise ValueError("unknown case split")
        media_sha = _hash(case["media_sha256"])
        _hash(case["contract_sha256"])
        _text(case["target_asset_id"], "target_asset_id")
        for mapping, key in ((groups, source), (media_splits, media_sha)):
            if key in mapping and mapping[key] != case_split:
                raise ValueError("cross-split source_group or media hash leakage")
            mapping[key] = case_split
        origin = case["annotation_provenance"]
        if origin not in PROVENANCE:
            raise ValueError("unknown annotation provenance")
        if case_split == "holdout":
            holdout_provenance[origin] += 1
        reports = case["reports"]
        if not isinstance(reports, dict) or set(reports) != set(baselines):
            raise ValueError("unequal baseline cohort: every case needs every declared baseline")
        _verify_media(path.parent, case["media_path"], media_sha)
        labels = _json(_read(path.parent, case["labels"]["path"], case["labels"]["sha256"]))
        for name in baselines:
            ref = reports[name]
            report = _json(_read(path.parent, ref["path"], ref["sha256"]))
            _binding(report, case)
            score = score_findings(report, _baseline_labels(labels, baselines, name))
            resources = _resources(report)
            if case_split == split:
                selected[name].append({"case_id": cid, "source_group": source,
                                       "target_asset_id": case["target_asset_id"],
                                       "contract_sha256": case["contract_sha256"],
                                       "media_sha256": media_sha, "labels_sha256": case["labels"]["sha256"],
                                       "report_sha256": ref["sha256"], "annotation_provenance": origin,
                                       "score": score, "resources": resources})
        if case_split == split:
            provenance[origin] += 1
    cohort = [r["case_id"] for r in selected[baselines[0]]]
    if not cohort:
        raise ValueError(f"no cases in requested split: {split}")
    return {"schema_version": SCHEMA_VERSION, "evaluator_version": EVALUATOR_VERSION,
            "manifest_sha256": hashlib.sha256(raw).hexdigest(), "split": split,
            "model_qualification_established": False,
            "cohort_case_ids": cohort, "case_count": len(cohort),
            "source_group_count": len({r["source_group"] for r in selected[baselines[0]]}),
            "annotation_provenance_counts": dict(provenance),
            "human_adjudicated_holdout_cases": holdout_provenance["human_adjudicated"],
            "human_adjudicated_holdout_available": bool(holdout_provenance["human_adjudicated"]),
            "all_selected_labels_human_adjudicated": provenance["human_adjudicated"] == len(cohort),
            "scope": "offline frozen-cohort diagnostic; no model qualification or universal SOTA verdict",
            "limitations": ["Sample counts describe this cohort only; no production generalization or statistical sufficiency established.",
                            "Source grouping and frozen labels do not prove absence of previous tuning or contamination.",
                            "Annotation provenance is manifest-declared; agent drafts and synthetic labels are not human ground truth.",
                            "Recall covers supplied labels only; unresolved findings withhold precision and confusion counts.",
                            "Resources are report-declared; unmeasured review and missing cost are unknown."],
            "baselines": {name: {"per_case": rows, "aggregate": _aggregate(rows)} for name, rows in selected.items()}}
