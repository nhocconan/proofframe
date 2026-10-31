# ProofFrame runbook (local docker-compose)

## Start / stop

```bash
# from the repository root
# one-time on a fresh checkout: let the container user (uid 10001) write the file-drop dir
mkdir -p dropbox && setfacl -m u:10001:rwx -m d:u:10001:rwx dropbox
docker compose up -d --build db api worker web     # API 127.0.0.1:8080, UI http://127.0.0.1:3000
docker compose stop                                # stop, keep data
docker compose down                                # remove containers, keep volumes (pf_data, pf_db)
```

Secrets: the Meta key is read from `.env` at the repo root (`META_DEV_API`, gitignored) via `env_file`.
Spend bounds live in `docker-compose.yml` (`PROOFFRAME_MAX_PROJECT_COST_USD=100`, `PROOFFRAME_MAX_RUN_COST_USD=15` by default; both are environment-overridable).
Check remaining budget: `curl -H "Authorization: Bearer $PROOFFRAME_API_TOKEN" 127.0.0.1:8080/v1/budget`
(token from `.env`; without that file compose falls back to `dev-local-token`, acceptable only on loopback).

## Public test site (Traefik)

```bash
# .env (gitignored, chmod 600), in addition to META_DEV_API:
#   PROOFFRAME_API_TOKEN=<openssl rand -hex 24>
#   PROOFFRAME_BASIC_AUTH_USERS='proofframe:<htpasswd -nbB bcrypt hash>'
docker compose -f docker-compose.yml -f docker-compose.deploy.yml up -d --build db api worker web
```
Only `web` joins the external `balancer` network; the router `Host(`test-proof-frame.dic.app`)` uses `websecure` + `myresolver`
with a basic-auth middleware. Never route the API publicly (anyone reaching it could spend the Meta budget).

## Test your own 3–5 minute video

1. Copy `demo/contract_template_own_video.json`, edit it:
   - `asset_id` in `assets[]` and every `target_asset_id` must match.
   - `expected` holds the approved value. `observation.subject/attribute` must describe WHERE/WHAT to look at
     without stating the expected value (the model never sees `expected`).
   - Optional `scope` (ms) limits a check to a window — cheaper and more precise. No scope = whole video.
   - `category_equals` needs `expected` inside `vocabulary`; `exact_text_nfc` compares exact text (Unicode NFC,
     dash/quote variants normalised, letters/diacritics/case exact).
   - Events/state changes (something breaks, appears, is handed over): set `"temporal": "occurs"` — a miss in sampled
     frames is UNCERTAIN, never FAIL, and a dense 0.5 s frame grid is added. Default `throughout` = must hold in every clear frame.
   - Keep the `gen-artifacts` (undeclared AI defects inside shots) and `continuity` (cross-shot props, wardrobe, set,
     people) assertions: without them only the listed requirements are checked. Budget ≈ $0.65–0.75 per minute of film.
   - Bump `revision` if you change an approved contract with the same `contract_id` (contracts are immutable).
2. Either use the UI (`http://127.0.0.1:3000/upload`: asset_id + mp4 + contract) or the CLI:
   ```bash
   mkdir -p media/clips && cp my_video.mp4 media/clips/ && cp my_contract.json dropbox/
   docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api \
     proofframe verify --contract /dropbox/my_contract.json --video my-video=/media/clips/my_video.mp4 --wait
   ```
3. Open `http://127.0.0.1:3000/runs/<run_id>`; click a check to seek to its evidence.

Cost guide (estimates from measured usage × list price): each visual check costs ≈ $0.015 per minute of its
scope (1 fps video pass, 640 px) + ≈ $0.005 frame confirmation. A 5-minute video with 4 whole-video visual
checks ≈ $0.35 (not yet run live — longest live run so far is 2 min); scoped checks cost far less. The $15/run default cap stops a run before overspending (remaining checks
become NOT_CHECKED, never PASS). Long videos are split into ≤60 s windows with 3 s overlap.

## Repair round trip (file-drop)

```bash
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api proofframe export-repair <run_id> --out /dropbox/req.json
# request lands in dropbox/requests/; the allowlisted executor (correct | faulty_text | drops_audio) runs it:
docker compose --profile repair run --rm -e EXECUTOR_VARIANT=correct executor python -m proofframe.repair.executor --once
# executor uploads a new asset revision, writes dropbox/receipts/<id>.json, submits it → regression run
```
Max 2 attempts per target along a run chain (3rd → HTTP 409, escalate to human review).

## Tests

### Decoded technical QC

`demo/contract_decoded_qc.json` is a template, not approved production intent. Review its thresholds and scopes before submitting it: intentional black, static holds and silence are legitimate in many films. Assertions compare the measured union duration with `expected` ± `tolerance`, in milliseconds. Use separate scoped assertions for approved portions rather than silently exempting findings after a run.

```bash
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api proofframe verify --contract demo/contract_decoded_qc.json --video delivery=/media/owned-delivery.mp4 --wait
```

The shared verifier decodes the selected first stream with FFmpeg; no model credential or paid call is needed for technical-only checks. `black_duration_ms`, `freeze_duration_ms` and `silence_duration_ms` produce source-bound JSON scan artifacts, checked intervals, settings and detector version. In the UI open the check's details to download measurements or seek to its first flagged interval. The CLI uses the same report.

Current bounds: 300 s per scan scope, visual frame size at most 3840×2160, 300 s subprocess timeout. Default detectors exclude black events shorter than 100 ms, freezes shorter than 500 ms and silence shorter than 200 ms; thresholds are recorded in evidence. Missing required audio, decode failures and invalid scopes produce ERROR. Non-frame-aligned scopes may begin at the next decoded frame: incomplete coverage is UNCERTAIN and cannot PASS. These heuristics do not qualify speech intelligibility, lip-sync, artistic quality or perception accuracy.

### Audio delivery measurements

`demo/contract_audio_qc.json` is a draft for an audio-only slot. It illustrates −23 LUFS ±0.2 LU and a maximum −1 dBTP. Approve the delivery targets before use; these values are not universal streaming settings or a certification claim. The same observations work on video slots with an audio stream.

```bash
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api proofframe verify --contract demo/contract_audio_qc.json --audio master-audio=/media/owned-master.wav --wait
```

`integrated_loudness_lufs` and `true_peak_dbtp` use FFmpeg metering without changing source audio. `technical_relation` is `equals` (default), `at_most` or `at_least`; tolerance accepts finite fractional values. The first audio stream is measured for at most 300 s per scope. A 0.1-unit summary has a ±0.05 rounding interval: a measurement straddling an approved boundary is UNCERTAIN. This accounts for printed precision, not calibrated instrument accuracy. Unmeasurable silence/sub-gated loudness is UNCERTAIN; absent audio or failed decoding is ERROR.

Whole-programme loudness requires a whole-programme scope. Do not average LUFS from separate shots to claim programme compliance. Longer inputs require an explicitly supported full-duration implementation; these bounds do not silently split and average. Peak/loudness measurements do not prove intelligible dialogue or synchronized lips.

### Dialogue against an approved script

`demo/contract_dialogue_qc.json` is a template, not approved intent. For each locked script line, add one
`kind: "dialogue"` assertion against the delivery asset, use the speaker description as `subject`, put the
exact approved line in `expected`, and bind `scope` to that line's source-time shot/scene interval. The ASR
request receives the scoped audio and optional `language_bias`, never the expected line. Double transcription
is on by default; set `double_transcription: false` only when the contract deliberately accepts the weaker route.

PASS means the normalized transcript matches the locked line. FAIL means two agreeing transcriptions clearly
contradict it, with an expected-versus-heard token diff as the retake note. Empty speech recovery or materially
disagreeing biased/unbiased passes is UNCERTAIN and therefore REVIEW, flagged as possibly unintelligible. Two
near-identical transcripts in different declared scopes also produce REVIEW on both lines unless either assertion
sets `allow_repeat: true`. Provider/decoding errors are ERROR and budget refusal is NOT_CHECKED; neither can PASS.

Audio is extracted from the first audio stream as mono 16 kHz WAV. A dialogue scope must be explicit, within the
asset, and no longer than the Meta file endpoint's 10-minute limit; longer scopes ERROR rather than truncate. Muse Voice evidence has turn-level
timestamps only. This check does not establish named-speaker identity, word alignment, mouth movement, or lip sync.

### Offline evaluation and judge controls

```bash
python scripts/score_findings.py report.json labels.json --json --controls controls.json
```

Install the project's dependencies first or run this in the app environment. Labels contain `defects` with `id`, `class`, `t` in seconds, `accept_categories` and optional `keywords`. Each distinct claim can match at most one label; reference-shot context does not locate a defect. Confirmed detections and surfaced review items have separate results. Repeated claims merge only with matching category/entity, overlapping intervals and an explicit shared `root_cause_id` or identical normalized description.

Precision is unknown while unmatched claims lack adjudication. An owner-confirmed complete annotation set can explicitly set `fully_annotated: true`; otherwise provide `adjudications` keyed by finding `id` or `assertion_id:zero_based_index`, with `false_positive`, `true_positive` or `uncertain`. Human decisions constrain matching. A true-positive label gap adds a precision positive, not a supplied-label recall hit. Conflicting duplicate decisions remain unresolved.

Controls JSON has `order_records` (`pair_id`, `order`: `AB`/`BA`, `verdict`: `same`/`different`/`abstain`/`error`) and `identical_records` (`pair_id`, `verdict`). Pair IDs must bind identical evidence, prompt, model and settings except ordering; the tool analyzes records without making calls. Reported rates keep abstention/error counts and decisive denominators. Machine-readable results include input hashes and evaluator version. These diagnostics do not create a holdout or establish superiority over Opus.

### Frozen-cohort baseline comparison

```bash
python scripts/evaluate_dataset.py private/my-evaluation/manifest.json --split holdout --json
```

Copy `examples/evaluation_dataset/manifest.template.json` to an ignored evaluation directory and replace every placeholder with real local files and hashes. The template is intentionally incomplete and cannot produce a valid evaluation. Paths resolve relative to the manifest directory and cannot escape it; keep private footage and derived artifacts outside Git.

Each case binds one target asset, exact media bytes, contract, labels and a complete set of baseline reports. Reports use the ProofFrame envelope shape and must contain checks for that case's target. All cases are validated before filtering a split. Episode/source groups and identical media hashes cannot cross development/calibration/holdout boundaries. Byte-bound snapshots do not prove that a holdout was locked before earlier tuning; preserve that history separately.

For multiple baselines, label files use `adjudications_by_baseline: {"opus-workflow": {"check:0": "false_positive"}, "proofframe": {"check:0": "true_positive"}}`. Each map refers only to that baseline's finding IDs. A shared nonempty `adjudications` map is rejected across multiple baselines. Missing or conflicting decisions remain unresolved. Annotation provenance is declared as human-adjudicated, agent-draft or synthetic; a manifest string alone does not prove human review.

Output separates per-case and aggregate confirmed/surfaced metrics, includes manifest/report/label/media hashes and counts source groups. Missing costs, unknown-cost calls and unmeasured owner review remain unknown. Reported estimates do not establish complete generation/repair/review costs. The tool makes no provider calls or qualification verdict; compare identical evidence for model selection and separately measure full systems before claiming savings.

```bash
docker compose run --rm api python -m pytest -q -p no:cacheprovider        # no paid calls
# UI seek check (Firefox/WebKit; Playwright's Chromium lacks H.264):
docker run --rm --network host -e BROWSER=firefox -v "$PWD/e2e":/e2e:ro -v "$PWD/validation/screenshots":/out \
  mcr.microsoft.com/playwright:v1.49.1-jammy sh -c 'cd /tmp && npm i -s playwright@1.49.1 >/dev/null 2>&1 && \
  cp /e2e/seek.mjs . && node seek.mjs http://127.0.0.1:3000 <run_id> <assertion_id> /out/seek.png'
```
