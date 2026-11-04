# ProofFrame

ProofFrame checks AI-generated and edited videos for visual defects, continuity mistakes, wrong captions, and mismatched dialogue before you publish them. Every issue it reports points to the exact frame and timestamp in your video so you can verify it in seconds.

## Try it

Live workbench: **https://proofframe.dic.app**

Reviewer login (basic auth, shared demo account):
- User: `demo`
- Password: `pf-demo-2026`

The demo site runs the code in this repository with small spend caps. Sample contracts live in [`demo/`](demo/); video footage is kept outside Git. A live walkthrough run recorded in the submission video is logged as `run-d48a881de32d4aeab001` in [`docs/RUN_HISTORY.md`](docs/RUN_HISTORY.md) (`BLOCK`, $0.6403 estimated).

## Check a video

Checking a clip in the web workbench takes less than a minute to start and needs no setup or JSON configuration:

1. Open the workbench and click **New verification**.
2. Choose an MP4 video file.
3. Optionally paste your script, brief, or scene notes so the checker understands what the video is supposed to show.
4. Click **Upload and verify**.

When the run finishes, ProofFrame gives a release recommendation (`Blocked`, `Needs review`, or `Eligible`) next to the video player. Click any finding on the timeline or issue list to jump straight to that moment and inspect the extracted still frames.

## How it works

ProofFrame follows three rules designed to keep automated review honest:

1. **The checker never sees the expected answer.** When ProofFrame checks a specific detail such as a caption, a spoken line, or a costume color, it asks the vision or speech model what it observes without revealing what the script requires. Deterministic code compares the observation with the requirement afterward, so the model cannot simply agree with the prompt.
2. **Anything unverifiable is marked uncertain, never passed.** If a detail is blurry, a shot is missing, a model call errors out, or the spend cap runs out mid-run, ProofFrame marks the check for human review instead of guessing `PASS`. Even when every check passes, ProofFrame marks the run `Eligible` and leaves the final publishing decision to a human.
3. **Every finding points to the exact frame and timestamp.** Model timestamps are treated only as rough hints. ProofFrame extracts the actual frames from your video with FFmpeg, hashes them, and re-checks suspected defects on higher-resolution stills (and in swapped shot order for continuity issues) before confirming a failure.

## What it checks

- **Visual generation defects:** extra or detached hands and limbs, morphing objects, garbled text, impossible physics, and within-shot glitches.
- **Cross-shot continuity:** props changing size or design across cuts, wardrobe or accessories appearing and disappearing, furniture shifting inside a scene, or people vanishing without an exit.
- **Technical delivery issues (free, no model calls):** black intervals, frozen frames, silent gaps, audio loudness, and true-peak levels.
- **Reference-still fidelity (optional via CLI/API):** new props, missing props, or setting changes when an image-to-video clip is compared against its source image.
- **Locked script and brand rules (advanced contract mode):** exact on-screen text (Unicode NFC normalized), spoken dialogue, and declared character or prop attributes.

**Cost and prototype limits:** ProofFrame is a working prototype, and its detection accuracy has not yet been measured on a held-out benchmark. On a 60-second multi-shot clip, a full scan on Meta `muse-spark-1.3` costs roughly **$0.64–$0.74** at list prices (~146 s wall time); 1–5 second single-shot clips cost roughly **$0.01–$0.02** each. Because scans sample frames rather than inspecting every decoded frame and rely on a single vision model family, a clean report reduces review work without guaranteeing a defect-free film.

---

## For developers

### Run locally with Docker Compose

Requirements: Docker with Compose v2 and a Meta developer API key. No GPU is needed.

```bash
git clone https://github.com/nhocconan/proofframe.git && cd proofframe
cp .env.example .env            # set META_DEV_API=<your Meta developer API key>
                                # set PROOFFRAME_API_TOKEN for any non-local deployment
mkdir -p dropbox media
docker compose up -d --build db api worker web
```

Open `http://127.0.0.1:3000` for the web workbench. The FastAPI service listens on `http://127.0.0.1:8080`. For Linux hosts where containers run as UID `10001`, grant write access on `dropbox/` (`setfacl -m u:10001:rwx -m d:u:10001:rwx dropbox`). Public deployment behind Traefik is configured in [`docker-compose.deploy.yml`](docker-compose.deploy.yml).

Spend caps are configured in `docker-compose.yml` (`PROOFFRAME_MAX_PROJECT_COST_USD`, `PROOFFRAME_MAX_RUN_COST_USD`). Every paid model call reserves an upper-bound estimate in Postgres before the request is sent and settles actual token or audio usage afterward.

### API and CLI

The web UI, CLI, and HTTP API share one verification pipeline (`proofframe.verify.pipeline.run_verification`).

**Video-only scan via HTTP (with optional plain-text brief):**

```bash
# 1. Upload the MP4
curl -H "Authorization: Bearer dev-local-token" \
  -F "file=@my_video.mp4" -F "asset_id=my-video" -F "media_type=video" \
  http://127.0.0.1:8080/v1/assets

# 2. Start a contract-free verification run
curl -X POST http://127.0.0.1:8080/v1/verifications \
  -H "Authorization: Bearer dev-local-token" \
  -H "Idempotency-Key: run-001" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "video_only",
    "assets": [{"asset_id": "my-video", "sha256": "<sha256-from-step-1>"}],
    "brief_text": "Optional plain-text script, brief, or scene notes.",
    "run_mode": "live"
  }'
```

When `mode` is `video_only`, the API probes the uploaded media and builds a deterministic scan contract (`proofframe.verify.autocontract.build_auto_contract`). When `brief_text` is supplied (up to 20,000 characters), it is stored in the generated contract and passed as scene context to the artifact-scan and continuity prompts.

**Video-only scan via CLI:**

```bash
cp my_video.mp4 media/
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api \
  proofframe verify --video-only --video my-video=/media/my_video.mp4 --wait
```

Add `--reference /media/still.png` to include a hash-bound reference-still comparison for image-to-video clips.

### Advanced: approved-contract mode and repair loop

When you need repeatable, requirement-by-requirement checks — exact lower-third copy, time-scoped wardrobe or prop rules, key-text screen coverage, or line-by-line dialogue verification — submit an immutable JSON contract (`proofframe_contracts.models.Contract`).

- **In the web UI:** open **New verification**, expand **Advanced: use an approved contract JSON**, and upload or paste the contract JSON.
- **From the CLI:**

```bash
cp my_video.mp4 media/ && cp demo/contract_template_own_video.json dropbox/my_contract.json
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api \
  proofframe verify --contract /dropbox/my_contract.json --video my-video=/media/my_video.mp4 --wait
```

Failed contract assertions can generate typed repair requests (`POST /v1/repair-requests`). When an external tool renders a new version and submits a `RepairReceipt` (`POST /v1/repair-receipts`), ProofFrame re-verifies the new bytes against the unchanged contract and classifies each check as `FIXED`, `STILL_FAILING`, `REGRESSION`, or `UNCERTAIN`.

### Models and data handling

| Model | Role in ProofFrame | Status |
|---|---|---|
| Meta `muse-spark-1.3` (`/v1/responses`, `/v1/files`, strict JSON schema) | Video localization, frame confirmation, artifact scan, cross-shot continuity audit, reference-still comparison | Active in pipeline |
| Meta `muse-voice-transcribe-1.0` (`/asr/transcribe`) | Speech transcription for dialogue checks (turn-level timestamps) | Active in pipeline |
| Meta `sam-3.1` | Object tracking (box/mask grammar parsed) | Probed only ([`docs/CAPABILITY_PROBES.md`](docs/CAPABILITY_PROBES.md)) |
| ElevenLabs Scribe v2 (optional, when `ELEVENLABS_API_KEY` is set) | Independent second ASR for provider-level voting and word timestamps on dialogue checks | Optional in pipeline |

In Meta Standard mode, content is not used to train Meta models; because uploaded files on `/v1/files` do not expire automatically, ProofFrame sends `DELETE /v1/files/{file_id}` after every video call and records the deletion result in the run trace. Full vendor data-handling citations are served by `GET /v1/capabilities`.

### Repository layout and documentation

```text
src/proofframe_contracts/   typed contract, report, repair models and fail-closed policy (SDK-free)
src/proofframe/verify/      verification pipeline, auto-contract builder, artifact scan, continuity audit, QC
src/proofframe/providers/   Meta and optional ElevenLabs adapters with budget reservation
src/proofframe/api, worker  FastAPI service and Postgres lease-based job worker
src/proofframe/repair/      repair request/receipt protocol and file-drop caption executor
web/                        Next.js evidence workbench
demo/                       sample contracts and own-video contract template
docs/                       runbook, API contract, run history, build status, capability probes, prior-art review
```

Further technical details, evaluation runs, and operational guides:
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — writing contracts, decoded technical QC, repair round-trips, test commands, deployment
- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — HTTP routes and `ReportEnvelope` schema
- [`docs/RUN_HISTORY.md`](docs/RUN_HISTORY.md) and [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md) — every recorded live run, cost, and test gate
- [`docs/SOTA_CONTINUITY_REVIEW.md`](docs/SOTA_CONTINUITY_REVIEW.md) and [`docs/SOURCE_REGISTER.md`](docs/SOURCE_REGISTER.md) — prior art and academic references

### Credits and license

Licensed under the MIT License — see [`LICENSE`](LICENSE). All ProofFrame source code was written for this project with no copied third-party source code. Demo footage used in validation runs is from *Tears of Steel* (Blender Foundation, CC-BY 3.0, not stored in this repository); see [`NOTICE.md`](NOTICE.md).
