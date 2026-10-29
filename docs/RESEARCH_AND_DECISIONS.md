# ProofFrame V3: research and product decisions

Read alongside SOURCE_REGISTER.md. Sources are referenced as [Sxx]. This document separates observed capabilities, limitations, and our engineering choices. The objective is a usable verifier in the user's Content Engine, AI-film and children's-video pipelines, not a claim to have invented video verification.

## Executive decision

Build a production acceptance service with evidence-backed checks and versioned repair requests. Do not fork an entire research benchmark or wrap one model in a more elaborate critique prompt. Keep the strongest currently useful model available for difficult judgments, while extracting repeatable media checks, approved intent, evidence collection and regression management out of that model's conversation.

The value proposition is **less total spend and less owner review at a comparable or better measured defect-escape rate**. A cheaper judge that misses failures or causes unnecessary rerenders is not a win. Provider neutrality means stable domain contracts and honest capability negotiation, not equal performance across models.

The immediate product is video-first. It accepts upstream text and reference assets because they define the intended result. It is not a replacement for the Content Engine, a general asset-management SaaS, an autonomous director, or a new video generator.

## 1. Direct and adjacent implementations

### Scene Fixer: strongest directly relevant product UX

Observed: the product page offers cross-shot continuity detection followed by user-confirmed edits through Runway Aleph. It explicitly uses Claude Opus for deep scans and Haiku for free scans. Runway's official event page corroborates its third-place award. Detection quality and preservation guarantees were not independently tested. [S02-S03]

Learn: side-by-side comparison, a small highlighted defect, targeted user control, and editing existing footage rather than discarding the whole sequence. These are useful product patterns, especially when a user is tired of rerender loops.

Do not assume: a corrected wardrobe leaves every other property unchanged, or that a product demo proves a general-purpose repair success rate. A vendor's preservation language must become assertions in our regression suite, not assumptions in our engine.

Our direction: distinguish editable overlays, audio, source-shot generation and assembly. A warped brand logo should usually be fixed in deterministic compositing, not by another costly whole-shot generation. A repair request carries explicit preservation checks and returns to verification before acceptance.

### continuity-checker: unusually good verification discipline, limited perception evidence

Observed: source separates frame observation from rule judgment; the reader does not receive canonical answers. Rules distinguish constant, progressive and declared changes. Repairs overlay the spec rather than rewriting its answer key. The inspected Gemini adapter targets Gemini 2.5 Pro, not Flash. The experiment log explicitly states that hosted model calls had not run and reported scores came from a placeholder pixel reader. [S01]

Learn: blind observation, abstention, unchanged-spec repairs, content-based rerender caching, and evaluation isolated from the detector. These are more useful than copying the project's four agent names.

Do not inherit: sparse fixed sampling as sufficient coverage for actions, occlusion reasoning, identity changes or synchronized audio. Its offline tests establish engineering behavior, not real-video accuracy.

Our direction: preserve those boundaries, then supply real-media grounding, assertion-specific evidence coverage, hard negatives and external repair execution. Treat this repository as a focused reference, not a production platform already proven to outperform the user's current review process.

### CONTINUUM: the strongest reference for production memory and dependencies

Observed: the project defines a temporal film graph, change propagation, coverage checks and observed/inferred/confirmed information. It exposes separate real and stub vision modes. The inspected SKEPTIC is a Gemini 3.5 Flash agent whose instructions favor confirming a finding. [S04]

Learn: changes have consequences beyond neighboring shots; production facts need provenance and authority; missing planned coverage can be detected before final editing. A past event may validly change a prop or costume later in story time.

Do not inherit: six named agents as the default design, shared-model agreement as independent validation, or a confirmation bias that can trigger expensive automatic repairs. Their on-set risk tradeoff need not match a generative pipeline's rerender economics.

Our direction: a bounded workflow with separately typed observations, hypotheses, approved intent and release decisions. Use a dependency graph in PostgreSQL initially. A second model pass must obtain additional evidence or test an alternative explanation; another opinion alone adds limited assurance.

### AI Video Production Verifier: useful preflight, not media inspection

Observed: locked production facts are checked against proposed shot plans; deterministic rules cover duration, events, dialogue, characters, props and generation segments. Semantic auditing is explicitly experimental. The repository's stated boundary excludes inspecting rendered frames/video. [S05]

Learn: reject a plan that already violates locked intent before paying for generation. Deduplicate issues by root cause, and point to the exact field that needs correction.

Do not inherit: a 100-minus-penalties score as a release criterion. Ten cosmetic improvements must never compensate for a wrong required claim or missing story event.

Our direction: preflight becomes the first ProofFrame gate, followed by first-frame/shot and assembled-output checks. Port selected rules only after license and implementation review; do not add a second creator UI to the existing production workflow.

### CASR Core: cost-aware repair planning, not measured visual verification

Observed: the Java library consumes metadata, issues, anchors and task status. The inspected policy search compares hand-authored action paths with state-sensitive estimated gains, cost, time, risk and success proxies. Its benchmark is described as deterministic and its execution endpoint as simulated. [S06]

Learn: regeneration is only one possible action; choose actions based on failure attribution, budget and downstream consequences. Recording repair outcomes can later improve these decisions.

Do not inherit: numerical success probabilities as calibrated predictions, hard-coded cost savings as measured savings, or preview fallbacks as successful final delivery. A first-frame slideshow is not a valid repair for a required motion event.

Our direction: a transparent rules-based repair selector first. Apply hard preservation and capability constraints before comparing cost. Learn success/cost distributions only after real outcomes are logged, with enough failures retained to avoid survivor bias.

## 2. Evaluation and perception building blocks

### NVIDIA Cosmos Evaluator

Observed: four checker families cover motion-mask hallucination, object correspondence, attributes and physical plausibility. The attribute checker separates question generation from VLM answering, reports execution errors separately and supports external endpoints. Its default is one sampled frame; the documented model choices are not Gemini-only. [S07-S09]

Learn: explicit checker interfaces, per-check results, model-role separation, cancellation and recorded inputs. Where source or control geometry exists, compare against it rather than relying exclusively on text.

Limit: some checks assume an original/reference video or expected object positions. Our arbitrary film may not have that ground truth. A frame-level attribute match cannot establish that an event happened over an entire clip.

Decision: learn and optionally port a narrow checker, not the whole service fleet or build system. Our coverage policy is assertion-specific and our outputs must include repair-relevant evidence.

### VBench / VBench 2.0

Observed: VBench 2.0 goes beyond simple visual scores; its dimensions include identity, clothes, dynamic relations, human motion and physical plausibility. The documented environment is a substantial research stack, and customized-input support varies by dimension. [S10-S11]

Learn: evaluate failure dimensions separately and include specialized perceptual signals where they are validated. An identity or clothing metric can be a useful candidate signal.

Limit: a benchmark score is not a production acceptance contract or a localized repair plan. A high aggregate score cannot excuse violating a required brand asset or plot event. Research dependency/model licenses need a separate review.

Decision: run selected metrics as offline baselines or optional workers, not in the initial API dependency graph. Never call a similarity score proof of fictional-character identity.

### DSG, T2V-CompBench and TC-Bench

Observed: DSG studies dependency-aware visual questions; T2V-CompBench evaluates composition such as attribute/action binding and relationships; TC-Bench explicitly studies temporal state transitions with assertion-based evaluation. [S12-S14]

Learn: make requirements atomic, preserve dependencies, and test both invariants and required changes. If a person cannot be observed, an outfit question may be unanswerable rather than false. A scene that starts and ends correctly can still omit the required transition.

Limit: these are evaluation methods and datasets, not complete production services. Code/data reuse rights are separate; T2V-CompBench's top-level license was not established here.

Decision: derive our own production assertion grammar and labeled cases. Do not claim that screenplay-to-assertions or temporal-state evaluation is a new invention.

### VideoMind and ActiveLook

Observed: VideoMind provides trained temporal grounding and verification roles; ActiveLook proposes demand-driven temporal/spatial resampling and candidate fusion on that base. [S15-S16]

Learn: find a plausible interval, gather sharper evidence, then reassess. Increase time resolution for a brief gesture and spatial detail for an ambiguous prop; do not blindly resubmit the full film.

Limit: the published implementation depends on specialized model training and its own tasks. Replacing those models with generic API calls does not reproduce its benchmark results. ActiveLook is an exploratory reference here, not independently established SOTA.

Decision: adopt the search/refinement policy as an engineering hypothesis and evaluate it with an ablation against fixed sampling. Keep refinement bounded by evidence needs and budget.

### VideoScore2

Observed: a trained evaluator covers visual quality, text alignment and physical/common-sense consistency, with human feedback and interpretable assessments. [S17]

Learn: specialized evaluators and preference data can help rank candidate renders or diagnose quality dimensions. Such models may be useful later if a narrow error class has enough labeled data.

Limit: ranking attractive clips is not verifying every mandatory production constraint. Published benchmark performance cannot be transplanted to Vietnamese dialogue, stylized children’s animation or this user's film.

Decision: optional offline baseline; later use to rank candidates that already satisfy hard constraints. Do not use a single overall score to authorize publication or repairs.

### TwelveLabs and broadcast QC products

Observed: TwelveLabs offers video analysis, structured output and timestamped segmentation; BATON is an established example of automated file-based QC. [S18-S19]

Learn: separate media observation/indexing from policy and learn technical-QC fault categories. Retrieval may help with a long episode or a series archive.

Decision: a future observation adapter, not a dependency needed to validate a few shots. FFprobe/FFmpeg and production metadata cover the first technical checks; a search index is not the source of production truth.

## 3. What remains a defensible opportunity

The inspected field already contains continuity checks, agents, repair loops, production graphs and scores. Do not pitch those individually as novel. The opportunity is a tested integration across the user's real production chain: approved intent -> localized evidence -> least-disruptive repair -> fresh regression -> release eligibility.

Concrete differentiation to demonstrate, not merely claim:

1. Source-aware repairs: repair the overlay, audio, prompt, shot or assembly that actually caused the failure.
2. Reliable handling of uncertainty and incomplete coverage, including cases where expensive models are still required.
3. Immutable intent and artifact hashes so a producer cannot make a failure disappear by changing the test.
4. Evidence and regression at the appropriate scope: shot, scene, episode and final export.
5. Measured cost per accepted deliverable, review time and escaped defects against the user's current Opus-heavy process.
6. The same protocol used by Content Engine and browser-driven film production without requiring a universal generation API.

This is an engineering and data advantage. It is not a promise that a small model will outperform Opus, or that every error is automatically fixable.

## 4. Make model comparisons fair

The user reports that Opus High/Extra has been necessary to make outputs publishable. Keep that as a production observation and a baseline, not a universal ranking. Confirm the actual API model and reasoning configuration; UI labels are not API identifiers.

Run two comparisons. First hold evidence, prompts, settings and budgets constant to compare judge capability. Then compare end-to-end systems, including evidence extraction, tool calls, repair costs and human review. Otherwise the team may mistake better sampling for a smarter model, or claim cheapness while excluding rerender costs.

A second pass from the same family is not independent evidence. Cross-model agreement is also not a calibrated probability. Require task-specific human-labeled holdouts and preserve uncertain outcomes. Perceptual judgment bias research motivates checking whether verdicts follow the visual evidence or merely persuasive producer descriptions. [S27]

## 5. User-specific delivery order

First: one real film shot with an explicit wardrobe/prop requirement, plus a hard-negative case. Second: a source-aware repair round trip and a deliberately introduced regression. Third: Content Engine overlay/approved-copy checks. Fourth: children's-video narration/illustration alignment and editorial review signals.

Do not make identity recognition, precise lip-sync scoring, universal physics or a definitive age-comprehension score prerequisites for the first useful product. They need specialized data and validation. Keep the public hackathon demo focused on the adult-fiction verification loop; the other profiles demonstrate extension without misrepresenting an educational chatbot as the core product.

## 6. Industrial implementation decisions (2026-10-29)

Current review used primary product documentation, the EBU recommendation PDF and research abstracts. Products were not installed or independently benchmarked. The table is a capability comparison, not a market ranking. See SOURCE_REGISTER S37–S43.

| Reference | Technique to adopt | Decision and evidence |
|---|---|---|
| [Vidchecker specifications](https://www.telestream.net/vidchecker/specs.htm) and [BATON documentation](https://interrasystems.com/file-based-qc.php/QS/video_tutorial-baton.php) | Decode media and check delivery parameters; expose timecoded QC separately from subjective review | Extended the existing black/freeze/silence layer with loudness and true-peak measurement. This covers two delivery measurements, not the products' codec, HDR, caption or PSE scope |
| [EBU R128 v5](https://tech.ebu.ch/docs/r/r128.pdf) | Programme loudness and reconstructed true peak, with explicit delivery limits | Added finite fractional tolerances and directional limits. The illustrative contract uses −23 LUFS ±0.2 LU and at most −1 dBTP; users must approve their actual delivery targets. No meter certification, automatic normalization or platform-wide compliance claim |
| [TwelveLabs Analyze](https://docs.twelvelabs.io/api-reference/analyze-videos) | Structured timestamped segments and explicit asynchronous states | Keep timestamped evidence/coverage as the public interface. Vendor adapter deferred until a controlled task comparison justifies it; no silent provider replacement |
| [EG-VQA](https://arxiv.org/abs/2606.24797) and [Evidence-Backed VQA](https://arxiv.org/abs/2607.11862) | Assess evidence grounding separately from answer correctness | Added frozen-cohort comparison with byte-bound media, labels, contracts and baseline reports; existing controls retain separate confirmed and surfaced-review tracks. Neither harness nor seek links prove spatial/semantic evidence sufficiency |
| [WhisperX upstream](https://github.com/m-bain/whisperX) | Separate transcription from forced alignment and speaker labeling | Candidate for an optional qualified audio worker, preserving the existing voice pipeline. CPU execution is documented, but language alignment models, runtime cost and weights require qualification before import. ASR/alignment does not validate lip-sync |

The audio meter uses `ebur128=peak=true` and independent decoded coverage. Its 0.1-unit printed resolution is represented as a rounding interval when testing limits; boundary-straddling measurements remain UNCERTAIN. Silence/sub-gated integrated loudness does not become a fabricated floor-value PASS. Evidence records source scope, settings and detector version. Source bytes remain unchanged.

A real, licensed 60 s Tears of Steel excerpt measured −14.6 LUFS / −0.1 dBTP with zero provider calls and failed the illustrative contract. That demonstrates execution on decoded media. It is neither a quality verdict on the film nor an R128 compliance test of a complete programme.

Next priorities: (1) collect owner-adjudicated, episode-separated holdouts and compare actual Opus/Meta workflows with measured review time; (2) qualify localized crops/visibility controls on the remaining continuity misses; (3) align approved dialogue and subtitles using the existing audio artifacts; (4) qualify additional delivery checks where a destination needs them. Defer universal quality scores and PSE/identity/lip-sync automation until appropriate validation exists. Do not expand a vendor list in place of measuring defect escapes.
