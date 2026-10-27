# Build status

## Gate 0 — done (2026-10-27)
- Seed contract tests: `docker run python:3.12-slim … pip install -e .[dev] && pytest -q` → **60 passed** (pydantic 2.14.1, pytest 9.1.1, jsonschema 4.26.0).
- Meta probes: see `docs/CAPABILITY_PROBES.md` ($0.046 est.).
- Spend bounds (owner-approved 2026-10-27): project $10, run $2. Test clips ≤ 2 min per owner instruction.
- Demo footage: *Tears of Steel* (Blender Foundation, CC-BY 3.0), 720p source sha256 `efa9062d9cdb7a338e40ad530dfdf234806743f29ae6a1a136b97ece4e588e8f`; kept under `../media/`, not in Git.

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
`docker compose run --rm api python -m pytest -q -p no:cacheprovider` → **99 passed** (97 at Gate 3 + 2 temporal-semantics tests) (60 seed + 21 API/DB/jobs/budget on real Postgres
+ 10 core pipeline (fake observer, real ffmpeg) + 6 Meta adapter failure semantics). None of these are perception benchmarks.

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
Credentials: `ProofFrame_V3/.deploy-credentials` + `ProofFrame_V3/.env` (both gitignored, mode 600).

## Owner footage dev run — details private (`private_evaluation/NOTES.md`, not in Git)
A 60 s owner clip with agent-drafted (not owner-approved) assertions exposed a **verifier false positive**: a state-change event
(object breaking) fell between sampled frames, so earlier "intact" frames produced a FAIL. Fix in evaluator 0.4:
`ObservationSpec.temporal="occurs"` (sampled miss → UNCERTAIN, never FAIL) + 0.5 s uniform frame grid for event checks.
Live rerun of that check: PASS with evidence on the correct 0.5 s interval. Existing contract fingerprints unchanged (tested).

## Known gaps / next
- All live runs above used evaluator 0.1; 0.2/0.3 changes (skip not_visible segments, absorb ≤10 s tail window, input-seek frames) are covered only by fake-observer tests.
- Gate 3 did not include a generative shot replacement: REGENERATE_SHOT has no executor here (only the deterministic composite executor).
- SAM is probed but not used in the pipeline; the "blue jacket" zero-record result is an unverified negative.
- Gate 2 partial: coverage ledger, ERROR/NOT_CHECKED semantics, timeout/invalid-JSON/budget tests exist; NOT done: SAM tracking in the pipeline,
  ASR/dialogue checks, story-time vs edit-time, occlusion/allowed-change exceptions, cache keys, a frozen dev/held-out set, 10% PASS audit sampling.
- Frame confirmation uses the same model family as localization → agreement is not independent evidence (stated in every check).
- Evidence is sampled (≈3 frames + 1 fps video), never exhaustive; brief events between samples can be missed.
- Gate 4 (Content Engine adapter, Opus comparison, evaluation table) not started. `production_best_qualified` profile not implemented — runs are `meta_hackathon` only.
- Single tenant/static token; no TLS (loopback only). UI not tested in Chromium.
- Seed change: `Assertion` gained optional `scope` and `observation` (fingerprints of contracts now include these fields).
