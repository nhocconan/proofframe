"""Compile a dialogue verification contract from a workprint EDL.

The film pipeline assembles each scene cut from locked takes and records an
EDL (JSON list of {shot, take, start, dur, line}) where ``line`` is the exact
locked script line spoken in that shot (or null). This compiler turns that
EDL into a ProofFrame contract with one blind dialogue assertion per spoken
line, scoped to the shot's window in the assembled cut — the deterministic
half of the script->contract step (P0-4). Visual/canon assertions still come
from the hand-authored scene contracts.

Usage:
    python scripts/compile_edl_contract.py EDL.json \
        --asset-id c01-workprint --contract-id tan-so-0-ep01-c01-dialogue \
        --tenant demo-tenant --profile-revision v5-c01 [--language Vietnamese] \
        -o contract.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compile_edl(edl: list[dict], *, asset_id: str, contract_id: str, tenant_id: str,
                profile_revision: str, language: str = "Vietnamese") -> dict:
    assertions = []
    cursor = 0.0
    for entry in edl:
        dur = float(entry["dur"])
        start_ms, end_ms = round(cursor * 1000), round((cursor + float(dur)) * 1000)
        cursor += dur
        line = entry.get("line")
        if not line:
            continue
        shot = str(entry["shot"])
        assertions.append({
            "assertion_id": f"dlg-{shot.lower().replace('_', '-')}",
            "source_pointer": f"/edl/{shot}",
            "target_asset_id": asset_id,
            "predicate": "spoken line matches locked script",
            "expected": line,
            "scope": {"start_ms": start_ms, "end_ms": end_ms},
            "observation": {"kind": "dialogue", "subject": "the on-screen speaker",
                            "attribute": "spoken words", "comparator": "dialogue_nfc",
                            "double_transcription": True, "language_bias": [language]},
        })
    return {
        "schema_version": "proofframe.contract.v0.1",
        "contract_id": contract_id,
        "revision": 1,
        "tenant_id": tenant_id,
        "profile": "film",
        "profile_revision": profile_revision,
        "assets": [{"asset_id": asset_id, "media_type": "video", "role": "output"}],
        "assertions": assertions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edl")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--profile-revision", default="edl-compiled")
    parser.add_argument("--language", default="Vietnamese")
    parser.add_argument("-o", "--out", required=True)
    args = parser.parse_args()
    edl = json.loads(Path(args.edl).read_text(encoding="utf-8"))
    contract = compile_edl(edl, asset_id=args.asset_id, contract_id=args.contract_id,
                           tenant_id=args.tenant, profile_revision=args.profile_revision,
                           language=args.language)
    Path(args.out).write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}: {len(contract['assertions'])} dialogue assertions")


if __name__ == "__main__":
    main()
