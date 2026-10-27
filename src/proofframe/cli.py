"""`proofframe` CLI — a client of the same HTTP service the UI uses (no parallel verifier).

  proofframe doctor
  proofframe verify --contract demo/contract.json --video shot-01=/media/x.mp4 [--assertions a,b] [--wait]
  proofframe report RUN_ID [--out file.json]
  proofframe export-repair RUN_ID --out repair-request.json
  proofframe reverify --receipt repair-receipt.json [--wait]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

API = os.environ.get("PROOFFRAME_API_URL", "http://api:8080")
TOKEN = os.environ.get("PROOFFRAME_API_TOKEN", "dev-local-token")


def _c() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=600)


def _ok(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        sys.exit(f"HTTP {r.status_code} {r.request.method} {r.request.url.path}: {r.text[:500]}")
    return r.json()


def upload(c: httpx.Client, asset_id: str, path: Path, media_type: str = "video") -> dict:
    with open(path, "rb") as fh:
        return _ok(c.post("/v1/assets", data={"asset_id": asset_id, "media_type": media_type},
                          files={"file": (path.name, fh, "video/mp4")}))


def wait(c: httpx.Client, run_id: str, timeout_s: int = 1800) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        run = _ok(c.get(f"/v1/verifications/{run_id}"))
        if run["status"] in ("succeeded", "failed", "cancelled"):
            return run
        time.sleep(3)
    sys.exit(f"timed out waiting for {run_id}")


def summarize(env: dict) -> None:
    d = env["decision"]
    print(f"run {env['run']['run_id']}  mode={env['run']['run_mode']}  DECISION={d['decision']} "
          f"(publish_authorized={d['publish_authorized']})  est_cost=${env['cost']['estimated_usd']:.4f} "
          f"unknown_cost_calls={env['cost']['unknown_cost_calls']}")
    for ch in env["checks"]:
        foc = ch.get("focus") or {}
        reg = f"  [{ch['regression']['classification']}]" if ch.get("regression") else ""
        print(f"  {ch['status']:<12} {ch['assertion_id']:<14} expected={ch['expected']!r:<40.40} "
              f"observed={ch['observed']!r:<40.40} focus={foc.get('start_ms')}-{foc.get('end_ms')}ms{reg}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="proofframe")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    v = sub.add_parser("verify")
    v.add_argument("--contract", required=True, type=Path)
    v.add_argument("--video", action="append", required=True, help="asset_id=/path/to.mp4")
    v.add_argument("--assertions")
    v.add_argument("--wait", action="store_true")
    v.add_argument("--out", type=Path)
    r = sub.add_parser("report")
    r.add_argument("run_id")
    r.add_argument("--out", type=Path)
    e = sub.add_parser("export-repair")
    e.add_argument("run_id")
    e.add_argument("--out", type=Path, required=True)
    rv = sub.add_parser("reverify")
    rv.add_argument("--receipt", type=Path, required=True)
    rv.add_argument("--wait", action="store_true")
    rv.add_argument("--out", type=Path)
    a = p.parse_args(argv)

    with _c() as c:
        if a.cmd == "doctor":
            print("api:", _ok(c.get("/healthz")))
            print("budget:", _ok(c.get("/v1/budget")))
            print("meta key configured:", bool(os.environ.get("META_DEV_API")))
            return
        if a.cmd == "verify":
            contract = json.loads(a.contract.read_text(encoding="utf-8"))
            ck = _ok(c.post("/v1/contracts", json=contract))
            assets = []
            for spec in a.video:
                aid, path = spec.split("=", 1)
                av = upload(c, aid, Path(path))
                print(f"asset {aid} rev {av['revision']} sha256 {av['sha256']} {av.get('duration_ms')}ms")
                assets.append({"asset_id": aid, "sha256": av["sha256"]})
            body = {"contract_sha256": ck["contract_sha256"], "assets": assets, "run_mode": "live"}
            if a.assertions:
                body["assertion_ids"] = a.assertions.split(",")
            run = _ok(c.post("/v1/verifications", json=body, headers={"Idempotency-Key": uuid.uuid4().hex}))
            print("queued", run["run_id"])
            if a.wait:
                run = wait(c, run["run_id"])
                print("status", run["status"], run.get("error") or "")
                if run["status"] == "succeeded":
                    env = _ok(c.get(f"/v1/verifications/{run['run_id']}/report"))
                    summarize(env)
                    if a.out:
                        a.out.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
            return
        if a.cmd == "report":
            env = _ok(c.get(f"/v1/verifications/{a.run_id}/report"))
            summarize(env)
            if a.out:
                a.out.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
            return
        if a.cmd == "export-repair":
            req = _ok(c.post("/v1/repair-requests", json={"run_id": a.run_id}))
            a.out.write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
            print("wrote", a.out, "request", req.get("request_id"))
            return
        if a.cmd == "reverify":
            receipt = json.loads(a.receipt.read_text(encoding="utf-8"))
            run = _ok(c.post("/v1/repair-receipts", json=receipt))
            print("regression run", run["run_id"])
            if a.wait:
                run = wait(c, run["run_id"])
                print("status", run["status"], run.get("error") or "")
                if run["status"] == "succeeded":
                    env = _ok(c.get(f"/v1/verifications/{run['run_id']}/report"))
                    summarize(env)
                    if a.out:
                        a.out.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
