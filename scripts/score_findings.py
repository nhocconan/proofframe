"""Offline development diagnostic: REPORT LABELS [--tolerance-s 1.0] [--json]."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from proofframe.evaluation import analyze_judge_controls, score_findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("labels")
    parser.add_argument("--tolerance-s", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    parser.add_argument("--controls", help="offline JSON with order_records and identical_records")
    args = parser.parse_args()
    try:
        report_bytes = Path(args.report).read_bytes()
        label_bytes = Path(args.labels).read_bytes()
        report, labels = json.loads(report_bytes), json.loads(label_bytes)
        result = score_findings(report, labels, tolerance_s=args.tolerance_s)
        result["input_hashes"] = {"report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                                  "labels_sha256": hashlib.sha256(label_bytes).hexdigest()}
        if args.controls:
            control_bytes = Path(args.controls).read_bytes()
            controls = json.loads(control_bytes)
            result["judge_controls"] = analyze_judge_controls(controls["order_records"], controls["identical_records"])
            result["input_hashes"]["controls_sha256"] = hashlib.sha256(control_bytes).hexdigest()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, allow_nan=False))
        return
    print(result["scope"])
    print(f'labels: {result["labels"]}; root causes: {result["root_causes"]}; duplicates removed: {result["duplicates_removed"]}')
    for track in ("confirmed", "surfaced"):
        metrics = result[track]
        precision = "unknown" if metrics["precision"] is None else f'{metrics["precision"]:.3f}'
        print(f'{track}: matched {metrics["matched_labels"]}/{result["labels"]}; precision {precision}; '
              f'unmatched {metrics["unmatched_findings"]}; unresolved {metrics["unresolved_findings"]}')
        for cls, counts in metrics["per_class"].items():
            print(f'  {cls}: {counts["matched_labels"]}/{counts["labels"]}')
        for finding in metrics["unmatched"]:
            print(f'  unmatched {", ".join(finding["finding_ids"])}: {finding["adjudication"]}')
    if "judge_controls" in result:
        print("judge controls: " + json.dumps(result["judge_controls"], allow_nan=False))


if __name__ == "__main__":
    main()
