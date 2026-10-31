"""Score the model-based artifact scan + single-shot continuity pass on the probe set, one-to-one.

  python scripts/score_probe_model_scan.py REPORT_DIR [--manifest M] [--out validation/runs/X.json]

REPORT_DIR holds one `proofframe verify --video-only --out` report per clip (the clip id is the media file name
`<folder>-<file>` with non-alphanumerics turned into '-'). Labels are clip-level (whole picture span):
artifact (fail|minor; 'disputed' is excluded), new_props, scene_changed. A gen-artifacts finding can match an
artifact label; a continuity finding can match new_props / scene_changed. An ERROR check counts as an
unscored clip, never as a pass. Labels are the reviewer's and in-sample; a finding on a clip with no matching
label is 'unresolved' (precision unknown) unless the clip is i2v and fully annotated, which this set does not claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from proofframe import probe_manifest as pm  # noqa: E402
from proofframe.evaluation import score_findings  # noqa: E402

CHECK_FOR_CLASS = {"artifact": "gen-artifacts", "new_props": "continuity", "scene_changed": "continuity"}
CATEGORY_FOR_CHECK = {"gen-artifacts": "artifact", "continuity": "continuity"}


def clip_key(clip: dict) -> str:
    p = Path(clip["file"])
    return re.sub(r"[^A-Za-z0-9]", "-", f"{p.parent.name}-{p.stem}")


def labels_for(clip: dict, end_s: float) -> list[dict]:
    lab, out = clip["labels"], []
    if lab["artifact"] in ("fail", "minor"):
        out.append({"id": "artifact", "class": "artifact", "t": [0, end_s], "accept_categories": ["artifact"]})
    if lab["new_props"] is True:
        out.append({"id": "new_props", "class": "new_props", "t": [0, end_s], "accept_categories": ["continuity"]})
    if lab["scene_changed"] is True:
        out.append({"id": "scene_changed", "class": "scene_changed", "t": [0, end_s], "accept_categories": ["continuity"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report_dir")
    ap.add_argument("--manifest", default=str(ROOT / "examples/evaluation_dataset/probe-2026-10-31.manifest.json"))
    ap.add_argument("--out")
    args = ap.parse_args()
    manifest = pm.load(Path(args.manifest))
    reports = {}
    for p in sorted(Path(args.report_dir).glob("probe-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        reports[p.stem[len("probe-"):]] = d
    rows, cost = [], 0.0
    cls_tot = {c: {"labels": 0, "caught": 0, "errored_clips_with_label": 0} for c in CHECK_FOR_CLASS}
    flags = {"gen-artifacts": {"findings": 0, "on_clips_without_label": 0}, "continuity": {"findings": 0, "on_clips_without_label": 0}}
    for clip in manifest["clips"]:
        key = clip_key(clip)
        rep = reports.get(key)
        if rep is None:
            raise SystemExit(f"no report for {clip['clip_id']} ({key})")
        end_s = clip["generator"]["served"]["duration_s"]
        labels = labels_for(clip, end_s)
        statuses = {c["assertion_id"]: c["status"] for c in rep["checks"]}
        findings, checks = [], []
        for c in rep["checks"]:
            if c["assertion_id"] not in CATEGORY_FOR_CHECK:
                continue
            fl = []
            for i, f in enumerate(c.get("findings") or []):
                fl.append({"id": f"{c['assertion_id']}:{i}", "category": CATEGORY_FOR_CHECK[c["assertion_id"]],
                           "root_cause_id": f.get("root_cause_id") or f"{c['assertion_id']}:{i}",
                           "entity": f.get("entity") or "clip", "verdict": f.get("verdict", "review"),
                           "start_ms": 0, "end_ms": int(end_s * 1000), "description": f.get("description", "")})
            checks.append({"assertion_id": c["assertion_id"], "findings": fl})
        score = score_findings({"checks": checks}, {"defects": labels, "fully_annotated": False})
        matched = {cls: v["matched_labels"] for cls, v in score["surfaced"]["by_class"].items()} if "by_class" in score["surfaced"] else {}
        for lab in labels:
            c = lab["class"]
            cls_tot[c]["labels"] += 1
            cls_tot[c]["caught"] += matched.get(c, 0)
            if statuses.get(CHECK_FOR_CLASS[c]) == "ERROR":
                cls_tot[c]["errored_clips_with_label"] += 1
        label_classes = {l["class"] for l in labels}
        for ch in checks:
            for f in ch["findings"]:
                flags[ch["assertion_id"]]["findings"] += 1
                if not any(CHECK_FOR_CLASS[c] == ch["assertion_id"] for c in label_classes):
                    flags[ch["assertion_id"]]["on_clips_without_label"] += 1
        run_cost = rep["cost"]["estimated_usd"]
        cost += run_cost
        rows.append({"clip_id": clip["clip_id"], "run_id": rep["run"]["run_id"], "mode": clip["generator"]["mode"],
                     "duration_s": end_s, "decision": rep["decision"]["decision"], "statuses": {k: statuses.get(k) for k in CATEGORY_FOR_CHECK},
                     "labels": sorted(label_classes), "artifact_label_disputed": clip["labels"]["artifact"] == "disputed",
                     "findings": sum(len(c["findings"]) for c in checks), "cost_usd": round(run_cost, 6)})
    out = {"manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(), "clips": len(rows),
           "estimated_usd": round(cost, 6), "per_class": cls_tot, "findings_by_check": flags,
           "gen_artifacts_errors": sum(r["statuses"]["gen-artifacts"] == "ERROR" for r in rows),
           "rows": rows,
           "scope": "in-sample; single-shot synthetic clips, --video-only, no reference still supplied to the scan; "
                    "new_props/scene_changed need a reference or neighbouring shot, which a single clip does not give the continuity pass"}
    print(json.dumps({k: out[k] for k in ("estimated_usd", "per_class", "findings_by_check", "gen_artifacts_errors")}, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
