"""Compare local hash-bound reports on a complete frozen dataset cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from proofframe.evaluation_dataset import evaluate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--split", choices=["development", "calibration", "holdout"], default="holdout")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = parser.parse_args()
    try:
        result = evaluate_dataset(args.manifest, split=args.split)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, allow_nan=False))
        return
    print(result["scope"])
    print(f'{result["case_count"]} cases; {result["source_group_count"]} source groups; manifest {result["manifest_sha256"]}')
    for name, baseline in result["baselines"].items():
        metrics = baseline["aggregate"]
        print(f'{name}: confirmed recall={metrics["confirmed"]["recall"]}; '
              f'surfaced recall={metrics["surfaced"]["recall"]}; '
              f'confirmed precision={metrics["confirmed"]["precision"]}; '
              f'resources={json.dumps(metrics["resources"], allow_nan=False)}')


if __name__ == "__main__":
    main()
