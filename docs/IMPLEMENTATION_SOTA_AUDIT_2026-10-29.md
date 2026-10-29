# Implementation audit, 2026-10-29

ProofFrame is a working research prototype with real integration evidence; SOTA detection quality and industrial production readiness are not established. The current architecture uses several relevant research techniques, but the recorded results include substantial misses and no held-out comparison. This is an assessment, not a new implementation or a perception benchmark.

Subsequent implementation on the same date added decoded black/freeze/silence QC, offline one-to-one scoring with judge controls, local provider-schema validation and entity-correspondence guards. Current implementation and verification are in `BUILD_STATUS.md` and `RUNBOOK.md`. The gap table below records the pre-improvement snapshot; no held-out accuracy or SOTA claim has since been established.

## Evidence and scope

Read: repository instructions, engineering handoff, implementation specification, research/continuity reviews, evaluation plan, build/probe records, pipeline/media/provider and policy code, CI and scoring code. Read the sibling studio's WHY-003 baby-teeth production lessons, MP4 r3 art review and final release verification. Those are historical reports, not footage re-evaluated in this audit. Model attribution comes from the reports; it was not authenticated against provider logs.

Re-ran the offline suite in the existing API container: **123 passed, 1 dependency deprecation warning, 21.04 s**. SHA-256 comparison found **41/41 checkout Python files under src/tests identical to the tested container**. No paid calls, new stack, publication or footage transfers. Existing live-run results below are historical records in `BUILD_STATUS.md`, not newly reproduced model runs.

Host commands failed: `python` is absent (127); `python3 -m pytest` lacks pytest (1). `docker exec proofframe-web-1 npx tsc --noEmit` exited 1 with compiler help: the runtime image omits source and tsconfig. A fresh frontend type check/build, browser journey, load test and security audit were not performed. No lint gate is configured in the inspected CI. This documentation-only audit changes no runtime behavior.

## Findings against the specification

| Priority | Finding | Evidence | Implication |
|---|---|---|---|
| P0 | Detection quality is unqualified | `BUILD_STATUS.md`: evaluator 0.12 surfaced 4/8 must-catch items; 0.11 full run 5/8. Same dev clip used for tuning; labels agent-authored, owner unconfirmed | These are development catches, not production recall. A REVIEW item counts as surfaced in the scorer; it is not a confirmed detection |
| P0 | No Opus or industrial baseline comparison | Gate 4 not started; `EVALUATION_PLAN.md` B0–B4 remain a plan | Cannot establish superiority, savings or which model should judge each task |
| P1 | Technical QC is substantially below broadcast tooling | `ObservationSpec.technical_metric` exposes duration, audio presence, width, height; media probe reads metadata | Audio presence cannot establish intelligibility, loudness, sync or absence of clipping; container metadata cannot establish clean decoded frames |
| P1 | Cross-shot reasoning is implemented, but spatial measurement is missing | `continuity.py`: entity log, adjacent/insert/long-range pairs; pipeline uses full frames. SAM is probed, not integrated; no measured entity-scale or crop qualification stage | Subtle material, accessory and prop-size drift still depends on model descriptions |
| P1 | Swapped adjudication is not a controlled position-bias experiment | Pipeline compares A/B then adjudicates B/A using a different prompt and selected candidates; no identical-pair control harness | Useful skepticism, but it neither isolates order effects nor measures false-difference rate |
| P1 | Evidence sampling can miss the event that decides the requirement | `plan_keyframes` uses one or two frames per shot; artifact scan uses sparse grids/video; owner event miss documented | Need task-specific temporal refinement and boundary strips, with explicit sampled coverage |
| P1 | Dialogue, alignment and qualified lip-sync are absent | Known gaps in build status; no supported audio observation kind in `ObservationSpec` | Do not infer dialogue or mouth synchronization from video/ASR proxies |
| P1 | Production profile is incomplete | Build status: only meta_hackathon, single-tenant static-token configuration; production_best_qualified not implemented | Industrial deployment requires measured routing and operational/security qualification beyond this demo |
| P2 | Earlier documents are stale | README/handoff describe the original seed; continuity review says no registry, while current code implements a descriptive log and pair selection | Use current code + dated run records for implementation claims; retain older documents as historical design evidence |

The implemented immutable contracts, media hashes, coverage states, typed repair receipts, bounded budget reservations and regression checks are worth preserving. Their offline tests establish software behavior, not perception accuracy. Generative shot replacement remains unimplemented; the demonstrated repair is deterministic compositing.

## Current primary-source comparison

Sources were checked online on 2026-10-29. Research abstracts and upstream documentation were inspected; upstream experiments, full-paper methods and code were not independently reproduced. These sources establish relevant approaches, not an exhaustive ranking of every commercial verifier.

| Source | Established by inspected source | Use here |
|---|---|---|
| [EntityBench](https://arxiv.org/abs/2605.15199) | Per-shot entity schedules and a fidelity gate for cross-shot evaluation; generation benchmark | Upgrade descriptive logs to evidence-bound entity appearances with visibility/anchor qualification. Do not treat generation results as detector accuracy |
| [MSAVBench](https://arxiv.org/abs/2605.20183) | Adaptive segmentation, instance-specific rubrics and tool-grounded evidence; abstract reports 0.915 human rank correlation | Narrow attribute rubrics plus measurements; that overall correlation does not establish per-defect recall |
| [VBench-2.0 upstream](https://github.com/Vchitect/VBench/blob/master/VBench-2.0/README.md) | 18 dimensions; custom-video routes for anatomy, identity, clothes and multi-view consistency; released anomaly pipeline | Evaluate selected specialist baselines offline, subject to license/runtime/domain checks; never use the aggregate generation score as release authority |
| [Vidchecker official FAQ](https://www.telestream.net/telestream-support/vidchecker/faq.htm) | Technical QC includes file parameters, levels/loudness, blockiness, dropouts, clipping and black sequences | Establish a deterministic technical QC baseline before adding more general model critiques; vendor documentation is not an independent accuracy comparison |
| [FFmpeg filter documentation](https://www.ffmpeg.org/ffmpeg-filters.html) | blackdetect/freezedetect and audio analysis filters are available | CPU technical candidates with timestamps; intentional black/static shots need approved exceptions |
| [VideoZeroBench, revised 2026-10-07](https://arxiv.org/abs/2604.01569) | Evaluates answering separately from temporal/spatial evidence grounding | Score claim correctness and evidence sufficiency separately; working seek links prove navigation only |
| [Beneath the Scores, 2026-09-24](https://arxiv.org/abs/2609.28991) | Stage-intervention protocol tests where downstream hallucinations originate | Ablate localization, observation and judgment independently using human-supplied evidence on evaluation-only runs |
| [Citation-verifier ablation, 2026-08-16](https://arxiv.org/abs/2608.15574) | On its task, direct verification and blind-caption/general-judge variants can fail; an NLI alternative is evaluated | Test claim-support verification as an ablation; text entailment cannot recover details a visual observer missed |

No source inspected establishes that ProofFrame is best in class. FFmpeg scene scoring is a practical baseline; the earlier continuity review's blanket claim that TransNetV2 is the accuracy leader should be read only within its cited comparison, not as a current universal SOTA claim.

## What to reuse from WHY-003

Historical sources in `/home/tienlv/projects/curious-kids-content-studio/`:

- `docs/LESSONS.md`, section “WHY-003 Long master ce2b555a”: owner rejected the output after 5/5 MP4 seats, final verification and 3 release seats passed.
- `data/agent-runs/WHY-003/teeth/mp4-r3/review/art.md`: reports Opus high effort in a separate context; exact MP4 hash, full-resolution stills, 405 px downscales, 2–30 fps strips and pixel/bounding-box measurements.
- `data/agent-runs/WHY-003/teeth/release/review/final-verify.md`: distinguishes measured output, minor defects and checks not performed. Identifies an end-card ratio gate computed from sprite constants that was green by construction despite rendered size drift.

| Technique | Apply in ProofFrame | Acceptance evidence |
|---|---|---|
| Exact master hash and tested-artifact inventory | Bind specialist/human reviews to output and evidence hashes; expire reuse after changed dependencies | A changed master or reference cannot inherit the earlier approval |
| Full-resolution crops plus phone-size review | Add corner/edge, face, overlay and text crops; inspect actual composition at target display size | Findings cite pixels/regions and timestamps; a downscale is labeled a simulation |
| Dense strips around transitions | Refine candidate events and clip/sprite joins rather than globally multiplying sparse critiques | Test short defects between old samples and legitimate cuts/occlusions |
| Output-derived measurements | Measure rendered eye spacing, box geometry, fringe/collision and audio features where references permit | A seeded visible defect changes the measured result; a constant-derived “test” does not qualify |
| Separate expert criteria | Science/intent, art, editorial, technical and rights checks get distinct capability/coverage declarations | No role PASS substitutes for an unsupported modality; multiple same-model roles are correlated |
| Delta review with preserved failures | Recheck changed regions, dependencies and final-export sentinels; keep old finding IDs | Detect fixed, still failing and newly introduced regression on actual new bytes |
| Explicit not-done list | Expose unobserved audio, unvalidated lip-sync, simulated phone view and absent audience study | Missing checks remain visible and cannot become PASS |
| Early human draft review and bounded redesign | Keep enjoyment/clarity as human acceptance; studio lesson suggests replanning after two beat redesigns | Owner acceptance is recorded separately from automated defect checks |

Do not import studio-specific thresholds (eye spacing, fringe colors, pace or safe areas) as universal film rules. These need approved profiles and calibration. Do not copy private footage or historical review dumps into this repo. More Opus review seats alone would repeat the recorded failure mode. The final verification's positive prediction of child enjoyment was an inference without a child study, later contradicted by owner acceptance.

## Recommended execution order

1. **Qualification before router/prompt expansion:** execute existing B0–B3 evaluation plan. Freeze owner-adjudicated development, calibration and held-out splits by episode/source family. Include WHY-003 owner defects as development examples only, clean films, legitimate transitions, occlusion and no-change controls. Keep private media outside Git. The proposed 60-example pilot is a feasibility milestone, not statistical proof.
2. **Strengthen the scorer:** report confirmed detections and surfaced review items separately; adjudicate unmatched findings, deduplicate root causes, use one-to-one event matching, and report TP/FP/FN, severity, false alerts/minute, abstention and localization/evidence quality. Current `score_findings.py` allows overlap with either broad shot span and keyword matching; one finding may match several labels. It is a development diagnostic, not a precision/recall qualification harness.
3. **Add deterministic QC:** decoded black/flat/freeze/error candidates and measured audio loudness/silence/clipping, plus appropriate approved exceptions. Prove on synthetic mutations AND real clean controls before changing release policy. This is the nearest industrial capability gap and can reduce avoidable VLM spend.
4. **Improve evidence:** task-specific high-resolution crops, dense local strips and a qualified entity registry with canonical anchors/visibility. Trial SAM/detectors only where crops measurably improve recall at tolerable false alerts and cost. Add identical-pair and matched A/B versus B/A controls.
5. **Qualify providers by task:** compare Meta and the configured Opus option on identical evidence; separately compare whole workflows including refinement, repairs and owner review. Record exact available model IDs/settings and measured usage. No model choice is justified by brand or a general leaderboard alone.
6. **Industrial graduation:** production routing, authenticated tenant isolation, workload/recovery tests, worker/resource bounds, real dialogue checks, and repeated repair/regression evaluation. Decide per-check automation thresholds with the owner before viewing the final holdout; report uncertainty and retain human acceptance.

The next implementation work should be executable qualification and technical QC, not another architecture rewrite. This audit authorizes no paid experiment and implements none of the proposed capabilities.
