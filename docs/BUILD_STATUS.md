# Build status

## Industrial audio QC and frozen cohorts (evaluator 0.15, 2026-10-29)
- Researched official Vidchecker/BATON capabilities, EBU R128 v5 PDF, TwelveLabs Analyze, WhisperX README and evidence-grounding research abstracts. Decisions: RESEARCH_AND_DECISIONS §6; sources S37–S43. No vendor product benchmark or new model adapter is claimed.
- Shared core now measures `integrated_loudness_lufs` and `true_peak_dbtp`, with decoded coverage, first-stream settings, 0.1-unit printed resolution and source-bound JSON evidence. Added finite fractional tolerances, exact numeric limits and directional relations; ambiguous boundary measurements remain UNCERTAIN. The original voice pipeline is untouched; metering performs no normalization.
- Audio-only assets now receive duration/provenance bindings; CLI `--audio` uses the existing upload/job endpoints. Draft delivery contract: `demo/contract_audio_qc.json`. Example values require approval for the destination and do not establish EBU compliance.
- Real execution: 60 s licensed Tears of Steel excerpt sha256 `a78ef51cdf2572129b8d9a94d27c6dff0f1a947f628bd39fe18e1d4656601071` measured **−14.6 LUFS / −0.1 dBTP**, both FAIL against the illustrative −23±0.2 LUFS / ≤−1 dBTP contract. No provider calls, estimated provider cost $0; this is decoded integration evidence, not a perception benchmark or artistic-quality judgment. Report retained at gitignored `private/industrial/results/tos_audio_measurement.json`.
- Frozen-cohort CLI: `scripts/evaluate_dataset.py`; validates media/label/report hashes, asset+contract bindings, complete baseline cohorts, split separation and baseline-specific adjudications. Missing resource costs/review measurements remain unknown; no owner-adjudicated holdout or Opus comparison has been executed. Manifest template is explicitly incomplete.
- Final gate: `docker exec -w /tmp/pf-industrial -e PYTHONPATH=/tmp/pf-industrial/src proofframe-api-1 python -m pytest -q -p no:cacheprovider .` → **306 passed, 1 existing Starlette/AnyIO deprecation warning, 41.88 s**. SHA-256 checks: 52/52 checkout Python source/test files match the tested snapshot. Runtime FFmpeg is 7.1.5; worker smoke probes also used host FFmpeg 8.0.1.
- Both audio and decoded-QC demo contracts passed Pydantic and JSON Schema validation; committed schema equals current Pydantic export. Exporter also validated 4 schemas / 10 existing synthetic examples. `git diff --check` passed. Frontend unchanged in this wave: prior type/build gates retained, not rerun; no browser or new perception evaluation performed.
- Independent review found and resolved 3 issues: integral-float legacy fingerprint changes, adjudication leakage between baseline-local IDs, and default Decimal precision allowing an approximate PASS. Regression coverage and scoped re-review found no remaining concrete issue. Working evidence: `private/industrial/results/`.
- Host Python/pytest discovery failed as already documented; FFmpeg filter-page fetch timed out, so installed filter help and actual execution verified supported options. No new dependencies/weights imported, no paid calls, no deployment or pre-existing service changes. Temporary verification snapshots/archives removed; private logs and the measurement report retained.

## Qualification infrastructure and decoded QC (evaluator 0.14, 2026-10-29)
- Shared core: decoded black/freeze/silence union durations, source intervals, checked coverage, versioned settings and JSON scan artifacts. Technical-only runs no longer instantiate a paid observer. A runnable draft contract is `demo/contract_decoded_qc.json`; approve thresholds/scopes for real delivery requirements.
- Fail-closed safeguards: local provider JSON Schema validation (including non-finite numbers); invalid verdict/severity and unresolved entity correspondence cannot PASS. Incomplete decoded scope becomes UNCERTAIN. Existing contract fingerprint regression remains green.
- Offline evaluator: independent confirmed/surfaced tracks, one-to-one maximum matching, conservative claim deduplication, human adjudication precedence, unknown precision for unresolved findings, hash-bound outputs and offline AB/BA/identical-pair controls. This implements diagnostics, not a held-out perception benchmark.
- Final integrated snapshot: `docker exec -w /tmp/pf-improvement -e PYTHONPATH=/tmp/pf-improvement/src proofframe-api-1 python -m pytest -q -p no:cacheprovider` → **224 passed, 1 Starlette/AnyIO deprecation warning, 28.89 s**. SHA-256 comparison: all 46 checkout Python source/test files match this snapshot. New QC tests use real FFmpeg on explicitly synthetic media; other perception calls remain fake/mocked.
- Frontend: `docker exec proofframe-web-1 node /app/node_modules/typescript/bin/tsc --project /tmp/pf-improvement-web/tsconfig.json --noEmit` → 0; `docker exec -w /tmp/pf-improvement-web -e NEXT_TELEMETRY_DISABLED=1 proofframe-web-1 npm run build` → 0. The UI distinguishes decoded measurements and links the JSON evidence. Browser interaction/screenshot checks were not rerun.
- Schema exporter → 4 valid schemas and 10 synthetic examples; committed contract schema refreshed. Provider schema validation uses jsonschema, already pinned in requirements.lock and now declared as a runtime dependency.
- Independent integration review found 3 issues (malformed judgments, adjudication precedence, over-broad deduplication); fixes and regression cases reviewed, no remaining blocker in the scoped re-review. Working logs: gitignored `private/improvement/results/`.
- Tool failures: host Python/pytest absent as noted below; Docker copy cannot access tmpfs in read-only-root containers, so snapshots were streamed through exec into /tmp. No running app source, service, credentials or deployment changed; no paid calls or new model-quality results. Held-out Meta/Opus comparison, specialist qualification and production readiness remain open.
- Temporary source/build snapshots and transfer archives removed after verification; logs retained in private/improvement/results. Existing service containers remained running throughout.

## Independent implementation audit (2026-10-29)
- Assessment: `docs/IMPLEMENTATION_SOTA_AUDIT_2026-10-29.md`; SOTA and production qualification remain unestablished. Reviewed WHY-003 historical art/final reviews and owner-rejection lessons; no private media copied.
- `docker exec proofframe-api-1 python -m pytest -q -p no:cacheprovider` → **123 passed, 1 Starlette/AnyIO deprecation warning, 21.04 s**. SHA-256 comparison: 41/41 checkout Python source/test files match the tested container.
- Host checks unavailable: `python -m pytest -q -p no:cacheprovider` → 127 (python absent); `python3 -m pytest -q -p no:cacheprovider` → 1 (pytest absent).
- `docker exec proofframe-web-1 npx tsc --noEmit` → 1, compiler help; runtime image omits source/tsconfig. Fresh frontend build/type check not performed. No runtime code changed, no paid calls, no new services, no new perception benchmark.

## Gate 0 — done (2026-10-27)
- Seed contract tests: `docker run python:3.12-slim … pip install -e .[dev] && pytest -q` → **60 passed** (pydantic 2.14.1, pytest 9.1.1, jsonschema 4.26.0).
- Meta probes: see `docs/CAPABILITY_PROBES.md` ($0.046 est.).
- Spend bounds (owner-approved 2026-10-27): project $10, run $2. Test clips ≤ 2 min per owner instruction.
- Demo footage: *Tears of Steel* (Blender Foundation, CC-BY 3.0), 720p source sha256 `efa9062d9cdb7a338e40ad530dfdf234806743f29ae6a1a136b97ece4e588e8f`; kept under `media/` (gitignored), not in Git.

## Gate 1 — done (live, 2026-10-27)
Stack: `docker-compose.yml` (postgres:16, FastAPI api, lease-based worker, Next.js 15 web, file-drop executor). Footage: 60 s
excerpt of Tears of Steel (source 0:15–1:15) with a **seeded composite defect on real footage**: lower-third caption
"…Celina…" where the approved text is "…Celia…". Contract: `demo/contract_tos_bridge.json` (6 assertions).

| Run | Media (sha256) | Result | Est. cost |
|---|---|---|---|
| `run-acf67e0ab88143719969` (v1) | 18df9f1c… | **BLOCK** — caption-01 FAIL (observed "Celina", 3/3 clear frames @13.2/17.4/21.6 s); wardrobe-01 PASS (blue, 3/3); title-01 PASS ("40 YEARS LATER" @27.4–29.8 s; real cut ≈27.5 s); eyes-01 UNCERTAIN (eyes not readable at sampled frames — the ambiguous counterexample); tech-duration/audio PASS | $0.0369 (8 calls, all HTTP 200, 3.4–7.2 s) |

UI seek (Playwright 1.49.1, `e2e/seek.mjs`): caption-01 → currentTime 13.2 s ∈ [13200, 21642] ms; title-01 → 27.4 s ∈ [27400, 29842] ms,
in Firefox and WebKit. Screenshots: `validation/screenshots/gate1_seek_*`. Chromium (Playwright build) cannot decode H.264 → not tested there.
Report: `validation/runs/gate1_v1_live.json`.

## Gate 3 — demonstrated (live)
| Chain | Run | Repair executed | Classification | Decision | Est. cost |
|---|---|---|---|---|---|
| A | `run-a7905e68dc474245a26d` | FIX_COMPOSITE, executor=correct → shot-01 r2 a6530e9a… | caption-01 FAIL→PASS **FIXED**; 4 others UNCHANGED_PASS | ELIGIBLE (not a publish authorization) | $0.0363 |
| B | `run-c90f57fa21ae4eedaeb3` | — (v1 on slot shot-01b) | same verdicts as Gate 1 run (repeatability on identical bytes: 6/6) | BLOCK | $0.0368 |
| B | `run-97af59e2be83472ab4b0` | attempt 1, executor=faulty_text ("Cella") | caption-01 **STILL_FAILING** (observed "Cella") | BLOCK | $0.0360 |
| B | `run-70042c1c1cf740e4bdf2` | attempt 2, executor=drops_audio | caption-01 FIXED; tech-audio PASS→FAIL **REGRESSION** | BLOCK | $0.0368 |
| B | (attempt 3) | refused: HTTP 409 "repair attempt cap reached (2)" | — | — | $0 |

Executor variants are deliberately faulty test executors (labelled in every receipt), running real ffmpeg on real footage.
Receipts validated by seed `validate_receipt` (plan hash, stale input, new revision, same media type).

## Long video (2 min, owner cap)
`run-be2942c1829a4ad0a5f5`, `demo/contract_tos_long_2min.json`, 120 s clip (8327502c…): whole-video assertions over 2 windows.
main-title PASS @52.2–54.0 s (real ≈50 s); sniper-jacket PASS @67.5 s and 102.1 s (minute-2 times mapped correctly: source 1:22.5 = clip 67.5 s);
ELIGIBLE, $0.0762. 3–5 min videos use the same windowing; **not run live** (owner limited tests to ≤2 min).

## Tests
`docker compose run --rm api python -m pytest -q -p no:cacheprovider` → **104 passed** (60 seed + 21 API/DB/jobs/budget + 12 core pipeline + 6 Meta adapter + 5 artifact-scan incl. parametrized cases) — API tests use real Postgres; pipeline tests use a fake observer on real ffmpeg media. None of these are perception benchmarks.

## Spend
Ledger (`GET /v1/budget`, end of day): $0.410 settled (was $0.305 before deployment/dev runs) of $10 project cap (incl. $0.046 Gate 0 probes); 0 unknown-cost calls. All amounts are usage × list price estimates.

## 5-minute readiness (no paid calls)
- Real 5-min file (tos_0015_0515.mp4, 85.8 MB): uploaded through the UI route → run `run-66fcb375ccd24409bd7b` (technical checks only) ELIGIBLE, duration 300000 ms; Range 206 at byte 85,000,000.
- Frame extraction at 290 s: 6.5 s (output seek) → 0.12 s (input seek), identical PNG; switched (evaluator 0.3).
- Full pipeline on the 5-min file with the fake observer: 24.6 s local processing, 6 windows per whole-video check, no budget refusal.
- A live 5-min run (est. ≈ $0.35 for 4 whole-video visual checks) has NOT been executed (owner capped tests at 2 min).

## Other live-stack checks
- Stale receipt replay (chain B attempt-1 receipt after attempt 2): HTTP 422 "repair base is no longer the current asset snapshot".
- Regression UI: `validation/screenshots/gate3_regression_view_firefox.png` shows REGRESSION / FIXED / UNCHANGED_PASS / UNCERTAIN separately.
- Lockfiles: `requirements.lock` (pip freeze of the built app image), `web/package-lock.json`.

## Public test site (2026-10-27)
`https://test-proof-frame.dic.app` via the host Traefik (`docker-compose.deploy.yml`, network `balancer`, Let's Encrypt `myresolver`).
Only the web UI is routed, behind Traefik basic auth; API stays internal/loopback. Checks: no auth → 401, wrong password → 401,
auth → 200, `/media` Range → 206, cert issuer Let's Encrypt (notAfter 2027-01-25), `http://<host>:8080` unreachable from outside,
old dev token → 401. Playwright (Firefox) seek on the public URL: caption-01 → 13.2 s ∈ [13200, 21642] ms.
Credentials: `private/deploy-credentials` + `.env` (both gitignored, mode 600).

## Owner footage dev run — details private (`private/evaluation/NOTES.md`, not in Git)
A 60 s owner clip with agent-drafted (not owner-approved) assertions exposed a **verifier false positive**: a state-change event
(object breaking) fell between sampled frames, so earlier "intact" frames produced a FAIL. Fix in evaluator 0.4:
`ObservationSpec.temporal="occurs"` (sampled miss → UNCERTAIN, never FAIL) + 0.5 s uniform frame grid for event checks.
Live rerun of that check: PASS with evidence on the correct 0.5 s interval. Existing contract fingerprints unchanged (tested).

## Generation-artifact scan (evaluator 0.5–0.7, live)
Trigger: the owner found an obvious AI defect (hands with no visible owner, owner clip @≈5–8 s) on a run that showed PASS — that run
only checked one declared assertion and there was no undeclared-defect scan at all. Added `generation_artifact_scan`
(`src/proofframe/verify/anomaly.py`): 2 fps blind video hunt + independent 2 s frame grid + skeptical adjudication on 1280 px frames
with a context frame. UI now warns on partial runs and on runs without a scan.

| Clip | Evaluator | Result | Est. cost |
|---|---|---|---|
| Owner clip (private) | 0.5 | FAIL — confirmed object/major @48–50 s (bottle both shattered and intact in one shot: a real defect the agent had missed); **missed the hand insert @5–8 s** (prompt excluded "plausibly off-frame" limbs) | $0.070 |
| Tears of Steel 60 s (real live action, control) | 0.5 | PASS — 1 grid candidate ("floating hand") correctly rejected by adjudication | $0.059 |
| Owner clip | 0.6 | hand insert now a candidate (video + grid) but adjudicator **rejected** it, contradicting the first pass on who owns the hand | $0.076 |
| Tears of Steel | 0.6 | UNCERTAIN — robot-arm close-up flagged as ownership/unclear → REVIEW | $0.062 |
| Owner clip, full contract | 0.7 | BLOCK — hand insert → REVIEW item (ownership never auto-cleared); bottle duplicate confirmed | $0.176 |

Measured so far: 2 clips, 1 confirmed true defect found, 1 owner-reported defect missed then surfaced as REVIEW, 0 confirmed false
positives, 1 REVIEW item on real footage (robot hand). This is not a benchmark; precision/recall are unmeasured.

## Cross-shot continuity audit (evaluator 0.8–0.12, live)
SOTA review: `docs/SOTA_CONTINUITY_REVIEW.md` (research worker; sources marked verified/secondary/unverified).
Implementation (self-written): `src/proofframe/verify/continuity.py`, `media.detect_shots` (FFmpeg scene score;
12/12 hard cuts found on the owner clip vs manual count). Dev labels frozen before implementation:
`private/evaluation/labels_*.json` (gitignored) (11 defects, 8 must-catch; agent-labelled, owner unconfirmed).
Scorer: `scripts/score_findings.py`.

| Evaluator | Run scope | Must-catch surfaced | Live-action control false FAIL | Est. cost | Wall |
|---|---|---|---|---|---|
| 0.7 (scan only) | full | 2/8 | 0 | $0.176 | — |
| 0.8 log only | scan+continuity | 2/8 | 0 | $0.227 | — |
| 0.9 pairs + swapped adjudication | scan+continuity | 3/8 (rescored with entity keywords) | 1 (hologram) | $0.458 | — |
| 0.10 intrinsic long-range + insert bridging + VFX clause | scan+continuity | 5/8 | 0 | $0.466 | 216 s |
| 0.10 | full contract | 3/8 (adjudication cap cut 11 of 21 candidates) | — | $0.592 | 309 s |
| 0.11 cap 24 | continuity only ×2 | 3 and 4 cross-shot catches | 0 | $0.585 / $0.599 | 118 / 126 s |
| 0.11 | full contract | 5/8 | — | $0.742 | 287 s |
| 0.12 concurrent assertions | full contract | 4/8 | — | $0.643 | **146 s** |

Persistent misses: D2 furniture swap (1 of 4 runs), D7 person vanishing across an insert (raised by pairs,
rejected at adjudication), D8 bag material. Unlabelled confirmed findings (owner to judge): telephone appearing
on the shop table, bottle growing as it falls, boombox handle color. The dev clip was used for tuning — numbers
are optimistic; no held-out set. Tests: 114 passed.

## Budget plan and partial results (evaluator 0.13)
Problem: on long films the stages that run last (continuity) found the run cap already spent, then raised
NOT_CHECKED and discarded findings already paid for. Parallel calls also held upper-bound reservations
(≈ $0.05 per 4-image call vs ≈ $0.011 real), so the cap refused calls while real spend still had room.
Changes (`src/proofframe/verify/plan.py`, `providers/meta.py`, `verify/anomaly.py`, `verify/pipeline.py`):
- Pre-run plan from free FFmpeg facts (shots, durations) and per-call costs measured on run-ee24dd80868649a4b3b1.
  If the estimate exceeds the remaining budget (`PgBudget.remaining`), knobs shrink in a fixed order (registry
  pairs, cross-shot adjudication cap, grid step, scan adjudication cap); adjacent shot pairs are never cut.
  Plan + reductions are in the envelope (`plan`), on each affected check (limitations) and in the UI.
  Estimates: 60 s clip $0.88 (measured $0.64; adjudication counted at its cap); 5-min film $2.06 full →
  registry pairs 12 → 6 to fit $2.00. The 5-min figure is an estimate; no 5-min live run yet.
- Budget stop no longer discards work: confirmed findings stay (a confirmed FAIL stays FAIL), otherwise
  UNCERTAIN with "Budget exhausted: X of Y call(s) not made"; NOT_CHECKED only when every call was refused.
- Observer waits for its own in-flight calls to settle and retries before treating a refusal as final.
- Run cap overridable: `PROOFFRAME_MAX_RUN_COST_USD` (default 2).

Live check (owner clip, full r4 contract, worker started with `PROOFFRAME_MAX_RUN_COST_USD=0.30`):
run-435966aa67d14703a7e6 — plan est. $0.93 full vs $0.30 → all 7 reductions, still over (`fits: false`);
spent **$0.259** (≤ cap); 8 declared checks PASS; artifact scan UNCERTAIN (1 of 4 calls refused);
continuity UNCERTAIN (18 of 27 calls refused); decision REVIEW, no PASS on incomplete coverage.
This run predates two display fixes in the committed 0.13 (the "adjudicated" count now counts completed calls
only — it showed "1 adjudicated" for a refused call; the observed text now says the budget ran out instead of
"no surviving defects"). The FAIL-kept-on-budget-stop path is covered by fake-observer tests only.
Tests: `docker compose run --rm -T -v "$PWD/src:/app/src:ro" -v "$PWD/tests:/app/tests:ro" api python -m pytest -q`
→ 123 passed. Same suite in a clean python:3.12-slim container (CI simulation) → 123 passed.
CI: `.github/workflows/ci.yml` (pytest + Postgres service + ffmpeg; web `tsc --noEmit`); no secrets, no paid calls.
Simulated locally on an empty postgres:16 + python:3.12-slim → 123 passed; first GitHub run not yet observed.
Secret scan: gitleaks v8.21.2 over all 5 commits → no leaks; no `.env`/`private/`/`media/`/video paths in history.

## Known gaps / next
- 5-minute film: budget plan exercised only by tests and a low-cap 60 s run; no 5-minute live run yet.
- Gate 3 did not include a generative shot replacement: REGENERATE_SHOT has no executor here (only the deterministic composite executor).
- SAM is probed but not used in the pipeline; the "blue jacket" zero-record result is an unverified negative.
- Gate 2 partial: coverage ledger, ERROR/NOT_CHECKED semantics, timeout/invalid-JSON/budget tests exist; NOT done: SAM tracking in the pipeline,
  ASR/dialogue checks, story-time vs edit-time, occlusion/allowed-change exceptions, cache keys, a frozen dev/held-out set, 10% PASS audit sampling.
- Frame confirmation uses the same model family as localization → agreement is not independent evidence (stated in every check).
- Evidence is sampled (≈3 frames + 1 fps video), never exhaustive; brief events between samples can be missed.
- Gate 4 (Content Engine adapter, Opus comparison, evaluation table) not started. `production_best_qualified` profile not implemented — runs are `meta_hackathon` only.
- Single tenant/static token; no TLS (loopback only). UI not tested in Chromium.
- Seed change: `Assertion` gained optional `scope` and `observation` (fingerprints of contracts now include these fields).

## Video-only auto-contract and episode campaign caps (2026-10-30)

Implemented the bounded P0-1/P0-3 slice only:
- `docker-compose.yml`: project/run defaults are environment-overridable at $100/$15; probe-spend seeding is unchanged. The Postgres ledger remains an operational counted-spend ledger, not Meta-billed lifetime truth.
- `src/proofframe/verify/autocontract.py`, API and CLI: one ingested video can create a deterministic hash-derived contract without client-supplied intent. It contains generic artifact/continuity audits and non-blocking decoded-QC limits only; no expected-bearing visual claim is invented.
- Media over 180 s uses deterministic 90 s scopes for the two visual audits. This reuses existing assertion windows because the API has no approved shot list at run creation; it is not scene-derived segmentation.
- The envelope is labelled `VIDEO_ONLY_NO_BRIEF`; the existing run UI renders an eligible result as “No confirmed defects in sampled scan — nothing was checked against a brief.” The upload form remains unchanged.
- Tests added in `tests/test_autocontract.py` for determinism/fingerprint stability, advisory status, long-media audit chunks, API run creation without a supplied contract, and CLI request/argument validation.

Verification in this workspace:
- `python3 -m py_compile src/proofframe/verify/autocontract.py src/proofframe/api/app.py src/proofframe/cli.py src/proofframe/verify/pipeline.py tests/test_autocontract.py` — passed.
- `git diff --check` — passed.
- `docker compose run --rm -T -v "$PWD/src:/app/src:ro" -v "$PWD/tests:/app/tests:ro" api python -m pytest -q -p no:cacheprovider` — not run: sandbox denied access to `/Users/conan/.colima/default/docker.sock` before container creation.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q -p no:cacheprovider` — not run: no local pytest installation. Creating a lockfile-based environment with `UV_CACHE_DIR=/private/tmp/proofframe-uv-cache uv pip sync --python .venv/bin/python requirements.lock` failed because this sandbox cannot resolve `pypi.org`.
- `npm --prefix web run typecheck` — not run: `tsc` is unavailable because `web/node_modules` is not installed.

No live or paid provider call was made. Remaining verification risk is the unexecuted pytest/Postgres suite and web typecheck; CI or a Docker-enabled checkout must run both before merge.

## Independent verification of P0-1/P0-3 (Muse, 2026-10-31)

- Reviewer fixes after the Codex pass: (1) tests/test_autocontract.py imported the shared API fixtures incompletely (client/settings/engine chain) — aligned with the import block used by tests/test_api_http.py; (2) verify/autocontract.py: decoded-QC advisories are now scoped per 90 s chunk when media exceeds the detectors 300 s scope cap (previously a >300 s video-only scan would ERROR the advisories instead of measuring), with a regression test for a 486 s asset.
- Full suite, run by the reviewer in Docker (compose run, src+tests mounted): **314 passed, 1 warning, 0 errors** (command: docker compose run --rm -T -v /Users/conan/Workspace/proofframe/src:/app/src:ro -v /Users/conan/Workspace/proofframe/tests:/app/tests:ro api python -m pytest -q -p no:cacheprovider).
- Baseline live runs before this change (technical QC only, bash): run-b3ee03d29f6d4c369649 ELIGIBLE on a clean 60 s excerpt; run-cebe314a0de34ab5900b correctly ERROR/REVIEW on a timestamp-broken stream-copy excerpt.

## Dialogue / ASR verification (P0-2, 2026-10-31)

Implemented a blind scoped-audio path for `kind: dialogue`: first-stream mono 16 kHz WAV extraction,
Muse Voice `ENDPOINTING` transcription through the existing atomic reservation/settlement ledger, strict buffered
response validation, NFC/dash/quote comparison with token retake diffs, optional biased/unbiased agreement checks,
and deterministic cross-scope duplicate review with `allow_repeat`. ASR evidence remains turn-level and makes no
speaker-identity, word-alignment, mouth-motion, or lip-sync claim. `demo/contract_dialogue_qc.json` is a template,
not approved production intent.

Verification in this workspace:

- Prerequisite baseline command, before P0-2 edits: `docker compose run --rm -T -v "$PWD/src:/app/src:ro" -v "$PWD/tests:/app/tests:ro" api python -m pytest -q -p no:cacheprovider` — **not run**; Docker API access failed with `permission denied` on `/Users/conan/.colima/default/docker.sock`. The preceding independent P0-1/P0-3 record above remains 314 passed, but is historical, not this run.
- `PYTHONPATH=src:. .venv/bin/python -m py_compile src/proofframe_contracts/models.py src/proofframe/media.py src/proofframe/providers/meta.py src/proofframe/verify/dialogue.py src/proofframe/verify/plan.py src/proofframe/verify/pipeline.py tests/test_dialogue.py tests/test_meta_adapter.py` — passed.
- Pure deterministic dialogue checks (normalized match, changed-token diff, near-empty REVIEW, duplicate similarity) via `PYTHONPATH=src .venv/bin/python` — passed.
- Scoped FFmpeg extraction smoke (2 s stereo/48 kHz synthetic sine → 250–1250 ms mono/16 kHz WAV) — passed; ffprobe measured exactly 1000 ms with an audio stream.
- `git diff --check` — passed.
- `PYTHONPATH=src:. /Users/conan/.hermes/hermes-agent/venv/bin/python scripts/export_schemas_and_examples.py` — passed: `Validated 4 JSON Schemas and 10 synthetic example documents`; `schemas/contract.schema.json` was regenerated by the repository exporter, not hand-edited.
- `PYTHONPATH=src:. /Users/conan/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@39/bin/python -m pytest -q -p no:cacheprovider tests/test_dialogue.py tests/test_meta_adapter.py` — **23 passed in 0.37 s**, no paid calls. This includes generated-schema acceptance/rejection, provider validation/budget behavior, dialogue outcomes, duplicate review/allow-repeat, and ASR plan pricing.
- Full local pytest attempt with the same interpreter — **stopped during collection with 4 errors** because that unrelated read-only environment lacks SQLAlchemy (`test_api_http.py`, `test_api_jobs.py`, `test_api_support.py`, `test_autocontract.py`). The prescribed Docker full suite remains blocked by socket permission, so a complete post-change suite result is not available in this sandbox.
- Non-database local sweep excluding those four modules — **278 passed, 18 failed in 17.05 s**. All 18 failures are in pre-existing decoded audio/technical tests under the host FFmpeg: FFmpeg 8 rejects the suite's `-vsync` option, and several generated audio fixtures are unreadable/measure differently. The focused dialogue/media extraction tests pass on the same host; the Docker image remains the required reproducible gate.
- No live/paid ASR smoke was attempted: although the focused fake gate passed, the required full suite did not. Subtitle grounding and live budget checks were intentionally skipped.


## Addendum 2026-10-31 — independent review fixes (Muse orchestrator)

- **pf-verify-0.17**: dialogue comparator folds case/punctuation (typographically
  clean ASR previously FAILed locked lines over a trailing period); continuity
  audits respect their scope (chunked video-only runs re-audited the whole film
  per chunk, duplicating findings and multiplying continuity cost); per-run
  scratch dirs are always removed (the leak filled the worker's 2 GB /tmp and
  ERRORed 20 checks of run-009b7aae9d9d43cbbd54 with "No space left on device");
  decoded-QC coverage tolerance is one frame duration (a fixed 1 ms bound
  ERRORed clean concat re-encodes).
- **Suite**: full Docker suite green — 331 passed, including new regression
  tests for all four fixes. The 18 host-run FFmpeg failures reported earlier
  do not reproduce in the Docker reference environment.
- **P0-4 (dialogue half)**: `scripts/compile_edl_contract.py` compiles a
  workprint EDL into a dialogue contract deterministically; on the real C01
  production EDL it reproduces the hand-built contract's 13 assertions exactly.
- **Baselines**: run-7e1df17b73a44464a1c3 (video-only, V4 draft) BLOCK $11.8134,
  adjudication in `private/RUN1_ADJUDICATION.md`; run-009b7aae9d9d43cbbd54
  (contract, V4 draft) BLOCK $3.5555 with coverage crippled by the scratch
  leak — clean re-run in flight. Project cap raised to the author's $140.

## Dialogue Scribe voting and Vietnamese number canonicalization (2026-10-31)

- Added optional ElevenLabs Scribe v2 as an independent dialogue ASR provider. Its scoped-WAV request and response are validated locally; word timestamps are exposed in `provider_transcripts`. Missing credentials retain Meta-only operation with an explicit single-provider limitation, and Scribe errors produce `UNCERTAIN` rather than aborting or silently passing a check.
- Dialogue comparison now canonicalizes Vietnamese digit sequences, positional numbers, and time expressions while preserving ambiguous year-noun `năm`, `rưỡi`, and real word/digit differences. Provider-level voting treats Meta biased/unbiased passes as one provider; a split provider cannot FAIL, independent providers must agree on the same differing reading to FAIL, and the historical two-agreeing-Meta-pass FAIL remains only when Scribe is disabled.
- Scribe duration pricing is reported separately at $0.22/audio-hour through `cost.external_cost_usd` and `external_line_items`. It does not reserve or settle the Meta budget ledger. Evaluator tag: `pf-verify-0.18(...scribe-vote,number-canon...)`.

Verification in this workspace:

- `/opt/homebrew/bin/python3 -m pytest tests/test_dialogue.py tests/test_elevenlabs.py -q` — not run: that interpreter has no pytest installation.
- `PYTHONPATH=src:. /Users/conan/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@39/bin/python -m pytest tests/test_dialogue.py tests/test_elevenlabs.py -q -p no:cacheprovider` — **29 passed**; fake HTTP/ASR only, no paid calls.
- Same interpreter with `tests/test_meta_adapter.py tests/test_budget_plan.py tests/test_core_pipeline.py` added — **66 passed**.
- `.venv/bin/python -m compileall -q src/proofframe tests/test_dialogue.py tests/test_elevenlabs.py` and direct canonicalization/voting probes — passed.
- Docker suite — not run in this sandbox; the parent agent must run the Compose gate because the Docker socket is unavailable here.

## Addendum 2026-10-31 (Muse verification of Scribe + voting + number canon)
- Full Docker suite on final tree: **352 passed, 0 failed**. One boundary fix during verification: decoded-QC coverage tolerance tightened from 1.0x to 0.5x median frame duration (a full missing frame must still fail; sub-frame seam jitter still passes).
- Live dialogue re-run on C01 workprint: run-d10a4fe125264aed938c = BLOCK, Meta $0.006832 + external Scribe $0.004162 (separate ledger). 8 PASS / 1 FAIL / 4 UNCERTAIN (was 5/4/4 pre-Scribe).
- Scribe broke the s04 tie: Scribe hears "1995" (the locked digit-by-digit year), Meta hears "1999" in both passes -> UNCERTAIN, evidence favours the line being correct.
- s04b FAIL is now corroborated by two independent providers + word timestamps: the word "hội" is absent from the workprint audio at the 15.83s edit boundary (film team found it present in the source take -> suspected edit trim). Referred to the film team.
- Known follow-ups: pad dialogue scopes (~1s tail) for lines finishing over a cut (s10 truncation class); vầy/vậy dialect rendering fold (cosmetic; does not change verdicts while another provider differs).

## 2D cartoon calibration, Scribe language fix, key-text coverage (pf-verify-0.19, 2026-10-31)

Branch `feat/key-text-coverage-why003-calibration`. Film: a private, unreleased 2D cartoon, 211.3 s,
sha256 `6298bf55181fea6c01ec2a7fb9587d7b8fd464729c4f8a55db94f108bcdc3219`. No media, frames, contract text or
labels are committed; they stayed in gitignored `media/`, `dropbox/` and the owner's production repo.

- **Bug found before the paid run (code reading):** the Scribe adapter sent `language_code: "vie"` for every
  contract, so English dialogue would be decoded as Vietnamese. Now the contract's `language_bias` maps to an
  ISO 639-3 code (`vie`, `eng`; unknown → no code, auto-detect); free-text bias is still never sent.
  Tests: `tests/test_elevenlabs.py`, `tests/test_dialogue.py::test_pipeline_sends_contract_language_to_scribe`.
- **New `min_coverage` (0 < x ≤ 1) on on-screen text / visual attributes held throughout a scope:** uniform grid of
  4–16 frames (`compare.coverage_grid`, one per 250 ms; model hints not used), `compare.decide_coverage`: PASS if
  matched/sampled ≥ x with no differing reading; FAIL only with ≥ 1 clear match and ≥ 2 frames with no such
  text, and even counting unreadable/differing frames as misreads the fraction stays < x; else UNCERTAIN (or the
  existing exact-value FAIL when the wrong text is held). Report row gains `coverage`; UI shows "read in m of n
  evenly spaced frames". Plan counts the larger confirmation. Field omitted from fingerprints when unset (stored
  fingerprint test unchanged). Tests: `tests/test_text_coverage.py` (9).
- **Isolated stack:** `docker compose -p pfcal -f docker-compose.yml -f private/compose.cal.yml up -d --build db api
  worker` (own image tag `proofframe-app:cal`, own volumes, no published ports, cpus db 1 / api 2 / worker 4,
  caps $8 project / $3.5 run set in the override; the running public stack was not touched).
- **Live run 1** `run-760e05bcc4da41baba85`, full contract (24 exact-text, 52 English dialogue, 4 prop/character,
  artifact scan, continuity, has-audio): BLOCK, **$2.0954** Meta (plan estimate $2.654) + **$0.0113** Scribe,
  started 04:36:54Z, finished 04:46:35Z (580 s). 54 shots, 93 pairs, 24 adjudications.
  Against 17 defects from two independent blind model audits (labels, NOT owner-confirmed): 1/5 majors (prop held
  by an ownerless hand, artifact scan, blind), 1/12 minors (prop missing in 2 of 6 frames, declared check written
  after reading the audits). 2/10 of the visual defects. False blocking: 3 (agent adjudication from frames);
  unresolved: 4. Text 24/24 PASS; dialogue 44 PASS / 1 FAIL (invented name, both ASRs agree on another spelling) /
  7 UNCERTAIN (Meta ASR repeated or misheard words; Scribe matched the script on 5 of 7).
  `python scripts/score_findings.py /dropbox/…/report.json /dropbox/…/labels.json` (in the api container) →
  confirmed matched 1/17, precision unknown (5 unresolved roots).
- **Live run 2** `run-792628c2b85643e5a744`, the 24 text assertions with `min_coverage: 0.9`: **$0.4261**, 157 s
  wall. 22 PASS at 100 % of 5–16 frames; 2 FAIL where the contract window started before the text was due
  (first match 1.15 s / 1.06 s into the window): correct measurement, over-strict contract, fixed in the
  contract builder. No real coverage defect existed in this film, so this proves timing measurement, not a catch.
- **Meta total this entry: $2.5215** (ledger 2.556229 − 0.04597 probe seed).
- Gates: `docker compose -p pfcal … run --rm -T -v <src,tests,scripts,schemas,demo,examples,profiles,validation,pyproject.toml>:/repo api sh -c 'cp -r /repo /tmp/r && cd /tmp/r && PYTHONPATH=/tmp/r/src python -m pytest -q -p no:cacheprovider'`
  → **363 passed, 1 warning, 55.21 s** (Postgres from the pfcal stack). First attempt mounting the whole repo
  failed: `cp: cannot open '/repo/.env'` (permission) — secrets are not copied into test containers.
  Web: `docker run --rm --cpus 2 -v $PWD/web:/src:ro node:22-slim sh -c 'cp -r /src /w && cd /w && npm ci && npx tsc --noEmit'` → npm ci 0, tsc 0.
  Schemas: `python scripts/export_schemas_and_examples.py` → 4 schemas / 10 examples valid; `schemas/contract.schema.json` regenerated.
  Earlier partial gate `pytest tests/test_elevenlabs.py tests/test_dialogue.py` → 1 failure that was only the
  test container lacking `schemas/` (not mounted); passes in the full gate.
- Not done: ASR word timestamps are not yet used to place a coverage window (the window comes from the
  contract); object provenance across cuts (props popping in at a cut) remains the most-missed class.
