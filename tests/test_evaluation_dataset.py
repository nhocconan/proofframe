"""Deterministic synthetic cohort tests, not a perception benchmark."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from proofframe.evaluation_dataset import evaluate_dataset


CONTRACT = "a" * 64


def write_json(root, name, value):
    path = root / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def make_dataset(root, *, fully_annotated=True, provenance="synthetic"):
    cases = []
    for index in range(2):
        media = f"synthetic-media-{index}".encode()
        media_path = root / f"media-{index}.bin"
        media_path.write_bytes(media)
        sha = hashlib.sha256(media).hexdigest()
        labels = {"defects": [{"id": "shirt", "class": "must_catch", "t": [1, 2],
                                "accept_categories": ["wardrobe"]}],
                  "fully_annotated": fully_annotated}
        case = {"case_id": f"case-{index}", "source_group": f"source-{index}", "split": "holdout",
                "media_path": media_path.name, "media_sha256": sha, "target_asset_id": "shot",
                "contract_sha256": CONTRACT, "annotation_provenance": provenance,
                "labels": write_json(root, f"labels-{index}.json", labels), "reports": {}}
        for baseline in ("B1", "B2"):
            finding = {"id": "f", "category": "wardrobe", "verdict": "review" if baseline == "B1" else "confirmed",
                       "start_ms": 1000, "end_ms": 2000, "description": "wrong shirt", "entity": "alice"}
            report = {"run": {"contract_sha256": CONTRACT}, "report": {"contract_sha256": CONTRACT},
                      "assets": [{"asset_id": "shot", "sha256": sha}],
                      "checks": [{"assertion_id": "shirt", "target_asset_id": "shot", "findings": [finding]}],
                      "cost": {"estimated_usd": 0.1, "unknown_cost_calls": 0}, "owner_review_minutes": 2}
            case["reports"][baseline] = write_json(root, f"{baseline}-{index}.json", report)
        cases.append(case)
    manifest = {"schema_version": 1, "baselines": ["B1", "B2"], "cases": cases}
    path = root / "manifest.json"
    save_manifest(path, manifest)
    return path, manifest


def save_manifest(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")


def mutate_report(root, case, baseline, change):
    ref = case["reports"][baseline]
    report = json.loads((root / ref["path"]).read_bytes())
    change(report)
    case["reports"][baseline] = write_json(root, ref["path"], report)


def test_positive_comparison_keeps_tracks_cohort_resources_and_provenance(tmp_path):
    path, manifest = make_dataset(tmp_path, provenance="human_adjudicated")
    result = evaluate_dataset(path)
    assert result["schema_version"] == "proofframe.dataset_evaluation.v1"
    assert result["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["cohort_case_ids"] == ["case-0", "case-1"]
    assert result["annotation_provenance_counts"] == {"human_adjudicated": 2}
    assert result["human_adjudicated_holdout_available"] is True
    assert result["all_selected_labels_human_adjudicated"] is True
    assert result["model_qualification_established"] is False
    b1, b2 = [result["baselines"][b]["aggregate"] for b in ("B1", "B2")]
    assert b1["confirmed"]["recall"] == 0 and b1["confirmed"]["precision"] is None
    assert b1["surfaced"]["recall"] == b2["confirmed"]["recall"] == 1
    assert b1["raw_verdict_counts"] == {"review": 2}
    assert b2["confirmed"]["tp"] == 2 and b2["confirmed"]["fp"] == 0
    assert b2["resources"]["estimated_total_usd"] == 0.2
    assert b2["resources"]["owner_review_minutes"] == 4
    row = result["baselines"]["B2"]["per_case"][0]
    assert row["report_sha256"] == manifest["cases"][0]["reports"]["B2"]["sha256"]
    assert row["score"]["assumptions"]["fully_annotated"] is True
    assert row["media_sha256"] == manifest["cases"][0]["media_sha256"]
    assert "previous tuning" in " ".join(result["limitations"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("leak", ["source_group", "media_sha256"])
def test_cross_split_leakage_fails_before_selection(tmp_path, leak):
    path, manifest = make_dataset(tmp_path)
    first, second = manifest["cases"]
    second["split"] = "development"
    second[leak] = first[leak]
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="cross-split"):
        evaluate_dataset(path)


@pytest.mark.parametrize("which", ["media", "labels", "report"])
@pytest.mark.parametrize("failure", ["drift", "missing"])
def test_frozen_files_missing_or_changed_fail(tmp_path, which, failure):
    path, manifest = make_dataset(tmp_path)
    case = manifest["cases"][1]
    target = {"media": case["media_path"], "labels": case["labels"]["path"],
              "report": case["reports"]["B1"]["path"]}[which]
    file = tmp_path / target
    if failure == "missing":
        file.unlink()
    else:
        file.write_bytes(b"changed")
    with pytest.raises((ValueError, OSError)):
        evaluate_dataset(path)


@pytest.mark.parametrize("field", ["run_contract", "nested_contract", "asset", "media_hash", "check_asset"])
def test_report_bindings_fail_even_with_updated_report_hash(tmp_path, field):
    path, manifest = make_dataset(tmp_path)
    def change(report):
        if field == "run_contract":
            report["run"]["contract_sha256"] = "b" * 64
        elif field == "nested_contract":
            report["report"]["contract_sha256"] = "b" * 64
        elif field == "asset":
            report["assets"][0]["asset_id"] = "other"
        elif field == "media_hash":
            report["assets"][0]["sha256"] = "b" * 64
        else:
            report["checks"][0]["target_asset_id"] = "other"
    mutate_report(tmp_path, manifest["cases"][0], "B1", change)
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="binding mismatch"):
        evaluate_dataset(path)


@pytest.mark.parametrize("issue", ["missing", "extra", "duplicate_case"])
def test_incomplete_or_unequal_cohort_fails(tmp_path, issue):
    path, manifest = make_dataset(tmp_path)
    if issue == "missing":
        del manifest["cases"][1]["reports"]["B1"]
    elif issue == "extra":
        manifest["cases"][1]["reports"]["B3"] = manifest["cases"][1]["reports"]["B1"]
    else:
        manifest["cases"][1]["case_id"] = manifest["cases"][0]["case_id"]
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="cohort|duplicate case"):
        evaluate_dataset(path)


def test_unresolved_findings_withhold_aggregate_precision_and_missing_cost_is_unknown(tmp_path):
    path, manifest = make_dataset(tmp_path, fully_annotated=False)
    def change(report):
        report["checks"][0]["findings"][0].update(start_ms=7000, end_ms=8000)
        del report["cost"]
        del report["owner_review_minutes"]
    mutate_report(tmp_path, manifest["cases"][0], "B2", change)
    def unknown_cost(report):
        report["cost"]["unknown_cost_calls"] = 2
    mutate_report(tmp_path, manifest["cases"][1], "B2", unknown_cost)
    save_manifest(path, manifest)
    result = evaluate_dataset(path)
    aggregate = result["baselines"]["B2"]["aggregate"]
    assert aggregate["confirmed"]["recall"] == 0.5
    assert aggregate["confirmed"]["unresolved_findings"] == 1
    assert all(aggregate["confirmed"][key] is None for key in ("precision", "tp", "fp", "fn"))
    resources = aggregate["resources"]
    assert resources["known_estimated_usd"] == 0.1
    assert resources["estimated_total_usd"] is None and resources["unknown_cost_calls"] is None
    assert resources["reported_unknown_cost_calls"] == 2 and resources["unknown_cost_reports"] == 1
    assert resources["review_not_measured_cases"] == 1 and resources["owner_review_minutes"] is None
    assert result["human_adjudicated_holdout_available"] is False


@pytest.mark.parametrize("start,end", [(2000, 1000), (1000, 1000), (-1, 1000)])
def test_existing_scorer_rejects_malformed_intervals(tmp_path, start, end):
    path, manifest = make_dataset(tmp_path)
    def change(report):
        report["checks"][0]["findings"][0].update(start_ms=start, end_ms=end)
    mutate_report(tmp_path, manifest["cases"][0], "B1", change)
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="span"):
        evaluate_dataset(path)


@pytest.mark.parametrize("bad_path", ["https://example.com/media", "/tmp/media", "../media"])
def test_nonlocal_or_escaping_paths_rejected(tmp_path, bad_path):
    path, manifest = make_dataset(tmp_path)
    manifest["cases"][0]["media_path"] = bad_path
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="path"):
        evaluate_dataset(path)


def test_split_filter_still_validates_other_frozen_cases(tmp_path):
    path, manifest = make_dataset(tmp_path)
    manifest["cases"][1]["split"] = "development"
    save_manifest(path, manifest)
    assert evaluate_dataset(path)["cohort_case_ids"] == ["case-0"]
    assert evaluate_dataset(path, split="development")["cohort_case_ids"] == ["case-1"]
    (tmp_path / manifest["cases"][1]["labels"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        evaluate_dataset(path)


def test_cli_emits_json_and_rejects_incomplete_cohort(tmp_path):
    path, manifest = make_dataset(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_dataset.py"
    command = [sys.executable, str(script), str(path), "--split", "holdout", "--json"]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["baselines"]["B2"]["aggregate"]["confirmed"]["matched_labels"] == 2
    del manifest["cases"][1]["reports"]["B1"]
    save_manifest(path, manifest)
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 2 and "unequal baseline cohort" in completed.stderr
    assert not completed.stdout


def rewrite_labels(root, case, **changes):
    ref = case["labels"]
    labels = json.loads((root / ref["path"]).read_bytes())
    labels.update(changes)
    case["labels"] = write_json(root, ref["path"], labels)


def test_baseline_scoped_opposite_adjudications_do_not_leak_through_same_local_id(tmp_path):
    path, manifest = make_dataset(tmp_path, fully_annotated=False)
    for case in manifest["cases"]:
        rewrite_labels(tmp_path, case, adjudications_by_baseline={
            "B1": {"f": "false_positive"}, "B2": {"f": "true_positive"}})
    save_manifest(path, manifest)
    result = evaluate_dataset(path)
    b1 = result["baselines"]["B1"]["aggregate"]["surfaced"]
    b2 = result["baselines"]["B2"]["aggregate"]["surfaced"]
    assert (b1["tp"], b1["fp"], b1["matched_labels"]) == (0, 2, 0)
    assert (b2["tp"], b2["fp"], b2["matched_labels"]) == (2, 0, 2)


def test_baseline_scoped_distinct_finding_ids_and_missing_decisions_remain_independent(tmp_path):
    path, manifest = make_dataset(tmp_path, fully_annotated=False)
    for case in manifest["cases"]:
        def change(report):
            report["checks"][0]["findings"][0].update(id="b2-only", start_ms=7000, end_ms=8000)
        mutate_report(tmp_path, case, "B2", change)
        rewrite_labels(tmp_path, case, adjudications_by_baseline={"B1": {"f": "false_positive"}})
    save_manifest(path, manifest)
    result = evaluate_dataset(path)
    assert result["baselines"]["B1"]["aggregate"]["surfaced"]["fp"] == 2
    assert result["baselines"]["B2"]["aggregate"]["confirmed"]["unresolved_findings"] == 2
    assert result["baselines"]["B2"]["aggregate"]["confirmed"]["precision"] is None
    for case in manifest["cases"]:
        rewrite_labels(tmp_path, case, adjudications_by_baseline={
            "B1": {"f": "false_positive"}, "B2": {"b2-only": "true_positive"}})
    save_manifest(path, manifest)
    result = evaluate_dataset(path)
    assert result["baselines"]["B2"]["aggregate"]["confirmed"]["adjudicated_label_gaps"] == 2
    assert result["baselines"]["B2"]["aggregate"]["confirmed"]["precision"] == 1


@pytest.mark.parametrize("changes", [
    {"adjudications": {"f": "false_positive"}},
    {"adjudications": {}, "adjudications_by_baseline": {}},
    {"adjudications_by_baseline": {"unknown": {}}},
    {"adjudications_by_baseline": {"B1": []}},
])
def test_ambiguous_or_invalid_baseline_adjudications_fail(tmp_path, changes):
    path, manifest = make_dataset(tmp_path)
    rewrite_labels(tmp_path, manifest["cases"][0], **changes)
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="adjudications"):
        evaluate_dataset(path)


def test_single_baseline_retains_shared_adjudications(tmp_path):
    path, manifest = make_dataset(tmp_path)
    manifest["baselines"] = ["B2"]
    for case in manifest["cases"]:
        del case["reports"]["B1"]
        rewrite_labels(tmp_path, case, adjudications={"f": "false_positive"})
    save_manifest(path, manifest)
    assert evaluate_dataset(path)["baselines"]["B2"]["aggregate"]["confirmed"]["fp"] == 2


# --- probe benchmark manifest (hashes + labels only; media stays outside Git) ---
import json as _json
from pathlib import Path as _Path

from proofframe import probe_manifest as _pm

PROBE = _Path(__file__).resolve().parents[1] / "examples/evaluation_dataset/probe-2026-10-31.manifest.json"


def test_probe_manifest_is_valid_and_splits_i2v_from_t2v_by_reference_presence():
    m = _pm.load(PROBE)
    assert _pm.validate(m) == []
    i2v = [c for c in m["clips"] if c["reference_still_sha256"]]
    t2v = [c for c in m["clips"] if not c["reference_still_sha256"]]
    assert (len(i2v), len(t2v)) == (8, 9)
    assert {c["generator"]["mode"] for c in i2v} == {"i2v"} and {c["generator"]["mode"] for c in t2v} == {"t2v"}
    assert "continuity benchmark" in m["not_a"] and m["kind"].startswith("i2v-fidelity")


def test_probe_manifest_carries_no_media_and_no_brand_names():
    raw = PROBE.read_text(encoding="utf-8")
    assert "FWD" not in raw and ".mp4\"" in raw  # names files, embeds none
    assert len(raw) < 60_000


def test_probe_manifest_validate_rejects_label_source_drift_and_reference_mixups():
    m = _json.loads(PROBE.read_text())
    m["clips"][0]["label_source"] = "agent_draft"
    m["clips"][1]["reference_still_sha256"] = None  # an i2v clip without reference
    errors = _pm.validate(m)
    assert any("label_source" in e for e in errors) and any("reference" in e for e in errors)


def test_probe_media_verification_detects_changed_and_missing_files(tmp_path):
    import hashlib
    clip = tmp_path / "a.mp4"
    clip.write_bytes(b"x")
    still = tmp_path / "still.png"
    still.write_bytes(b"s")
    m = {"reference_still": {"file": "still.png", "sha256": hashlib.sha256(b"s").hexdigest()},
         "clips": [{"file": "a.mp4", "sha256": hashlib.sha256(b"x").hexdigest()},
                   {"file": "b.mp4", "sha256": "0" * 64}]}
    assert _pm.verify_media(m, tmp_path) == ["missing: b.mp4"]
    clip.write_bytes(b"changed")
    assert "sha256 mismatch: a.mp4" in _pm.verify_media(m, tmp_path)
