# ProofFrame research source register

Research date: 2026-10-27. Public repository/source inspection, not a live model benchmark.
URLs below identify primary sources. Repository defaults can change; pin reviewed commits before importing code. Blob SHAs identify inspected file versions, not whole-repository commits. No third-party source code is redistributed in this package.

| ID | Primary source | Inspection and useful evidence | Reuse disposition |
|---|---|---|---|
| S01 | https://github.com/jtmuller5/continuity-checker | README; `notes/experiments.md`; `cinema/readers/gemini.py`. Repository HEAD observed: `99ac3c383f63105201c89b70e4dbb4a0e0f35924`. Gemini source blob: `5f312f186e6fc86b292713b975598ca4683968c8`; experiments blob: `70884d905b0ee46dc8b584d01bd23d029f950698`. | MIT declared. Learn blind observation, immutable repair overlays, caching, abstention and separate scoring. Its disclosed offline results are not evidence of real-film detection quality. |
| S02 | https://scenefixer.com/ | Product page explicitly identifies Opus for deep scans, Haiku for free scans, and Runway Aleph for edits. Beta caveats are visible. | Commercial product; no verified public implementation found in this review. Treat output preservation claims as vendor claims, not measured guarantees. |
| S03 | https://runway.com/en/api-hackathon | Official winner list identifies Scene Fixer as third place in the May 2026 event. | Historical corroboration, not an accuracy benchmark. |
| S04 | https://github.com/BenDuske/CONTINUUM | README and `src/continuum/agents/skeptic.py`. README blob `92660093edb2c01237dd1192a6ce88a7628a5a09`; skeptic blob `d5c00e7b887bb3a2f63f6d5310da843e08f0ce13`. | Apache-2.0 declared; skeptic source has SPDX header. Learn temporal production memory and change impact. Its skeptic uses the same Gemini family and defaults toward confirming findings. |
| S05 | https://github.com/martinsaguinaga315-dot/ai-video-production-verifier | README blob `1e284cac15796376c6ee512e583db98e73c825d0`. Locked-fact preflight, deterministic rules, experimental semantic audit, clear media-inspection limitations. | Apache-2.0 declared. Evaluate individual preflight rules for porting after code/license review; not a rendered-video engine. |
| S06 | https://github.com/TwoOxygenH2O/casr-core | README and `casr-engine/src/main/java/com/twooxygen/casr/engine/CasrPolicySearcher.java`, blob `2330dc1f17988fc6656fbed4bf354509e72ae77d`. Candidate actions and cost/success proxies are hand-authored in the inspected planner. | Apache-2.0 declared. Learn cost-aware action selection; do not represent its proxy outcomes as measured video repairs. |
| S07 | https://github.com/NVIDIA/cosmos-evaluator | README blob `46a70cfb182f52149c9ed38b1743a619d78faaeb`. Four checker families and orchestration framework. | Apache-2.0 stated. Check NOTICE, downloaded models and dependencies separately. Strong design reference, not our base application. |
| S08 | https://github.com/NVIDIA/cosmos-evaluator/blob/main/docs/checks/attribute_verification.md | Question generation/repair, multiple-choice verification, configurable evidence, default `frames: 1`, distinct failed/errored checks. | Reuse the checker contract pattern; do not inherit one-frame coverage assumptions. |
| S09 | https://github.com/NVIDIA/cosmos-evaluator/blob/main/checks/attribute_verification/processor.py | Inspected lines 1-220; blob `e1fed542725c25a9aadd9a21270b91ec087ed74f`. Typed result/summary, cancellation, model separation, CPU orchestration. | Source header Apache-2.0. No copied implementation in this package. |
| S10 | https://github.com/Vchitect/VBench | Broad video-generation evaluation suite; Apache-2.0 declared. | Optional offline evaluation, not mandatory runtime dependency. |
| S11 | https://github.com/Vchitect/VBench/blob/master/VBench-2.0/README.md | 18 dimensions, including human identity/clothes and dynamic relations; heavy research dependencies and limitations on customized input modes. | Corrects the earlier oversimplification that VBench only measures surface quality. |
| S12 | https://github.com/KaiyueSun98/T2V-CompBench | Default V2 README and repository listing; attribute/action/motion binding, interaction, spatial relationships and numeracy. | No clear top-level license was established in this review. Learn taxonomy; do NOT copy code/data until rights are established. |
| S13 | https://arxiv.org/html/2406.08656 | TC-Bench: Benchmarking Temporal Compositionality in Text-to-Video and Image-to-Video Generation, 2024. Initial/final states and assertion-based temporal evaluation. | Research reference, not proof of performance on 2026 models. Do not confuse with unrelated tropical-cyclone projects named TC-Bench. |
| S14 | https://github.com/j-min/DSG | Davidsonian Scene Graph for fine-grained text-to-image evaluation; dependency-aware questions. Apache-2.0 declared. | Learn assertion dependencies. Image evaluation is not a temporal video solution by itself. |
| S15 | https://github.com/yeliudev/VideoMind | Research implementation: planner, temporal grounder, verifier, answerer; shared backbone/LoRA roles; public benchmark results. BSD-3-Clause declared. | Learn localization workflow. Do not replace its trained models with generic prompts and claim equivalent results. |
| S16 | https://github.com/Amordia/ActiveLook | README describes temporal/spatial resampling and cross-scale candidate fusion on VideoMind. BSD-3-Clause declared. | Exploratory design reference. Publication status and comparative performance were not independently reproduced here. |
| S17 | https://github.com/TIGER-AI-Lab/VideoScore2 | Human-aligned evaluation of visual quality, alignment and physical/common-sense consistency; training/evaluation code. MIT declared. | Optional offline ranking baseline. Code, weights, datasets and upstream components require separate license review. |
| S18 | https://docs.twelvelabs.io/docs/guides/analyze-videos-and-images/videos | Asynchronous analysis, structured responses, reference-image support and timestamped segmentation mode. | Potential observation/retrieval adapter, not an acceptance-policy replacement. |
| S19 | https://www.interrasystems.com/file-based-qc.php | BATON commercial automated file-based QC. | Useful technical-QC product reference; not a basis for claims about narrative verification. |
| S20 | https://github.com/Breakthrough/PySceneDetect | Shot/transition detection library; BSD-3-Clause declared. | Direct dependency candidate. Prefer actual production shot boundaries when supplied. |
| S21 | https://opentimelineio.readthedocs.io/en/latest/ | Editorial interchange for timing, tracks, transitions and external media references. | Optional adapter. Unsupported retimes must be reported, not silently flattened. |
| S22 | https://ffmpeg.org/ffmpeg-filters.html | Media filters and technical signals. | Direct CLI dependency; inspect chosen binary build and licensing. Signals require project-aware interpretation. |
| S23 | https://dev.meta.ai/docs/video-understanding | Muse video input, Files API, native video support; explicit audio caveat for Muse Spark 1.3. | Official documentation, NOT a tested call on the user's account. |
| S24 | https://dev.meta.ai/docs/sam/overview | SAM 3.1 boxes/masks/tracks, special-token output and official parser reference. | Implement a real segmentation adapter, not a generic JSON-chat wrapper. |
| S25 | https://dev.meta.ai/docs/speech-to-text and https://dev.meta.ai/docs/api-reference/voice/schemas | Vietnamese support; dedicated ASR routes; buffered response requires `sessionId`, `transcript`, `audioDurationMs`, and `turns`; file endpoint limit is 10 minutes / 32 MB; turn-level timestamps but no word-level timestamps; diarization is session-scoped; `audioProcessedMs` is progress, not word timing. Rechecked 2026-10-31. | Validate the buffered response locally; split longer approved scopes explicitly rather than truncating. Verify alignment separately before exposing word timing. |
| S26 | https://dev.meta.ai/docs/pricing-rate-limits | Current pricing/rate-limit source. | Refresh when starting live tests; this package does not hard-code a current price table. |
| S27 | https://arxiv.org/html/2606.02578 | Research on perceptual judgment bias: judges can follow response descriptions rather than visual evidence. | Supports testing for anchoring; its experiments are not measurements of the user's models or films. |
| S28 | https://deepmind.google/models/model-cards/gemini-4-argon/ | Official identification of the model mentioned by the user. | Public aggregate benchmarks do not establish fitness for the user's QA task. |

## Verification boundary

2026-10-29 audit additions (primary abstracts/documentation inspected; no upstream experiments reproduced):

| ID | Source | Scope | Limit |
|---|---|---|---|
| S29 | https://arxiv.org/abs/2605.15199 | EntityBench: entity schedules and fidelity-gated cross-shot scoring | Generation benchmark, not ProofFrame detector qualification |
| S30 | https://arxiv.org/abs/2605.20183 | MSAVBench: hybrid rubrics/tool-grounded evaluation | Abstract inspected; reported correlation not reproduced |
| S31 | https://github.com/Vchitect/VBench/blob/master/VBench-2.0/README.md | Specialist/custom-video evaluation routes | README inspected; no code/weights imported or tested |
| S32 | https://www.telestream.net/telestream-support/vidchecker/faq.htm | Industrial technical-QC coverage | Vendor documentation, not an accuracy benchmark |
| S33 | https://www.ffmpeg.org/ffmpeg-filters.html | Black/freeze and audio-analysis capabilities | Decoded black/freeze/silence checks subsequently implemented and tested on synthetic controls; no detector qualification claim |
| S34 | https://arxiv.org/abs/2604.01569 | VideoZeroBench v2: separate answer and evidence evaluation | Abstract inspected; domain/task differs |
| S35 | https://arxiv.org/abs/2609.28991 | Stage-intervention video-agent evaluation | Abstract inspected; transfer to ProofFrame untested |
| S36 | https://arxiv.org/abs/2608.15574 | Citation verifier ablations | Abstract inspected; no claim its results transfer to film QC |
| S37 | https://www.telestream.net/vidchecker/specs.htm | Vendor technical/audio QC specification | Inspected 2026-10-29; product not executed or benchmarked |
| S38 | https://interrasystems.com/file-based-qc.php/QS/video_tutorial-baton.php | BATON decoded QC and integration capabilities | Vendor documentation inspected; no independent accuracy comparison |
| S39 | https://tech.ebu.ch/docs/r/r128.pdf | EBU R128 v5 (2023), programme loudness/true-peak delivery guidance | PDF read 2026-10-29; no claim our meter is certified or full compliance implemented |
| S40 | https://docs.twelvelabs.io/api-reference/analyze-videos | Structured timestamped analysis, sync/async/batch endpoints | Documentation read; no adapter/API run or model qualification |
| S41 | https://arxiv.org/abs/2606.24797 | EG-VQA v2 (2026-10-04), evidence faithfulness | Abstract inspected; experiment not reproduced |
| S42 | https://arxiv.org/abs/2607.11862 | Evidence-Backed VQA, temporal segments and masklets | Abstract inspected; code/weights not imported or tested |
| S43 | https://github.com/m-bain/whisperX | Transcription, word alignment and diarization; BSD-2-Clause declaration | README inspected; transitive model licenses and domain accuracy not qualified |

The industrial wave also inspected the installed FFmpeg `-h filter=ebur128` options and executed real/synthetic audio checks. The FFmpeg web filter page timed out on this pass; local execution establishes supported flags, not standards conformance. New code is self-written; no third-party source or weights were copied.

See `IMPLEMENTATION_SOTA_AUDIT_2026-10-29.md` for current local checks and WHY-003 historical evidence. The original research boundary below describes the initial handoff session.

The review read primary documentation and selected implementation files using web and GitHub tools. Downloading whole repositories into this runtime failed because the runtime could not resolve github.com. Consequently, NO upstream test suite, paid API, video generation job, or model evaluation was run here. The contract harness shipped in this package is newly authored and tested separately; its test report is not a perception benchmark.

Public source availability does not grant rights to client footage, trademarks, training data, voices, model weights or all transitive dependencies. Preserve notices when importing licensed code and document what was newly built during the hackathon.
