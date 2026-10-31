# ProofFrame API + report contract (v0.1, Gate 1–3)

One implementation behind CLI, API and UI. Core: `proofframe.verify.pipeline.run_verification`
(signature in `src/proofframe/interfaces.py`). Contracts use `proofframe_contracts.models.Contract`
(seed + `scope`/`observation` extension). All JSON; times are **asset-local milliseconds** unless named `*_s`.

## HTTP routes (FastAPI, `/v1`, bound to 127.0.0.1 in compose)

Auth: header `Authorization: Bearer <PROOFFRAME_API_TOKEN>` on every route except `/healthz`. Tenant = `tenant_id` of the token config (single tenant `demo-tenant` in v0.1; every query still filters by tenant).

| Method | Path | Body / result |
|---|---|---|
| GET | `/healthz` | `{"ok":true}` |
| POST | `/v1/assets` | multipart `file`, `asset_id`, `media_type` → `AssetVersion` (server computes sha256 + ffprobe; revision = previous+1 for that asset_id; identical bytes return the existing version) |
| GET | `/v1/assets` | list `AssetVersion` |
| GET | `/v1/media/{sha256}` | raw bytes; **must honour `Range` with 206** (video seek). Also serves evidence frames (image/png) and proxies |
| POST | `/v1/contracts` | Contract JSON → `{contract_id, revision, contract_sha256}`; immutable — same id+revision with different hash → 409 |
| GET | `/v1/contracts/{contract_sha256}` | contract JSON |
| POST | `/v1/verifications` | header `Idempotency-Key` required. `{contract_sha256, assets:[{asset_id, sha256}], assertion_ids?:[..], run_mode:"live", previous_run_id?:str}` → `Run` (status `queued`). Same key → same run |
| GET | `/v1/verifications` | list `Run` |
| GET | `/v1/verifications/{run_id}` | `Run` |
| GET | `/v1/verifications/{run_id}/report` | `ReportEnvelope` (404 until status `succeeded`) |
| POST | `/v1/verifications/{run_id}/cancel` | marks cancel requested (does not prove provider cancellation) |
| POST | `/v1/repair-requests` | `{run_id}` → `RepairRequest` (also written to file-drop `requests/`) |
| POST | `/v1/repair-receipts` | `RepairReceipt` (+ new asset already uploaded) → starts regression run, returns `Run` |
| GET | `/v1/budget` | `{cap_project_usd, cap_run_usd, spent_settled_usd, reserved_open_usd, unknown_cost_calls}` |
| GET | `/v1/capabilities` | contents of the capability registry (static JSON from `docs/CAPABILITY_PROBES.md` facts) |

`Run`: `{run_id, status: queued|running|succeeded|failed|cancelled, run_mode, contract_sha256, assets:[AssetVersion], previous_run_id, created_at, started_at, finished_at, error, decision?: "BLOCK"|"REVIEW"|"ELIGIBLE", cost_usd_estimated, attempts}`
`AssetVersion`: `{asset_id, revision, sha256, media_type, bytes, duration_ms, width, height, has_audio, created_at, url:"/v1/media/<sha>"}`

Execution status (`Run.status`) ≠ check status ≠ release decision. A `succeeded` run can BLOCK.

### Video-only mode and the optional reference still

`POST /v1/verifications` with `{"mode":"video_only", "assets":[...], "run_mode":"live"}` (no `contract_sha256`) builds a
generic scan contract server-side. `assets` holds exactly one `video` asset and, optionally, one `image` asset
(upload it with `media_type=image`; any other combination is 422). CLI:
`proofframe verify --video-only --video clip=/media/clip.mp4 --reference /media/still.png --wait`
(uploads the still as asset `clip-reference`).

The image becomes a hash-bound `canonical_reference` slot and the contract gains one blocking check,
`reference-match` (`observation.kind = "reference_match"`). Without a reference that check does not exist.
One model call compares the still (`REF`) with the clip's first / middle / last frames and reports
`new_prop`, `missing_prop` or `scene_changed`. A report is a review item (`UNCERTAIN`, `verdict: "review"`, severity
carried, cited clip frames), never `FAIL`: one model family agreeing with itself is not proof. A clean answer is
`PASS` citing the three inspected frames plus the reference; a provider error or malformed answer is `ERROR`; a
budget stop is `NOT_CHECKED`. Cost planner entry: `COST["reference_match"]`.

The continuity audit compares shots only. A clip with one detected shot reports `NOT_CHECKED` ("0 shot pairs
compared"), not `PASS`; the run then stays `REVIEW` because the check is blocking.

## ReportEnvelope

```jsonc
{
  "schema_version": "proofframe.envelope.v0.1",
  "run": { "run_id": "...", "run_mode": "live|recorded_replay|synthetic_fixture", "profile": "film",
           "contract_id": "...", "contract_revision": 1, "contract_sha256": "...",
           "started_at": "ISO", "finished_at": "ISO", "previous_run_id": null },
  "report": { /* proofframe_contracts.models.VerificationReport, model_dump(mode="json") */ },
  "report_sha256": "...",
  "decision": { /* PolicyDecision: decision, unresolved, blocking_failures, advisory_findings, run_mode, publish_authorized:false */ },
  "assets": [ { "asset_id": "shot-01", "revision": 1, "sha256": "...", "duration_ms": 60000,
                "url": "/v1/media/<sha>", "lineage": {"source": "...", "offset_ms": 15000, "note": "..."} } ],
  "checks": [ {
      "assertion_id": "caption-01", "target_asset_id": "shot-01", "status": "FAIL", "blocking": true, "global_sentinel": false,
      "source_pointer": "/shots/01/lower_third", "predicate": "...",
      "expected": "approved value (shown to humans, never sent to the observer)",
      "observed": "value the observer reported, or null",
      "observation_question": "exact neutral question sent to the model",
      "scope": {"start_ms": 10000, "end_ms": 25000} | null,
      "focus": {"start_ms": 12000, "end_ms": 20000} | null,   // interval the UI seeks to
      "evidence_ids": ["ev-..."], "trace_ids": ["tr-..."],
      "rationale": "why this status, incl. disagreements",
      "limitations": ["sampled at 1 fps; not exhaustive", "..."],
      "regression": null | {"before": "FAIL", "after": "PASS",
                             "classification": "FIXED|STILL_FAILING|REGRESSION|UNCERTAIN|NOT_COMPARABLE|UNCHANGED_PASS"}
  } ],
  "evidence": [ {  // superset of report.evidence with display data
      "evidence_id": "ev-...", "asset_id": "shot-01", "kind": "frame|clip|metadata",
      "start_ms": 12000, "end_ms": 12042, "sha256": "...", "url": "/v1/media/<sha>",
      "role": "target|context|reference", "label": "F3 @ 00:12.000" } ],
  "traces": [ { "trace_id": "tr-...", "provider": "meta", "model": "muse-spark-1.3",
      "endpoint": "/v1/responses", "purpose": "localize|confirm_frames|...", "http_status": 200,
      "latency_s": 21.3, "usage": {...}, "cost_usd": 0.0153, "cost_basis": "usage*list_price|unknown",
      "remote_request_id": "resp_...", "outcome": "ok|http_error|timeout|invalid_output|refused|budget_exhausted",
      "request_digest": "sha256 of request body without media bytes" } ],
  "coverage": { "mandatory": 5, "pass": 2, "fail": 1, "uncertain": 1, "not_checked": 0, "error": 0, "not_applicable": 0 },
  "cost": { "estimated_usd": 0.05, "unknown_cost_calls": 0, "reserved_open_usd": 0.0 },
  "labels": ["LIVE RUN — real Meta calls", "..."]
}
```

UI rules: show decision AND coverage; unresolved mandatory checks are visible; clicking a check seeks the
target video to `focus.start_ms` (fallback first evidence `start_ms`) and shows evidence frames, expected vs
observed, limitations; run_mode label is always visible; regression classification shown separately.

Decoded technical assertions add `black_duration_ms`, `freeze_duration_ms` and `silence_duration_ms` to `ObservationSpec.technical_metric` (kind/comparator remain `technical`). `expected` and `tolerance` compare union duration in milliseconds. Existing serialized defaults and contract fingerprints are unchanged.

Their check rows include `technical_measurement` with `value`, source `intervals`, checked `coverage`, `settings`, `detector_version` and `limitations`. Evidence kind `scan` points to the JSON artifact; `inspection=exhaustive` covers only the decoded metric's checked interval, not exhaustive semantic video understanding. Incomplete decoded scope is UNCERTAIN; missing streams or operational failures are ERROR. Technical-only runs need no observer and have zero provider traces/cost. See the runbook for resource bounds and scope behavior.

Audio metering adds `integrated_loudness_lufs` and `true_peak_dbtp` for video-with-audio and audio-only slots. `technical_relation` is `equals` (omitted by default), `at_most` or `at_least`. `tolerance` accepts finite fractional values; integral floats still serialize as integers to preserve legacy fingerprints. Directional relations apply only to numeric technical metrics. Numeric comparisons use exact decimal-derived fractions; unsupported precision is an error rather than an approximate PASS.

Audio `technical_measurement` additionally records `units` and `numeric_resolution` (0.1 from the printed summary); it need not contain event `intervals`. The complete measurement scope is the focus: a whole-scope peak is not a precisely localized transient. Boundary-straddling values and unmeasurable gated/silent audio remain UNCERTAIN. First-stream scope, meter settings and limitations accompany the evidence. No normalization or source-audio repair occurs. The CLI accepts `--audio slot=/path.wav` alongside `--video` through the same asset/job endpoints.
