"""Score a ProofFrame report against a labelled defect list (dev-set evaluation, not a benchmark).

usage: python scripts/score_findings.py REPORT.json LABELS.json [--tolerance-s 1.0]

A label counts as caught when a non-rejected finding (any scan/audit check) has a compatible category and
its interval (or its reference-shot interval) overlaps the label's time span widened by the tolerance, and
(when the label lists keywords) the finding names the same entity.
Findings that match no label are listed as 'unlabelled' — possible false positives OR label gaps; they need
a human decision and are not silently counted either way.
"""
from __future__ import annotations

import argparse
import json


def overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 <= b1 and b0 <= a1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("labels")
    ap.add_argument("--tolerance-s", type=float, default=1.0)
    a = ap.parse_args()
    env = json.load(open(a.report, encoding="utf-8"))
    labels = json.load(open(a.labels, encoding="utf-8"))["defects"]
    tol = a.tolerance_s
    findings = []
    for c in env["checks"]:
        for f in c.get("findings") or []:
            if f["verdict"] == "rejected":
                continue
            spans = [(f["start_ms"] / 1000, f["end_ms"] / 1000)]
            if "ref_start_ms" in f:
                spans.append((f["ref_start_ms"] / 1000, f["ref_end_ms"] / 1000))
            findings.append({**f, "check": c["assertion_id"], "spans": spans, "matched": []})
    rows = []
    for lab in labels:
        t0, t1 = lab["t"][0] - tol, lab["t"][1] + tol
        kws = [k.lower() for k in lab.get("keywords", [])]
        hits = [f for f in findings if f["category"] in lab["accept_categories"]
                and any(overlaps(s0, s1, t0, t1) for s0, s1 in f["spans"])
                and (not kws or any(k in (f.get("entity", "") + " " + f["description"]).lower() for k in kws))]
        for f in hits:
            f["matched"].append(lab["id"])
        best = ("confirmed" if any(h["verdict"] == "confirmed" for h in hits)
                else "review" if hits else "missed")
        rows.append((lab["id"], lab["class"], best, lab["desc"][:70]))
    must = [r for r in rows if r[1] == "must_catch"]
    print(f"labels: {len(rows)} (must_catch {len(must)})")
    for r in rows:
        print(f"  {r[0]:<4} {r[1]:<10} {r[2]:<9} {r[3]}")
    caught = sum(r[2] != "missed" for r in must)
    confirmed = sum(r[2] == "confirmed" for r in must)
    print(f"must_catch surfaced: {caught}/{len(must)}  (confirmed as defect: {confirmed}, review: {caught - confirmed})")
    un = [f for f in findings if not f["matched"]]
    print(f"unlabelled findings (FP or label gap — needs human): {len(un)}")
    for f in un:
        print(f"  {f['check']}: {f['category']}/{f['verdict']} @{f['start_ms']/1000:.1f}s {f['description'][:80]}")


if __name__ == "__main__":
    main()
