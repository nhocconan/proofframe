"""Score the model-based artifact scan + continuity / reference-match checks on the probe set, one-to-one.

  python scripts/score_probe_model_scan.py REPORT_DIR [--manifest M] [--out validation/runs/X.json]

REPORT_DIR holds one `proofframe verify --video-only --out` report per clip (the clip id is the media file name
`<folder>-<file>` with non-alphanumerics turned into '-'). Labels are clip-level (whole picture span):
artifact (fail|minor; 'disputed' is excluded), new_props, scene_changed.

Class -> check mapping (strict):
  artifact       <- gen-artifacts findings of any category. gen-artifacts `object` findings do NOT credit new_props.
  new_props      <- continuity findings OR reference-match findings of category new_prop / missing_prop
  scene_changed  <- continuity findings OR reference-match findings of category scene_changed
A reference-match finding with verdict review counts as a flag (surfaced track).

Per class the table is caught / checked / labelled. A label is `checked` only if a check that could raise that class
finished PASS, FAIL or REVIEW. ERROR, NOT_CHECKED and a missing check (old reports without reference-match) are not checked,
and neither is a continuity check that compared "0 shot pairs" (vacuous PASS in old reports). Not-checked labels are
excluded from the recall denominator and listed separately under `not_checked`. Labels are the reviewer's and in-sample;
a finding on a clip with no matching label is 'unresolved' (precision unknown).
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

CHECKS_FOR_CLASS = {"artifact": ("gen-artifacts",), "new_props": ("continuity", "reference-match"),
                    "scene_changed": ("continuity", "reference-match")}
SCORED_CHECKS = ("gen-artifacts", "continuity", "reference-match")
CHECKED_STATUSES = {"PASS", "FAIL", "REVIEW"}
# scorer category for a finding; None = not scored. reference-match categories map by name, never to `artifact`.
REFERENCE_CATEGORY = {"new_prop": "new_props", "missing_prop": "new_props", "scene_changed": "scene_changed"}
ACCEPT = {"artifact": ["artifact"], "new_props": ["continuity", "new_props"], "scene_changed": ["continuity", "scene_changed"]}


def check_finished(check: dict | None) -> bool:
    """True only if the check ran to a PASS/FAIL/REVIEW result that actually examined something."""
    if not check or check.get("status") not in CHECKED_STATUSES:
        return False
    if check.get("assertion_id") == "continuity":
        text = " ".join(str(check.get(k) or "") for k in ("rationale", "observed")) + " " + " ".join(check.get("limitations") or [])
        if re.search(r"\b0 shot pairs compared", text):
            return False
    return True


def scored_category(check_id: str, finding: dict) -> str | None:
    if check_id == "gen-artifacts":
        return "artifact"
    if check_id == "continuity":
        return "continuity"
    return REFERENCE_CATEGORY.get(finding.get("category"))


def clip_key(clip: dict) -> str:
    p = Path(clip["file"])
    return re.sub(r"[^A-Za-z0-9]", "-", f"{p.parent.name}-{p.stem}")


def labels_for(clip: dict, end_s: float) -> list[dict]:
    lab, out = clip["labels"], []
    if lab["artifact"] in ("fail", "minor"):
        out.append({"id": "artifact", "class": "artifact", "t": [0, end_s], "accept_categories": ACCEPT["artifact"]})
    if lab["new_props"] is True:
        out.append({"id": "new_props", "class": "new_props", "t": [0, end_s], "accept_categories": ACCEPT["new_props"]})
    if lab["scene_changed"] is True:
        out.append({"id": "scene_changed", "class": "scene_changed", "t": [0, end_s], "accept_categories": ACCEPT["scene_changed"]})
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
    cls_tot = {c: {"labels": 0, "labelled": 0, "checked": 0, "caught": 0, "not_checked": []} for c in CHECKS_FOR_CLASS}
    flags = {c: {"findings": 0, "on_clips_without_label": 0} for c in SCORED_CHECKS}
    for clip in manifest["clips"]:
        key = clip_key(clip)
        rep = reports.get(key)
        if rep is None:
            raise SystemExit(f"no report for {clip['clip_id']} ({key})")
        end_s = clip["generator"]["served"]["duration_s"]
        labels = labels_for(clip, end_s)
        by_id = {c["assertion_id"]: c for c in rep["checks"]}
        statuses = {k: (by_id[k]["status"] if k in by_id else None) for k in SCORED_CHECKS}
        findings, checks = [], []
        for c in rep["checks"]:
            if c["assertion_id"] not in SCORED_CHECKS:
                continue
            fl = []
            for i, f in enumerate(c.get("findings") or []):
                cat = scored_category(c["assertion_id"], f)
                if cat is None:
                    continue
                fl.append({"id": f"{c['assertion_id']}:{i}", "category": cat,
                           "root_cause_id": f.get("root_cause_id") or f"{c['assertion_id']}:{i}",
                           "entity": f.get("entity") or "clip", "verdict": f.get("verdict", "review"),
                           "start_ms": 0, "end_ms": int(end_s * 1000), "description": f.get("description", "")})
            checks.append({"assertion_id": c["assertion_id"], "findings": fl})
        score = score_findings({"checks": checks}, {"defects": labels, "fully_annotated": False})
        matched = {cls: v["matched_labels"] for cls, v in score["surfaced"]["per_class"].items()}
        for lab in labels:
            c = lab["class"]
            t = cls_tot[c]
            t["labelled"] += 1
            t["labels"] += 1
            caught = matched.get(c, 0)
            if caught or any(check_finished(by_id.get(k)) for k in CHECKS_FOR_CLASS[c]):
                t["checked"] += 1
                t["caught"] += caught
            else:
                t["not_checked"].append(clip["clip_id"])
        label_classes = {l["class"] for l in labels}
        for ch in checks:
            for f in ch["findings"]:
                flags[ch["assertion_id"]]["findings"] += 1
                if not any(ch["assertion_id"] in CHECKS_FOR_CLASS[c] for c in label_classes):
                    flags[ch["assertion_id"]]["on_clips_without_label"] += 1
        run_cost = rep["cost"]["estimated_usd"]
        cost += run_cost
        rows.append({"clip_id": clip["clip_id"], "run_id": rep["run"]["run_id"], "mode": clip["generator"]["mode"],
                     "duration_s": end_s, "decision": rep["decision"]["decision"], "statuses": statuses,
                     "labels": sorted(label_classes), "artifact_label_disputed": clip["labels"]["artifact"] == "disputed",
                     "findings": sum(len(c["findings"]) for c in checks),
                     "continuity_vacuous": "continuity" in by_id and not check_finished(by_id["continuity"]), "cost_usd": round(run_cost, 6)})
    out = {"manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(), "clips": len(rows),
           "estimated_usd": round(cost, 6), "per_class": cls_tot, "findings_by_check": flags,
           "gen_artifacts_errors": sum(r["statuses"]["gen-artifacts"] == "ERROR" for r in rows),
           "rows": rows,
           "scope": "in-sample; single-shot synthetic clips, --video-only. caught/checked/labelled: labels whose check did not finish "
                    "(ERROR, NOT_CHECKED, missing, continuity with 0 shot pairs) are excluded from `checked` and listed in `not_checked`"}
    print(json.dumps({k: out[k] for k in ("estimated_usd", "per_class", "findings_by_check", "gen_artifacts_errors")}, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
