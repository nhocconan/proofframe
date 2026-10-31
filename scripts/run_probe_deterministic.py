"""Run the zero-cost deterministic checks over the probe clips and score them one-to-one.

  python scripts/run_probe_deterministic.py MEDIA_DIR [--manifest M] [--out validation/runs/X.json]

No provider is configured, no network is used, spend is 0. Thresholds below were fixed BEFORE the first run
on these clips; the reviewer's band they come from was proposed after looking at the same clips, so the
result is in-sample for the thresholds and says nothing about held-out footage.
Maps each failed check to a finding and each labelled defect class to a clip-level label (whole picture
span), then scores with proofframe.evaluation.score_findings (one-to-one matching).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from proofframe import media, probe_manifest as pm  # noqa: E402
from proofframe.evaluation import score_findings  # noqa: E402
from proofframe.interfaces import AssetInput  # noqa: E402
from proofframe.verify.pipeline import run_verification  # noqa: E402

THRESHOLDS = {  # (metric, relation, expected, category, description)
    "static": ("motion_mean_abs_diff", "at_least", 3, "motion_static", "first-to-last change below 3 grey levels: a still sold as video"),
    "excess_total": ("motion_mean_abs_diff", "at_most", 40, "motion_excess", "first-to-last change above 40 grey levels"),
    "excess_step": ("motion_max_step", "at_most", 25, "motion_excess", "largest 250 ms step above 25 grey levels"),
    "camera": ("global_motion_px", "at_most", 20, "camera_move", "camera move above 20 px (240 px-wide frame)"),
}


class DirStore:
    def __init__(self, root: Path):
        self.root = root

    def put_file(self, src: Path, *, media_type: str) -> str:
        sha = media.sha256_file(src)
        dst = self.root / sha
        if not dst.exists():
            shutil.copyfile(src, dst)
        return sha

    def path_for(self, sha: str) -> Path:
        return self.root / sha


class ZeroBudget:
    def reserve(self, **_):
        raise RuntimeError("no paid call is allowed in this run")

    def settle(self, *_, **__):
        pass


def contract(keys: list[str], end_ms: int) -> dict:
    assertions = []
    for key in keys:
        metric, relation, expected, _, why = THRESHOLDS[key]
        assertions.append({
            "assertion_id": key, "source_pointer": f"/probe/{key}", "target_asset_id": "v", "predicate": why,
            "expected": str(expected), "scope": {"start_ms": 0, "end_ms": end_ms},
            "observation": {"kind": "technical", "subject": "clip", "attribute": metric, "comparator": "technical",
                            "technical_metric": metric, "technical_relation": relation}})
    return {"contract_id": "probe-deterministic", "revision": 1, "tenant_id": "t", "profile": "film",
            "profile_revision": "1", "assets": [{"asset_id": "v", "media_type": "video"}], "assertions": assertions}


def labels_for(clip: dict, end_ms: int) -> dict:
    lab, defects = clip["labels"], []
    span = [0, end_ms / 1000]
    if lab["motion_band"] == "near_static":
        defects.append({"id": "static", "class": "motion_static", "t": span, "accept_categories": ["motion_static"]})
    if lab["motion_band"] == "excess":
        defects.append({"id": "excess", "class": "motion_excess", "t": span, "accept_categories": ["motion_excess"]})
    if lab["camera_holds"] is False:
        defects.append({"id": "camera", "class": "camera_move", "t": span, "accept_categories": ["camera_move"]})
    return {"defects": defects, "fully_annotated": clip["generator"]["mode"] == "i2v"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("media_dir")
    ap.add_argument("--manifest", default=str(ROOT / "examples/evaluation_dataset/probe-2026-10-31.manifest.json"))
    ap.add_argument("--out")
    args = ap.parse_args()
    manifest = pm.load(Path(args.manifest))
    problems = pm.validate(manifest) + pm.verify_media(manifest, Path(args.media_dir))
    if problems:
        print("\n".join(problems))
        return 1
    rows, totals = [], {}
    work = Path(tempfile.mkdtemp(prefix="pf-probe-"))
    try:
        for clip in manifest["clips"]:
            path = Path(args.media_dir) / clip["file"]
            info = media.probe(path)
            end_ms = min(info.duration_ms, info.video_duration_ms or info.duration_ms)
            i2v = clip["generator"]["mode"] == "i2v"
            keys = ["static", "excess_total", "excess_step"] + (["camera"] if i2v else [])  # t2v prompt asked for a pan
            store = DirStore(work)
            sha = store.put_file(path, media_type="video/mp4")
            env = run_verification(run_id=f"probe-{clip['clip_id']}", run_mode="synthetic_fixture",
                                   contract_json=contract(keys, end_ms), assets=[AssetInput("v", 1, sha, "video")],
                                   store=store, budget=ZeroBudget()).envelope
            findings, statuses, values = [], {}, {}
            for check in env["checks"]:
                key = check["assertion_id"]
                statuses[key] = check["status"]
                m = check.get("technical_measurement") or {}
                values[key] = m.get("value")
                if check["status"] in ("FAIL", "UNCERTAIN"):
                    cat = THRESHOLDS[key][3]
                    findings.append({"id": key, "category": cat, "root_cause_id": cat, "entity": "clip",
                                     "verdict": "confirmed" if check["status"] == "FAIL" else "review",
                                     "start_ms": 0, "end_ms": end_ms, "description": THRESHOLDS[key][4]})
            report = {"checks": [{"assertion_id": "probe", "findings": findings}]}
            score = score_findings(report, labels_for(clip, end_ms))
            rows.append({"clip_id": clip["clip_id"], "mode": clip["generator"]["mode"], "end_ms": end_ms,
                         "statuses": statuses, "values": values, "labels": [d["class"] for d in labels_for(clip, end_ms)["defects"]],
                         "confirmed": {k: score["confirmed"][k] for k in ("tp", "fp", "fn", "findings", "unresolved_findings", "matched_labels")},
                         "cost_usd": env["cost"]["estimated_usd"]})
            print(f'{clip["clip_id"]:18} {statuses} {values}')
    finally:
        shutil.rmtree(work, ignore_errors=True)

    classes = {"motion_static": "static", "motion_excess": "excess", "camera_move": "camera"}
    table, unresolved = {}, sum(r["confirmed"]["unresolved_findings"] for r in rows)
    for cls in classes:
        lab = sum(cls in r["labels"] for r in rows)
        # a finding of this class is a TP when its clip carries that label
        tp = sum(cls in r["labels"] and r["confirmed"]["matched_labels"] and any(
            f for f in r["statuses"] if THRESHOLDS[f][3] == cls and r["statuses"][f] == "FAIL") for r in rows)
        fp_clips = [r["clip_id"] for r in rows if cls not in r["labels"] and any(
            THRESHOLDS[f][3] == cls and r["statuses"][f] == "FAIL" for f in r["statuses"])]
        fp_i2v = [c for c in fp_clips if c.endswith("-i2v")]
        unresolved_clips = [c for c in fp_clips if c.endswith("-t2v")]
        table[cls] = {"labels": lab, "caught": tp, "missed": lab - tp, "false_positive_i2v": len(fp_i2v),
                      "t2v_findings_unadjudicated": len(unresolved_clips)}
    unchecked = sum(s == "NOT_CHECKED" for r in rows for s in r["statuses"].values())
    out = {"manifest_sha256": __import__("hashlib").sha256(Path(args.manifest).read_bytes()).hexdigest(),
           "thresholds": {k: v[:3] for k, v in THRESHOLDS.items()}, "clips": len(rows), "estimated_usd": 0,
           "unresolved_findings_total": unresolved, "not_checked_checks": unchecked, "per_class": table, "rows": rows,
           "scope": "in-sample for thresholds; synthetic single-shot clips; i2v labels cover motion/camera only"}
    print(json.dumps(table, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
