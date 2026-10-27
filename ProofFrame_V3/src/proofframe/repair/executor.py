"""File-drop repair executor (the external producer side). `python -m proofframe.repair.executor`

Reads $PROOFFRAME_DROPBOX_DIR/requests/*.json, performs ONLY the allowlisted typed capability
`ffmpeg_drawtext_composite` (re-composite the approved caption onto the producer's clean plate),
writes the new immutable output to outputs/, uploads it to the API as a new revision, writes a
receipt to receipts/ and submits it. It cannot edit approved intent: it never calls /v1/contracts.

EXECUTOR_VARIANT (labelled in every receipt; used to demonstrate Gate 3 outcomes honestly):
  correct      - composite the approved text exactly
  faulty_text  - simulated sloppy producer: introduces a one-letter typo  -> expect STILL_FAILING
  drops_audio  - correct text but loses the audio track during re-encode   -> expect REGRESSION
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

from proofframe_contracts.models import AssetBinding, RepairReceipt, fingerprint, RepairPlan

from .. import media

DROP = Path(os.environ.get("PROOFFRAME_DROPBOX_DIR", "/dropbox"))
API = os.environ.get("PROOFFRAME_API_URL", "http://api:8080")
TOKEN = os.environ.get("PROOFFRAME_API_TOKEN", "dev-local-token")
VARIANT = os.environ.get("EXECUTOR_VARIANT", "correct")
# Producer-owned clean plates per logical asset (the source stage below compositing).
CLEAN_PLATES = json.loads(os.environ.get("EXECUTOR_CLEAN_PLATES",
                                         '{"shot-01": "/media/clips/tos_0015_0115.mp4"}'))
ALLOWED = {"ffmpeg_drawtext_composite"}


def _typo(text: str) -> str:
    return text.replace("Celia", "Cella") if "Celia" in text else text[:-1] + "x"


def execute(req_path: Path, client: httpx.Client) -> Path:
    req = json.loads(req_path.read_text(encoding="utf-8"))
    plan = RepairPlan.model_validate(req["plan"])
    if fingerprint(plan) != req["plan_sha256"]:
        raise ValueError("plan hash mismatch — refusing")
    current = {a["asset_id"]: a for a in req["current_assets"]}
    replacements, notes = [], []
    for stage in req["stages"]:
        if stage["executor_capability"] not in ALLOWED:
            notes.append(f"{stage['action_id']}: capability {stage['executor_capability']} not available here")
            continue
        action = next(a for a in plan.actions if a.action_id == stage["action_id"])
        target = action.target_asset_id
        plate = Path(CLEAN_PLATES[target])
        work = DROP / "work" / req["request_id"]
        work.mkdir(parents=True, exist_ok=True)
        text = stage["set_to"] if VARIANT != "faulty_text" else _typo(stage["set_to"])
        tfile = work / "caption.txt"
        tfile.write_text(text, encoding="utf-8")
        scope = stage["scope"] or {"start_ms": 0, "end_ms": 10_000}
        out = DROP / "outputs" / f"{target}-{req['request_id']}-{VARIANT}.mp4"
        media.composite_caption(plate, out, text_file=tfile, start_ms=scope["start_ms"] + 1000,
                                end_ms=scope["end_ms"] - 1000, drop_audio=(VARIANT == "drops_audio"))
        with open(out, "rb") as fh:
            r = client.post("/v1/assets", data={"asset_id": target, "media_type": "video"},
                            files={"file": (out.name, fh, "video/mp4")})
        r.raise_for_status()
        av = r.json()
        prev = current[target]
        replacements.append({"target_asset_id": target, "input_sha256": prev["sha256"],
                             "output": AssetBinding(asset_id=target, revision=av["revision"], sha256=av["sha256"],
                                                    media_type="video", duration_ms=av.get("duration_ms")
                                                    ).model_dump(mode="json")})
        notes.append(f"{stage['action_id']}: re-composited {stage['source_pointer']} on clean plate "
                     f"{plate.name}; variant={VARIANT}")
    receipt = RepairReceipt.model_validate({"plan_sha256": req["plan_sha256"], "replacements": replacements,
                                            "execution_mode": "real"})
    doc = {"request_id": req["request_id"], "receipt": receipt.model_dump(mode="json"),
           "executor": {"name": "proofframe-file-drop-ffmpeg", "variant": VARIANT,
                        "capabilities": sorted(ALLOWED), "notes": notes,
                        "disclaimer": "execution record, not a success verdict"}}
    rp = DROP / "receipts" / f"{req['request_id']}.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return rp


def main() -> None:
    once = "--once" in sys.argv
    (DROP / "requests").mkdir(parents=True, exist_ok=True)
    done_dir = DROP / "requests" / "done"
    done_dir.mkdir(exist_ok=True)
    with httpx.Client(base_url=API, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=600) as client:
        while True:
            for req_path in sorted((DROP / "requests").glob("*.json")):
                try:
                    rp = execute(req_path, client)
                    doc = json.loads(rp.read_text(encoding="utf-8"))
                    if os.environ.get("EXECUTOR_SUBMIT", "true") == "true":
                        r = client.post("/v1/repair-receipts", json=doc)
                        print(f"[executor] {req_path.name} -> receipt {rp.name}; submit HTTP {r.status_code} {r.text[:300]}",
                              flush=True)
                    else:
                        print(f"[executor] {req_path.name} -> receipt {rp.name} (not submitted)", flush=True)
                except Exception as exc:
                    print(f"[executor] {req_path.name} FAILED: {type(exc).__name__}: {exc}", flush=True)
                req_path.rename(done_dir / req_path.name)
            if once:
                return
            time.sleep(2)


if __name__ == "__main__":
    main()
