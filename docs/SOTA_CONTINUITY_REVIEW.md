# Cross-shot continuity: state-of-the-art review

Research date: 2026-10-27. Method: web search plus page fetches (arXiv abstract pages, GitHub READMEs, vendor pages). Full PDFs were mostly NOT read; where a metric or number comes from a search-result summary rather than a page I fetched, it is marked **(secondary)**. Anything I could not confirm is marked **(unverified)**. Extends `RESEARCH_AND_DECISIONS.md` and `SOURCE_REGISTER.md` (S01-S28); it does not repeat them.

## Executive summary

- No independent measurement of any commercial "AI continuity checker" was found. Scene Fixer, invideo, and "Continuity Copilot" are vendor claims. invideo's own FAQ concedes that frame-by-frame continuity scanning of a finished film is not yet reliable anywhere (secondary, via search summary): https://invideo.io/faq/can-ai-automatically-detect-character-consistency-errors/
- The real 2026 activity is in academic multi-shot generation benchmarks (EntityBench, MSAVBench, PersonaShot, MuSS, GroundBench, VideoMemory-54). They evaluate generators, not arbitrary finished films, but their metric designs are directly reusable as verification recipes.
- Converging recipe across these benchmarks: (a) per-shot entity schedule, (b) localise the entity (detector/SAM), (c) embedding similarity (DINOv2/CLIP/ArcFace) as a cheap signal, (d) rubric-decomposed VLM judge on adjacent shot pairs for what embeddings miss. Embeddings and VLM judges disagree, and neither is validated as ground truth.
- The defects the human found are mostly attribute drift of a recurring entity (size, design, material, accessory), swap of a scene element, entity appearance/disappearance, and owner contradiction. All need an entity registry across shots; ProofFrame has none. That is the gap.
- Main risk: VLM judges are weak at fine two-image differences and prone to hallucinating differences or favouring a position. Design must include no-difference controls, order swaps, and abstention.

## 1. Solutions table

| Name | Type | What it checks | Method | Strengths | Limits | License | URL |
|---|---|---|---|---|---|---|---|
| Scene Fixer | Commercial web app | Cross-shot continuity detection + user-confirmed fix | LLM scan (Opus/Haiku per vendor), Runway Aleph edit | Good UX pattern (see S02) | No public accuracy; beta | Closed | https://scenefixer.com/ |
| invideo AI agent / "AI script supervisor" | Commercial | Rough cut vs shot list; flags e.g. prop or grade change | LLM watching cut (details not published) | Reports unprompted catches in its own examples | Marketing content only; vendor FAQ says scan-finished-film is unreliable (secondary) | Closed | https://invideo.io/faq/what-is-an-ai-script-supervisor-and-how-does-it-work-for/ |
| Continuity Copilot (Beverly Boy article) | Promotional article | Colour consistency, prop tracking claims | Not described | None verifiable | Promo, no evidence (unverified) | n/a | https://beverlyboy.com/film-technology/continuity-copilot-ai-catches-visual-errors/ |
| continuity-checker, CONTINUUM | OSS repos | Blind observation, rule judgement; temporal film graph | See S01, S04 | Discipline, provenance | No real-video accuracy (see register) | see register | https://github.com/jtmuller5/continuity-checker ; https://github.com/BenDuske/CONTINUUM |
| EntityBench | Benchmark (generation, 2026-05) | Cross-shot entity consistency; 140 episodes, 2,491 shots; per-shot entity schedule (characters/objects/locations); up to 48-shot recurrence gaps | 3 pillars (intra-shot, prompt alignment, cross-shot) + "fidelity gate" that admits only accurate appearances to cross-shot scoring; 21 cross-shot metrics mixing embedding and LLM judgments (secondary); baseline EntityMem memory bank | Closest published analogue to an entity registry; reports consistency degrading with recurrence distance; DINOv2 vs LLM identity disagreement (secondary) | Code license not stated in README; gate details not read | Unverified (no LICENSE seen) | https://arxiv.org/abs/2605.15199 ; https://github.com/Catherine-R-He/EntityBench/ |
| GroundShot / GroundBench | Method + benchmark (2026-06) | Entity-level consistency vs first valid appearance (ARC metric, secondary) | Agentic: entity visual memory from accepted shots, grounding, verify before storing, retrieve before generating | "Verify before storing" is a useful memory-poisoning guard | ARC definition and code not confirmed | Unverified | https://arxiv.org/abs/2606.20799 |
| VideoMemory | Method + 54-case benchmark (2026-01) | Character/prop/background persistence | Dynamic Memory Bank of visual+semantic descriptors, updated after each shot | Explicit "semantic descriptor + visual" entity record, updated for story change | Metrics not named on abstract page; code unconfirmed | Unverified | https://arxiv.org/abs/2601.03655 |
| EM-Vid | Method (2026-05) | Subject consistency | Entity-indexed latent patch bank; evaluation reportedly samples frames per shot, segments subjects with SAM3, scores with CLIP/DINO (secondary) | Argues full-frame memory entangles entity and scene context | Generator-side; SAM3 use not confirmed on the abstract page | Unverified | https://arxiv.org/abs/2605.23610 |
| MSAVBench | Benchmark (2026-05) | Multi-shot audio-video; subject, layout, illumination consistency | Subject: VLM localiser + DINOv2 + ArcFace pairwise across shots; illumination: rubric VLM pass-rate on adjacent pairs; layout: tool-grounded judge (all secondary). Reports Spearman 0.915 with humans for the overall score | Shows rubric/tool-grounded beats direct VLM scoring (secondary: direct VLM ~0.60 narrative, ~0.41-0.43 layout) | Overall rank correlation is not per-defect precision | Unverified (repo ali-vilab/MSAVBench) | https://arxiv.org/abs/2605.20183 |
| PersonaShot | Benchmark (2026-08) | Person-centric continuity: physical state, emotion, cinematic grammar; ~1,000 segments, 16 metrics | Distilled criterion-specific evaluators | Reports cross-shot scores 25.6-50.0% below per-shot scores (secondary) | No human-agreement figures on abstract page; code not confirmed | Unverified | https://arxiv.org/abs/2608.16717 |
| LogiShot | Model + benchmark (2026-08) | Cross-shot logical coherence | Single VLM judge, fixed prompt, six 1-5 sub-metrics; judge vs human rank corr. 0.68 (logic) and 0.59 (visual consistency), weighted kappa 0.84/0.76 (secondary) | Honest judge validation numbers | Visual-consistency judge is the weakest dimension | "Will be released" (unverified) | https://arxiv.org/abs/2608.08820 |
| MuSS | Dataset + benchmark (2026-04) | Multi-shot subject-to-video | DINO/CLIP keyframe similarity, DINOv2/InsightFace identity, anti-copy-paste variance (secondary) | Copy-paste guard: high similarity can mean a frozen/pasted subject | Generation-oriented | Unverified | https://arxiv.org/html/2604.23789v1 |
| ViStoryBench | Benchmark (image stories; CVPR 2026) | Character identity (CIDS), style (CSD), onstage count (OCCM) | CIDS (secondary): Grounding DINO crop, CLIP for stylised / face models for photoreal, bipartite matching | OCCM-style count check maps to "character vanished/replaced"; CLIP route for stylised art | CIDS formula not verified from the paper | Unverified | https://arxiv.org/html/2505.24862v4 |
| VBench / VBench-2.0 | Benchmark suites | v1: subject consistency (DINO) and background consistency (CLIP) (from my knowledge of the paper, not re-fetched); 2.0: 18 dims incl. identity, clothes, instance preservation (secondary) | Detector/embedding based | Mature code; per-dimension reporting | Single-clip/prompt oriented; dimension-to-method mapping for 2.0 is secondary | Apache-2.0 declared (S10) | https://arxiv.org/abs/2503.21755 ; https://github.com/Vchitect/VBench |
| TransNetV2 | Shot-boundary model | Hard cuts + gradual transitions | CNN, F1 77.9 / 96.2 / 93.9 on ClipShots / BBC / RAI (authors' re-evaluation) | Best published accuracy of the three options; handles gradual | Needs model runtime; speeds only secondary | MIT | https://github.com/soCzech/TransNetV2 ; https://arxiv.org/abs/2008.04838 |
| PySceneDetect | Shot-boundary library | Hard cuts, fades | Detectors: Content (HSV delta, thr 27), Adaptive (rolling avg), Threshold (fades), Histogram, Hash | CPU only, trivial to install; adaptive mode helps fast camera motion | Docs don't claim dissolve handling; one secondary comparison on 200 videos: 65.5% vs TransNetV2 87.0% whole-video accuracy | BSD-3 declared (S20) | https://www.scenedetect.com/docs/latest/api/detectors.html ; https://arxiv.org/pdf/2508.11484 |
| FFmpeg `scdet` / `select='gt(scene,x)'` | CLI filter | Frame-difference score | Global frame difference | Zero extra dependency | Not tested here (ffmpeg not installed in this sandbox); not read from docs this session | LGPL/GPL build-dependent | https://ffmpeg.org/ffmpeg-filters.html |

## 2. Judge reliability: what is established

| Finding | Evidence | Implication |
|---|---|---|
| VLM judges show position bias; in a video A/B test the human-edited video won 55.6% in slot A but 20.2% in slot B, while run-to-run agreement was 83-87% (secondary) | https://arxiv.org/pdf/2607.25300 | Stable output does not mean unbiased output; swap order and require agreement |
| Position bias is systematic and depends on the quality gap between candidates (text LLMs, 15 judges, >150k instances) | https://arxiv.org/html/2406.07791v9 | Bias worst when two options are close, which is exactly subtle continuity drift |
| VLMs prefer a position in pairwise tasks and are steered by prompt structure (image tasks) | https://arxiv.org/pdf/2402.04788 | Randomise slot, keep prompt neutral |
| Best of 13 frontier VLMs finds only 40.7% of true UI differences zero-shot; Hard recall <23%; several hallucinate differences on identical pairs | https://arxiv.org/html/2605.29615 | Expect low recall on subtle diffs and false positives; include identical-pair controls. Domain is web UI, not film |
| VLMs at or near chance tracking identical objects through motion; they re-identify by per-frame appearance | https://arxiv.org/abs/2603.08436 | Do not ask a VLM to "follow" an object across a cut; give explicit crops per shot |
| Rubric-decomposed and tool-grounded scoring raised agreement over direct VLM scoring (secondary) | https://arxiv.org/pdf/2605.20183 | Ask narrow attribute questions, with measured evidence (boxes, ratios) |
| Judge vs human rank correlation for visual consistency 0.59 in LogiShot (secondary) | https://arxiv.org/pdf/2608.08820 | Even tuned judges are noisy on this exact dimension |
| Binary VQA judges have yes-bias; Likert preferred; mean human inter-annotator agreement 66.9% (secondary) | https://arxiv.org/pdf/2605.03475v1 | Humans also disagree: label set needs adjudication |
| Embedding metrics and LLM identity judgements disagree; authors attribute gap to embedding limits (secondary) | https://arxiv.org/pdf/2605.15199v1 | Embeddings = triage signal, never the verdict |
| Perceptual judgment bias: judge can follow description over visuals (S27) | https://arxiv.org/html/2606.02578 | Already covered; keep producer text out of observation |

## 3. State of the art vs marketing

Genuinely supported by published work (still mostly generation-side, self-evaluated):
- Entity-centric memory with per-shot entity schedules is the dominant 2026 approach to cross-shot consistency (EntityBench, VideoMemory, EM-Vid, GroundShot). Consistency degrades with recurrence distance (EntityBench).
- Hybrid scoring (embedding + rubric VLM + tool grounding) is the evaluation norm (MSAVBench, EntityBench, MuSS).
- Cross-shot scores are far below per-shot scores for current generators (PersonaShot, secondary), which supports the claim that per-shot scanning misses a real defect class.
- TransNetV2 is the accuracy leader for shot boundaries in the authors' own protocol.

Caveats on the academic side: nearly all are 2026 preprints from the last six months, rely on VLM judges validated by rank correlation (not defect-level precision/recall), and I did not read the papers' full text or confirm code licenses. Benchmark scores here are not evidence that any verifier built on them catches a specific defect.

Marketing / not verified:
- Scene Fixer, invideo agent, Continuity Copilot: no measurements, no methodology. "Catches continuity errors" demos are cherry-picked by construction. Note invideo itself says post-hoc scanning of finished films is not reliable (secondary).
- Any "memory" product claim: no published comparison against a plain per-pair VLM baseline was found. Whether a memory bank beats sequential pair checking for verification (as opposed to generation) is untested in what I found.

Not found: any benchmark that labels continuity errors in finished, already-generated films and scores a detector on them. No public dataset of this exact task was located (search was limited; absence is not proof). That means ProofFrame's labeled set from the 60 s short is itself a contribution, if shared.

## 4. Gap analysis vs ProofFrame current design

Current (README/spec): per-shot artifact scan using Muse Spark video + frame grid + adjudication; no cross-shot memory.

| Defect found by human | Why per-shot scan misses it | Needed capability |
|---|---|---|
| Boombox shrinks to hand-sized | Each shot internally fine | Per-entity scale relative to a stable reference (person/hand/table) across shots |
| Table swapped between consecutive shots | Same | Scene-element registry with design descriptor, compared in same-scene adjacent shots |
| Character vanishes, another takes seat | Same | Per-shot cast/seat inventory; entry/exit explained by on-screen action or unexplained delta |
| Bag changes material; watch present/absent | Same | Attribute-level record for each recurring entity (material, accessories) with abstention when not visible |
| Face identity drift | Same | Per-character crops compared across shots (embedding triage plus VLM pair judge) |
| Hand insert owner contradicts previous shot | Same | Ownership linkage: sleeve, skin tone, accessories vs candidate owner in neighbouring shots |
| Object both shattered and intact | Caught in-shot (already works) | Extend across shots: state timeline for an object (intact, broken), with allowed transitions |

Additional gaps: shot segmentation is not described as a first-class stage; scene grouping (which shots share a location) is needed so a legitimate location change is not flagged; no mechanism distinguishes legitimate story-driven change from defect (CONTINUUM's declared-change idea, S04); no calibrated false-positive control on "no change" pairs.

## 5. Recommendations (ranked by value / effort)

Ranking assumes self-written code, Meta APIs plus SAM 3.1, bounded paid calls.

1. **Shot segmentation stage, then keyframes per shot (high value, low effort).** Start with PySceneDetect AdaptiveDetector (or FFmpeg `scdet`) for hard cuts; accept an externally supplied shot list when available. Measure recall on the 60 s short; add TransNetV2 only if dissolves/missed cuts show up (it is the accuracy leader in authors' protocol, but speed and fit are unmeasured here). Sources: https://www.scenedetect.com/docs/latest/api/detectors.html ; https://github.com/soCzech/TransNetV2 .
2. **Blind per-shot entity inventory (high value, medium effort).** For each shot, a blind Muse pass (no script, no producer text) outputs structured entities: category, visual descriptor (color, material, design, worn accessories), seat/position, count, visible-or-not flags with abstention; SAM 3.1 supplies a crop and box per entity. Idea from entity schedules/registries in EntityBench, VideoMemory, ViStoryBench OCCM; blind-observation rule from continuity-checker (S01). Sources: https://arxiv.org/abs/2605.15199 , https://arxiv.org/abs/2601.03655 .
3. **Adjacent-shot, same-scene pair judge with controls (high value, medium effort).** Present entity crops side by side (not whole films), ask narrow rubric questions per attribute, run both orders and require agreement, add identical-pair controls to measure the false-difference rate, allow "cannot tell". Sources for design: https://arxiv.org/html/2605.29615 (hallucinated diffs, low recall), https://arxiv.org/pdf/2607.25300 (order effect), https://arxiv.org/pdf/2605.20183 (rubric/tool grounding), https://arxiv.org/abs/2603.08436 (do not rely on VLM tracking through cuts).
4. **Measured scale ratios from SAM masks (high value for the boombox class, low-medium effort).** Compute prop-box size relative to the nearest hand/person/table in each shot; flag ratio changes beyond a threshold only when camera distance cues are comparable, then send to the pair judge. This is my own design hypothesis; no published verification of it was found. Idea of tool-grounded evidence: MSAVBench (https://arxiv.org/pdf/2605.20183). Needs testing against legitimate close-ups.
5. **Cast and presence delta with explanation requirement (high value, medium effort).** Compare per-shot cast and seat occupancy for consecutive same-scene shots; an entity gone or replaced without an exit/entry or cut-away explanation becomes a candidate. Credit: ViStoryBench OCCM for count checking (secondary), CONTINUUM for declared vs undeclared change (S04).
6. **Embedding triage only (medium value, low effort).** DINOv2/CLIP similarity on SAM crops to rank candidate pairs and to match entities across shots; ArcFace only for photoreal faces. Never emit a verdict from embedding distance: EntityBench and MuSS report embedding/LLM disagreement and copy-paste artifacts. Stylised characters: embedding behaviour on them was not found in my search (unverified).
7. **Verify-before-store registry (medium value, low effort).** Only add an entity appearance to the registry after a quality gate (visible, unoccluded, crop confidence); the first valid appearance is the anchor. Credit: GroundShot (https://arxiv.org/abs/2606.20799) and EntityBench's fidelity gate. Prevents a bad first observation poisoning later comparisons.
8. **Object state timeline (medium value, medium effort).** Extend the existing shattered/intact check across shots with allowed transitions (intact to broken allowed, reverse not). Idea: TC-Bench temporal states (S13).
9. **Evaluation set before more features (high value, medium effort, do early).** Encode the human's 8 defects as labeled cases with hard negatives (legit location change, legit costume change, close-up vs wide) and injected controls; report recall, false positives per minute, and judge order-flip rate. LogiShot-style judge-vs-human numbers are the model for reporting honestly (https://arxiv.org/pdf/2608.08820). Do not claim SOTA.
10. **Defer:** full temporal scene graph or vector-DB memory (no evidence it beats rec. 2-3 for verification), ownership-of-hand linkage beyond a pair-judge question, trained evaluators (PersonaShot-style distillation needs data).

## 6. Open questions

- Can Muse Spark 1.3 return reliable shot timestamps, and how many images can one call take? Not tested in this review (see S23).
- Per-defect recall of any approach above on ProofFrame's footage is unknown until rec. 9 exists.
- Licenses for EntityBench, MSAVBench, GroundShot, PersonaShot, MuSS were not established; treat as read-for-ideas only.
