# ProofFrame

**An independent verification layer for generative video pipelines.**
ProofFrame checks a rendered video against the brief that was approved *before* it was generated, and reports what
it can prove: each finding is tied to real frames and timestamps, failures block release, and anything it cannot
verify stays visibly unresolved. It is built on Meta's Muse Spark multimodal models.

> **Status: working prototype, under active development.** The end-to-end loop runs on real footage with real
> Meta API calls (see [evidence](#what-works-today-measured)). Detection quality has **not** been benchmarked;
> nothing here is production-qualified yet. See [limitations](#limitations).


## Headline result: Vietnamese dialogue, two independent ASRs

ProofFrame checks that the dialogue in a rendered cut still matches the locked script. On one real Vietnamese
film workprint (13 locked lines; footage private, not in this repository; full rows in
[`docs/RUN_HISTORY.md`](docs/RUN_HISTORY.md)):

| Run | Providers | PASS / FAIL / UNCERTAIN | Cost | What it showed |
|---|---|---|---|---|
| run-272d2c40 | Meta ASR only (two passes) | 5 / **4** / 4 | $0.0068 | all 4 FAILs adjudicated as ASR or comparator artifacts (digit rendering, segmentation echo): false alarms |
| run-d10a4fe1 | Meta + ElevenLabs Scribe v2, provider-level voting | 8 / **1** / 4 | $0.0110 | the 1 remaining FAIL (first word "hội" missing at an edit boundary) was heard by both independent ASRs, with word timestamps |
| run-cf6495aa | same, after the film team fixed the trim | 10 / **0** / 3 | $0.0110 | the corrected cut verifies; the catch, fix, re-verify loop closed |

What this supports: requiring two independent providers to agree before a FAIL removed the 4 false FAILs on
this clip and kept the one real defect. What it does not: it is one clip, 13 lines, adjudicated by the film
team and the authors, not a benchmark; 3 lines stay UNCERTAIN; Scribe is a second vendor with its own data
terms (see [`/v1/capabilities`](#data-handling)); without an ElevenLabs key the check falls back to Meta only
and says so in the report.

## Measured on the probe clip set (deterministic checks, zero model cost)

Set: 17 synthetic clips from 10 video-generation models, frozen as hashes plus labels in
[`examples/evaluation_dataset/probe-2026-10-31.manifest.json`](examples/evaluation_dataset/probe-2026-10-31.manifest.json)
(media outside Git; `scripts/verify_probe_manifest.py` re-hashes it). **It is a single-shot i2v-fidelity and
unplanned-change negative-control set (8 image-to-video clips against one approved still, 9 text-to-video clips
with no reference). It is not a continuity benchmark** and says nothing about the cross-shot audit.
Labels are a model reviewer's ("human-adjudicated (Fable review 2026-10-31)" in the manifest) and a second human pass is still open.

Checks (`motion_mean_abs_diff`, `motion_max_step`, `global_motion_px`, run through the normal pipeline, 0 USD,
17 clips, 0 NOT_CHECKED). Thresholds were fixed before the first run; they come from a band the reviewer proposed
after looking at the same clips, so **the result is in-sample**.

| Defect class (i2v clips) | Labelled | Flagged correctly | False flags on i2v | Precision | Note |
|---|---|---|---|---|---|
| near-static ("a still sold as video", first-to-last change < 3) | 2 | 2 | 1 (grok-1.5, 2.88 vs 3) | 2/3 | threshold edge on a 1 s clip |
| uncommanded large motion (first-to-last > 40 or step > 25) | 1 | 1 | 0 | 1/1 | |
| camera moved when "camera holds" (> 20 px at 240 px width) | 4 | 4 | 0 | 4/4 | push-in, pull-back, reframe |
| **All three, i2v** | **7** | **7** | **1** | **7/8 = 0.875 (n = 8 clips)** | recall 7/7 |
| same checks on the 9 t2v clips | not adjudicated | 6 clips flagged by the motion band | unknown | **unknown** | prompts asked for a pan; camera check not applied |

Not detected, by construction: new props (Omni's phone, Wan's monitor and books), re-staged sets, and the one-frame
smear in HappyHorse (that clip is caught only because it also moves too much). The result file is
[`validation/runs/probe-2026-10-31-deterministic.json`](validation/runs/probe-2026-10-31-deterministic.json); reproduce with
`python scripts/run_probe_deterministic.py <media_dir>`. One clip (grok-lite t2v) carries a disputed
artifact label: the reviewer saw none, a frame check found a split picture with a duplicated mug.

### Model-based scan on the same 17 clips (paid, run once, 2026-10-31)

`proofframe verify --video-only` per clip, Meta `muse-spark-1.3`, per-run cap $0.25, no prompt or threshold changed before
scoring. **Cost: $0.2397 in total for 17 runs** (list-price estimate from the reports; $0.0078-$0.0202 per clip, far below the
$0.124/clip the plan allowed because 1-5 s clips get one hunt pass and at most one frame grid). Scored one-to-one by
`scripts/score_probe_model_scan.py`; result in [`validation/runs/probe-2026-10-31-model-scan.json`](validation/runs/probe-2026-10-31-model-scan.json).

| Label class (clip-level, reviewer's labels) | Labelled | Model scan caught | Model scan false flags | Deterministic checks caught |
|---|---|---|---|---|
| generation artifact (fail or minor) | 4 | **0** | 0 | 0 (HappyHorse trips the motion band for another reason) |
| new props vs the approved still | 3 | **0** | 0 | 0 |
| scene changed | 3 | **0** | 0 | 0 |

The model scan raised **no finding on any clip**: 13 clips PASS on both audits, 4 clips (the four 1.04 s Grok clips) ERROR
on the artifact scan. Recall on this set is 0 of 10 labelled defects, precision is undefined (no flags), and the n is 17
single-shot clips with a model reviewer's labels, scored in-sample. Two limits make "caught 0" less damning than it looks,
and neither changes the number: `--video-only` gives the continuity pass no reference still, so new props and re-staging
are not testable in this mode (the clip is the only evidence); and the scan is built for cross-shot and within-shot defects
in longer film, not 2-5 s single shots. A reference-image check mode is the thing this run says is missing.

Defect found by the run: clips shorter than the artifact scan's 3-4 s frame grid (all four 1.04 s clips) got no frame
evidence and ended ERROR (fails closed). Fixed afterwards (grid shrinks to first/middle/last inside the video stream).

### Second paid run after the fixes (v2, 2026-10-31)

Three changes, all made after v1 was scored and **evaluated on the same 17 clips, so v2 is in-sample**: (1) the short-clip
grid fix; (2) the continuity audit no longer reports PASS when it compared 0 shot pairs (single-shot clips are
`NOT_APPLICABLE` under an exclusion written into the auto-contract before the run); (3) a new `reference-match` check:
`--video-only --reference still.png` sends the still plus first/middle/last frames and asks for new props, missing props
and setting changes. Findings go to REVIEW, never FAIL (one model family). The scorer was changed before the run so a
check that did not run (ERROR, NOT_CHECKED, 0 shot pairs) leaves the recall denominator instead of counting as a miss.
Same manifest (sha256 `3df16b52…`), same `muse-spark-1.3`, per-run cap $0.70, code at commit f5de35d. **Cost: $0.2829 for 17 runs.**
Result in [`validation/runs/probe-2026-10-31-model-scan-v2.json`](validation/runs/probe-2026-10-31-model-scan-v2.json).

| Label class | v1 caught / checked / labelled | v2 caught / checked / labelled | v2 false flags |
|---|---|---|---|
| generation artifact | 0 / 4 / 4 | 0 / 4 / 4 | 0 |
| new props vs the still | 0 / 0 / 3 | **1 / 3 / 3** | 0 |
| scene changed vs the still | 0 / 0 / 3 | 0 / 3 / 3 | 0 |

- The catch: omni i2v, "smartphone held in man's hand, not visible in REF", 1.5-3.0 s (the labelled pen-to-phone swap).
- A miss we looked at: wan3 i2v. A monitor enters frame as the camera pans right, in a region outside the still's
  borders. The prompt tells the model to ignore framing differences, so whether that counts as a new prop is ambiguous.
  The prompt was not changed after seeing this.
- The artifact scan still raises nothing on the 4 labelled clips (0 candidates, so the adjudicator never ran). On
  1-5 s single shots it is a recall miss at the hunt/grid stage, not over-rejection.
- The disputed grok-lite t2v clip (a sharp middle band between two blurred bands, a second mug in the top band) passed
  the artifact scan in v2 (v1: ERROR, no frames); a frame sheet for human labelling is in the operator's private notes.
- 1 clip (grok-1.5 t2v, 1.04 s) still ended gen-artifacts ERROR: a hunt candidate at 1.0 s was padded to 1.2 s, past the 1.04 s clip end. Fixed afterwards;
  not re-run.

### Data handling

`/v1/capabilities` lists, per provider, what the vendor documents about training and retention, with the URL
and the date read (2026-10-31). Meta Standard mode does not train on content; uploaded files persist until
deleted, so ProofFrame deletes every video it uploads after the call and records the outcome in the trace.
ElevenLabs may train on non-Enterprise content unless the workspace toggle is off, and zero retention is
Enterprise-only; the toggle state of this deployment is not confirmed.

---

## Why

AI video tools now produce minutes of footage per prompt, and they fail in ways that are easy to miss:
a prop changes color between shots, the approved caption gets one word wrong, a hand appears with no body,
a bottle is both shattered and intact in the same shot. Today a human scrubs through every render, and a
"looks fine" from a second model is not evidence.

ProofFrame sits **between the approved brief and the generator**:

```mermaid
flowchart LR
  A[Approved brief<br/>contract + assertions] --> V
  G[External generator<br/>Flow, Veo, editors…] -->|render| V[ProofFrame<br/>verify]
  V -->|report: findings + evidence| R[Reviewer / pipeline]
  V -->|typed repair request| G
  G -->|new version + receipt| V
```

It never generates, never publishes, and can never edit the approved requirements.

## What works today (measured)

All numbers below come from live runs recorded in [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md). Costs are
`usage × list price` estimates.

| Capability | Live evidence |
|---|---|
| Exact on-screen text check (Vietnamese, NFC-normalised) | Caught a one-word caption error ("Celina" vs approved "Celia") on 3/3 frames at 13.2–21.6 s; same verdict reproduced on a second run of the same bytes |
| Wardrobe / prop / title-card checks with timestamped evidence | 60 s clip: 4 PASS + 1 FAIL + 1 UNCERTAIN (eye color not readable) for **$0.037** |
| Undeclared-defect scan (`generation_artifact_scan`) | On an AI-generated short: confirmed a bottle that is both shattered and intact in one shot (48–50 s); surfaced an ownerless-hands insert for review. On real live-action footage (*Tears of Steel*): no false FAIL — one candidate rejected (evaluator 0.5); with the stricter ownership rule (0.6) a robot-arm close-up became a REVIEW item |
| Event semantics | "Bottle breaks" initially FAILed because sampled frames missed a 1 s event; fixed (`temporal: occurs`), now PASS with evidence on the correct 0.5 s interval |
| Repair loop | Correct repair → **FIXED**; faulty repair → **STILL_FAILING**; repair that dropped audio → **REGRESSION**; 3rd attempt refused (cap = 2); stale receipt rejected |
| Cross-shot continuity audit | On a 60 s AI-generated short (13 shots): caught a boombox shrinking to hand size between scenes, its design changing, and a watch appearing/disappearing between consecutive shots; **4–5 of 8** labelled must-catch defects surfaced per full run (incl. the artifact scan), **0** false FAIL on real live-action footage — see [evaluation](#evaluation) |
| Long video | 2-minute clip, timestamps in minute 2 mapped correctly (**$0.076**). 5-minute files: upload, seek and full pipeline verified without paid calls. A pre-run cost plan shrinks audits to the remaining configured budget (5-min film, full contract: est. $2.06; not yet run live) |
| Budget stop | Owner clip with the run cap lowered to $0.30: spent $0.259; both audits UNCERTAIN ("18 of 27 calls not made") instead of being discarded, never PASS. Keeping a confirmed FAIL through a budget stop is covered by tests only |
| Deterministic motion and camera checks | Zero model cost: first-to-last and per-step frame difference, camera move in px, peak-difference frames added to the artifact-scan grid, every sample time clamped to the video stream (fixes the missing-frame crash when audio outlasts picture). Numbers on the probe set above |
| Evidence UI | Clicking a finding seeks the player into the evidence interval (Playwright, Firefox + WebKit) |
| 2D cartoon calibration (one film, 211 s, sha256 `6298bf55…`) | Full contract (24 exact-text, 52 dialogue, 4 prop/character, both audits): **$2.10** Meta + $0.011 Scribe, 580 s. Against 17 defects from two independent blind model audits (not owner-confirmed): **1/5 majors, 1/12 minors** caught (a prop held by an ownerless hand, blind via the artifact scan; a prop disappearing, via a declared check); 2/10 of the defects that are visual at all. 3 false blocking findings (a look-alike pattern read as "nothing", an invented name spelled differently by both ASRs, a prop "scale change"), 4 unresolved. 24/24 text assertions and 44/52 dialogue lines PASS; the 7 dialogue UNCERTAINs were ASR noise |
| Key-text coverage (`min_coverage`) | Same film, 24 text assertions with a 90 % rule: **$0.43**, 157 s; 22 PASS at 100 % of 5–16 uniform frames; 2 FAIL where the contract window started before the text was meant to appear (first readable frame 1.15 s and 1.06 s into the window), i.e. correct timing, over-strict contract |

Test suite: **444 tests** (419 pass and 25 Postgres-backed tests skip without a database; CI runs them on every push: `.github/workflows/ci.yml`): seed contract/policy, API + Postgres + job leases + atomic budget, pipeline plumbing,
Meta adapter failure semantics (incl. upload deletion), dialogue/ASR voting, text-coverage rules, deterministic motion/camera checks, frame-extraction clamp, artifact-scan and continuity-audit rules. These test our logic, **not** video-understanding accuracy.

## How it works

1. **Approved contract.** Each assertion names a target asset, an approved `expected` value, an optional time
   `scope`, and a *neutral* observation spec (subject + attribute, closed vocabulary where possible).
   Contracts are immutable and hash-identified; new renders never rewrite them.
2. **Coverage ledger first.** Every assertion gets a row before any model runs, so a skipped check is visible as
   `NOT_CHECKED`, never silently missing.
3. **Blind observation.** The model is asked *what it sees*, never told the expected value or a producer's
   "fixed" claim (enforced by a test). Long videos are split into ~60 s windows (the last may reach 70 s) with 3 s overlap.
4. **Server-side evidence.** Model timestamps are only hints: ProofFrame extracts the actual frames with FFmpeg,
   hashes them, and asks a second, independent question on those frames.
5. **Deterministic comparison** in code (exact text after Unicode NFC, closed categories), not by the model.
6. **Undeclared defects.** A three-stage artifact scan (video hunt, independent frame grid, skeptical
   adjudication on higher-resolution frames) looks for anatomy, ownership, object, text, physics and
   within-shot continuity defects nobody wrote an assertion for.
7. **Cross-shot continuity.** Per-shot scans cannot see errors that only exist *between* shots. ProofFrame
   splits the film into shots (FFmpeg scene score), builds a blind continuity log of recurring characters,
   props and sets, compares every adjacent pair, pairs bridging short insert shots, and first-vs-later
   appearances of each logged entity (intrinsic size/design/material only), then re-checks each suspicion
   with the two shots in **swapped order** on higher-resolution frames. Face-identity drift is always routed to
   human review.
8. **Policy.** `PASS / FAIL / UNCERTAIN / NOT_CHECKED / ERROR / NOT_APPLICABLE` → `BLOCK / REVIEW / ELIGIBLE`.
   A provider error is `ERROR`, never a content `FAIL`; missing coverage is never `PASS`; `ELIGIBLE` is not a
   publishing authorization.
9. **Source-aware repair.** A failure becomes a typed request (stage, field, approved value, preserved checks,
   retest scope, input hash). An external executor returns a new immutable version plus a receipt; ProofFrame
   re-verifies the new bytes and classifies each check as FIXED / STILL_FAILING / REGRESSION / UNCERTAIN.

### Meta models

| Model | Use | Status |
|---|---|---|
| `muse-spark-1.3` (Responses API, Files API, `input_video` with `fps`, `input_image`, strict JSON schema) | Video localization, frame confirmation, artifact scan, adjudication | In the pipeline |
| `sam-3.1` | Object tracking (box/mask grammar parsed) | Probed only ([probes](docs/CAPABILITY_PROBES.md)) |
| `muse-voice-transcribe-1.0` | Vietnamese ASR, turn-level timestamps | Probed only |

Measured ([probes](docs/CAPABILITY_PROBES.md)): ≈ 117 input tokens per second of video at 1 fps / 640 px; ≈ 530 input tokens per 960 px confirmation frame (3-frame calls ≈ 1.6k tokens incl. prompt).

## Quickstart

Requirements: Docker with Compose v2. No GPU.

```bash
git clone https://github.com/nhocconan/proofframe.git && cd proofframe
cp .env.example .env            # set META_DEV_API=<your Meta developer API key>
                                # PROOFFRAME_API_TOKEN is optional locally (falls back to a dev token); required for any public deployment
mkdir -p dropbox media && setfacl -m u:10001:rwx -m d:u:10001:rwx dropbox   # Linux; containers run as uid 10001
docker compose up -d --build db api worker web
# browse to http://127.0.0.1:3000 (UI); API on 127.0.0.1:8080
```

Spend caps live in `docker-compose.yml` (`PROOFFRAME_MAX_PROJECT_COST_USD`, `PROOFFRAME_MAX_RUN_COST_USD`);
paid calls reserve a conservative amount *before* each request. Before the first call the run is planned to fit
the remaining budget (reductions are listed on the run page). If the budget still runs out, results already paid
for are kept and the affected check can no longer PASS (`UNCERTAIN`, or `NOT_CHECKED` if nothing ran).

Verify a video from the CLI (same service the UI uses):

```bash
cp my_video.mp4 media/ && cp demo/contract_template_own_video.json dropbox/my_contract.json  # edit it first
docker compose exec -e PROOFFRAME_API_URL=http://localhost:8080 api \
  proofframe verify --contract /dropbox/my_contract.json --video my-video=/media/my_video.mp4 --wait
```

Writing contracts, the repair round trip, tests and the Traefik deployment are covered in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Evaluation

The shared core now supports decoded black/freeze/silence measurements with source-time evidence and zero model calls for technical-only runs. Offline scoring separates confirmed findings from review items, uses one-to-one event matching, respects human adjudication and supports recorded judge controls. See the [runbook](docs/RUNBOOK.md#decoded-technical-qc) for the runnable contract and commands. These additions do not establish perception accuracy or SOTA status; the development results below predate them.

Audio delivery checks now measure integrated loudness/true peaks, including audio-only assets via `--audio`. Fractional tolerances, directional limits and printed-meter resolution are explicit. A [frozen-cohort comparison command](docs/RUNBOOK.md#frozen-cohort-baseline-comparison) binds baseline results to identical media/contracts and rejects cross-split leakage. The [industrial research decisions](docs/RESEARCH_AND_DECISIONS.md#6-industrial-implementation-decisions-2026-10-29) distinguish implemented measurements from deferred specialist capabilities.

A small **development** evaluation, not a benchmark. Labels: 11 defects (8 must-catch) on a 60 s AI-generated
short, written by a reviewer from 2 fps contact sheets *before* the continuity audit was built, not yet
confirmed by the film's owner. The same clip was used to improve the method, so these numbers are optimistic;
there is no held-out set yet. Scorer: [`scripts/score_findings.py`](scripts/score_findings.py) (time overlap +
category + entity keyword; unmatched findings are listed for a human, not silently counted).

| Version (evaluator) | Must-catch surfaced (of 8) | False FAIL on live-action control | Notes |
|---|---|---|---|
| per-shot artifact scan only (0.7) | 2 | 0 | bottle shattered-and-intact; ownerless-hands insert as review |
| + continuity log only (0.8) | 2 | 0 | log tracked entities well but listed almost no contradictions |
| + adjacent/registry pairs, swapped-order adjudication (0.9–0.10) | 3 → 5 | 1 → 0 | a hologram "size change" was a false FAIL until VFX was added as an innocent explanation |
| + adjudicate up to 24 suspicions, concurrent checks (0.11–0.12) | **5 and 4** (two full-contract runs) | 0 (2 runs) | two continuity-only runs caught 3 and 4 cross-shot defects; the artifact scan caught D4 and surfaced D1 in each of its last 6 runs; candidate generation varies run-to-run |

Per minute of footage (measured on the 60 s clip, full contract incl. both audits): ≈ **$0.64–0.74**
estimated, **146 s** wall time after concurrency (was 287 s). Consistently missed: furniture swap between
shots (caught 1/4 runs), a person vanishing across an insert (raised by the pair stage, rejected at
adjudication), a bag changing material. Also reported but not in the labels (owner to judge): a telephone
appearing on a table, a bottle growing when it falls, a handle changing color.

## Prior art and credits

All ProofFrame code in this repository was written for this project; **no third-party source code was
copied**. Runtime dependencies are listed in `requirements.lock` and `web/package-lock.json`; FFmpeg is used as
an external binary. Ideas we adopted, with credit:

- Blind observation before comparison, separate scoring — *continuity-checker* (J. Muller, MIT), see
  [`docs/SOURCE_REGISTER.md`](docs/SOURCE_REGISTER.md) S01.
- Entity registry / memory of first appearances for cross-shot consistency — *EntityBench* (arXiv 2605.15199),
  *VideoMemory* (arXiv 2601.03655), *GroundShot* (arXiv 2606.20799).
- Rubric-style judging of adjacent shot pairs rather than one global score — *MSAVBench* (arXiv 2605.20183).
- Order swapping because VLM judges show position bias — arXiv 2406.07791 and 2607.25300.
- Shot detection by scene-change score — FFmpeg `select='gt(scene,…)'`; *PySceneDetect* / *TransNetV2*
  evaluated as alternatives, not used.

The full review with URLs and verification status is in
[`docs/SOTA_CONTINUITY_REVIEW.md`](docs/SOTA_CONTINUITY_REVIEW.md). We found **no independent accuracy
measurement of any commercial continuity checker**, so we make no comparative claim.

## Limitations

- **No accuracy benchmark for the model-based checks yet.** Three annotated films plus the 17-clip probe set, which is
  single-shot, synthetic and reviewer-labelled; the deterministic-check numbers above are in-sample (n = 8 i2v clips).
  Defect-escape rate and comparison with a human or another model are unmeasured.
- **Most recorded live runs predate the latest evaluator changes** (versions are stamped in every report); later
  changes were verified with unit tests and the specific live reruns listed in BUILD_STATUS.
- **Sampled, not exhaustive.** 1–2 fps video passes plus a few frames per check; events shorter than the sampling
  interval can be missed. Every report says so.
- **One model family.** Localization, confirmation and adjudication all use `muse-spark-1.3`; agreement between
  them is not independent proof. Hand-ownership judgments contradicted each other in testing, so they are always
  routed to human review.
- **Run-to-run variance.** The same video surfaced 4 or 5 of 8 labelled defects on different full runs; a
  single clean run is not proof of a clean film.
- **Low recall on 2D cartoon story defects.** On one 211 s cartoon it caught 2 of 17 audit-labelled defects
  (2 of the 10 that are visual). It misses props popping in at a cut (pencil, thought-bubble items), pose pops,
  caption-over-character overlaps and everything non-visual (voice pitch, pacing, teaching). Its continuity audit
  confirmed 3 "scale change" findings on a cartoon that cheats scale between wides and close-ups; treat them as
  review items. Exact-text checks read the words, not their placement.
- **Key-text coverage is a fraction of sampled frames** (uniform grid, 4–16 frames per window), not of every
  decoded frame; its window must come from the contract (e.g. a measured subtitle file). ASR word timestamps are
  not yet used to place it.
- **Continuity is keyframe-based.** Two keyframes per shot; changes inside a shot between keyframes, dissolves
  and contradictions between distant batches of a long film can be missed.
- **Not yet in the pipeline:** SAM tracking (would allow measured size ratios instead of judged ones),
  embedding similarity as a cheap pre-filter, lip sync, unrequested-speech detection, story-time vs edit-time, caching.
- **Repairs:** only a deterministic FFmpeg caption-composite executor exists; generative shot regeneration is a
  typed action without an executor.
- Single tenant, static API token; the API must stay on a private network.

## Roadmap

1. Owner-confirmed labels plus a held-out set of other productions; report precision/recall per defect class.
2. SAM 3.1 tracks for prop/occlusion questions; Muse Voice for dialogue-vs-script and caption alignment.
3. Cross-shot continuity (expected story state, approved transitions) and assembled-timeline checks.
4. Generative repair executors behind the same receipt protocol; integration with existing content pipelines.

## Repository layout

```
src/proofframe_contracts/   typed contract, report and repair records + fail-closed policy (domain, no SDKs)
src/proofframe/verify/      pipeline, deterministic comparison, artifact scan, cross-shot continuity audit
src/proofframe/providers/   Meta adapter (budget-reserved, failure-classified calls)
src/proofframe/api, worker  FastAPI service, Postgres job queue with leases
src/proofframe/repair/      repair request/receipt protocol, file-drop executor
web/                        Next.js evidence workbench
demo/                       demo contracts (Tears of Steel) and a template for your own video
docs/                       build status, runbook, API contract, capability probes, design docs, original handoff
validation/                 live run reports and UI screenshots used as evidence
```

## Credits

Demo footage: *Tears of Steel* © Blender Foundation | mango.blender.org, CC-BY 3.0 (not stored in this
repository). See [`NOTICE.md`](NOTICE.md). License for this repository: not yet chosen.
