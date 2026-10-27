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
Spend bounds live in `docker-compose.yml` (`PROOFFRAME_MAX_PROJECT_COST_USD=10`, `PROOFFRAME_MAX_RUN_COST_USD=2`).
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
checks ≈ $0.35 (not yet run live — longest live run so far is 2 min); scoped checks cost far less. The $2/run cap stops a run before overspending (remaining checks
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

```bash
docker compose run --rm api python -m pytest -q -p no:cacheprovider        # 99 tests (no paid calls)
# UI seek check (Firefox/WebKit; Playwright's Chromium lacks H.264):
docker run --rm --network host -e BROWSER=firefox -v "$PWD/e2e":/e2e:ro -v "$PWD/validation/screenshots":/out \
  mcr.microsoft.com/playwright:v1.49.1-jammy sh -c 'cd /tmp && npm i -s playwright@1.49.1 >/dev/null 2>&1 && \
  cp /e2e/seek.mjs . && node seek.mjs http://127.0.0.1:3000 <run_id> <assertion_id> /out/seek.png'
```
