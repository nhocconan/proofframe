"""Fake Verifier for API/worker tests. Always labelled synthetic_fixture, never live."""
from __future__ import annotations

import tempfile
from pathlib import Path

from proofframe.interfaces import RunOutcome


def run(*, run_id, run_mode, contract_json, assets, store, budget, assertion_ids=None) -> RunOutcome:
    if contract_json["contract_id"].startswith("boom"):
        raise RuntimeError("fake verifier exploded")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"\x89PNG fake frame " + run_id.encode())
    sha = store.put_file(Path(f.name), media_type="image/png")
    Path(f.name).unlink()
    ids = assertion_ids or [a["assertion_id"] for a in contract_json["assertions"]]
    env = {
        "schema_version": "proofframe.envelope.v0.1",
        "run": {"run_id": run_id, "run_mode": "synthetic_fixture", "profile": "film",
                "contract_id": contract_json["contract_id"], "contract_revision": contract_json["revision"]},
        "decision": {"decision": "REVIEW", "unresolved": ids, "blocking_failures": [],
                     "advisory_findings": [], "run_mode": "synthetic_fixture", "publish_authorized": False},
        "assets": [{"asset_id": a.asset_id, "revision": a.revision, "sha256": a.sha256} for a in assets],
        "checks": [{"assertion_id": i, "status": "NOT_CHECKED"} for i in ids],
        "evidence": [{"evidence_id": "ev-1", "kind": "frame", "sha256": sha, "url": f"/v1/media/{sha}"}],
        "cost": {"estimated_usd": 0.0, "unknown_cost_calls": 0, "reserved_open_usd": 0.0},
        "labels": ["SYNTHETIC FIXTURE — not a live run"],
        "report_sha256": "0" * 64,
        "report": {"assets": [{"asset_id": a.asset_id, "revision": a.revision, "sha256": a.sha256,
                               "media_type": a.media_type, "duration_ms": None} for a in assets]},
    }
    return RunOutcome(envelope=env, artifacts=[{"sha256": sha, "media_type": "image/png", "kind": "frame"}])
