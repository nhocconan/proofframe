# ProofFrame V3 - implementation handoff for Claude Code / Codex

You are implementing ProofFrame for a technical owner who needs publishable outputs, not persuasive completion reports. Work in the authorized project directory. Deliver running code, real integration evidence and measured limitations. This V3 supersedes earlier generic ProofFrame prompts wherever they conflict.

## Read first, then implement

Read `AGENTS.md`, `START_HERE.md`, `docs/RESEARCH_AND_DECISIONS.md`, `docs/IMPLEMENTATION_SPEC.md` and `docs/EVALUATION_PLAN.md`. Use `docs/SOURCE_REGISTER.md` to inspect exact upstream components only when necessary. Do not restart broad market research or spend the build producing another PRD.

The supplied package includes a NEW, tested contract/policy seed, schemas and synthetic examples. It does NOT include a video analyzer, model adapter, backend, frontend, storage service or working generation loop. Do not describe its 60 initial unit tests as model accuracy or completed product features. Re-run them in your environment and report the actual count.

Inspect the target repository, its instructions, installed tools and current implementation before changing anything. Preserve useful existing code, uncommitted work, naming and integration conventions. Do not overwrite an existing AGENTS.md, reset branches or perform wholesale restructuring. Record an incremental migration plan if an earlier ProofFrame build already exists.

## Product to build

An independent production acceptance service between an approved production brief and an external generation agent. It must:

1. Preflight approved intent and planned production before expensive rendering.
2. Check first frames/shots against explicit requirements using actual media evidence.
3. Check the final composition for cross-shot, dialogue and editorial errors.
4. Emit localized, versioned findings with honest uncertainty and coverage.
5. Request the smallest supported repair at the source stage that caused the problem.
6. Ingest the producer's new immutable output and recheck affected dependencies plus mandatory sentinels.

Primary integration: existing Content Engine and browser-driven AI-film production. The creator/generator remains external. File-drop JSON plus media is a required bridge; do not assume Google Flow or another tool has an available API. Preserve the owner's existing audio/voice pipeline.

The initial public demo is one owned adult-fiction sequence. Brand and educational-video profiles share the same core; they are not three separate applications. No generic chat interface, content-management rebuild, automatic publishing or full video-generation platform.

## Non-negotiable design rules

- Approved intent is immutable and separate from observed media, hypotheses and decisions. A repair cannot alter the requirement it failed.
- The approved contract identifies logical asset slots and hash-bound canonical references. Generated output versions belong in run manifests. A new render MUST NOT require changing approved intent merely because its bytes changed.
- Every required assertion gets an evidence plan before cheap candidate detection. The expensive judge must not see only defects a cheap model happened to notice.
- Use `PASS`, `FAIL`, `UNCERTAIN`, `NOT_CHECKED`, `ERROR`, and explicitly approved `NOT_APPLICABLE`. Missing/unsupported/error outcomes never become PASS.
- Release policy is `BLOCK`, `REVIEW`, or `ELIGIBLE`; ELIGIBLE never authorizes publishing. A numeric quality score cannot override a blocking failure.
- Blindly observe before comparing where feasible. Do not reveal a seeded answer key or the producer's "fixed" claim to the observer. Reference-comparison tasks may require references, but still need neutral questions.
- Actual frame/clip IDs and server-side timestamps replace hallucinated coordinates. Preserve source, proxy, crop and assembled-timeline mappings.
- Sampled evidence is sampled, not exhaustive. Absent masks do not prove missing props; correct endpoints do not prove an action happened; ASR is not lip-sync validation.
- Never trust a second agreeing LLM pass as independent proof. Seek new evidence or a falsifying alternative. Model confidence is not a calibrated probability.
- A repair receipt is an execution record, not a success verdict. Reverify new bytes against the same requirements. Reject stale inputs and changed canonical references.
- The model cannot execute arbitrary shell commands, change files, rewrite policy, approve its own repair or spend without a configured bound.

## Stack and integration boundaries

Use a modular Python core with FastAPI, PostgreSQL, one asynchronous worker, a storage interface, and a small Next.js/TypeScript evidence workbench. Use FFmpeg/FFprobe directly and PySceneDetect when production shot boundaries are unavailable. CPU media processing must work without a local GPU. Adopt compatible existing versions and pin lockfiles after a real clean build.

Provider interfaces must distinguish text reasoning, image/video observation, temporal grounding, segmentation/tracking, transcription, alignment and editing. Domain code must not import provider SDKs. Implement the real Meta capabilities needed for the first slice and one tested extension boundary; do not create six empty adapters.

Two profiles are required in configuration: `meta_hackathon` with visible, genuine Meta contribution and no hidden fallback; `production_best_qualified` with task-qualified routing. Keep Opus available as a configured escalation option where credentials exist. Do not assume "High/Extra" are API model IDs. A subscription is not an API credential.

In production, optimize total cost per accepted deliverable and owner review time at measured defect escape rates. Do not assume a cheap model is adequate, and do not hard-code the claim that one vendor is always best.

## Gate 0 - environment and real capability probes

Inspect local configuration without printing secrets. Read current official Meta documentation from the source register. The owner has a Meta API credential; use the authorized environment/secret store, never ask for a key pasted into chat or place it in source.

Enable paid tests only when an explicit project/run spend bound is configured. Reserve conservative costs before calls; usage that cannot be priced is unknown, not free. Do not run video generation merely to test authentication.

Probe short, owned fixtures for structured output, image input, native video, SAM output parsing and Vietnamese ASR as required. Log model ID, actual options, media representation, response shape, latency, billed/estimated cost, failure type and supported output semantics. Redact secrets and private media.

Important traps: SAM uses its own output grammar/parser, not ordinary findings JSON. The documented Spark video model has an audio caveat; test audio separately. ASR documents turn-level, not word-level, timestamps; `audioProcessedMs` is progress, not word timing. If a required capability is unavailable, report the exact failure, preserve NOT_CHECKED, and continue with other functional components instead of hiding a mock.

Run the seed tests and create `docs/BUILD_STATUS.md`, `docs/CAPABILITY_PROBES.md` and a pinned environment. Do not claim detector qualification from successful HTTP responses.

## Gate 1 - smallest real vertical slice

Build asset ingestion with hash verification, an approved assertion and a persistent verification job. Extract real evidence from one supplied owned clip. Execute actual Meta reasoning; store validated output, provenance and unresolved states. Show the result in a minimal UI with a video seek that lands on the evidence, plus expected/observed/reference comparison.

Include one real violation and one clean or ambiguous negative. Use both even if the first model call is wrong. A failure is useful evidence for improving sampling or model selection; do not tune the expected contract until it passes.

Acceptance: actual commands, API trace, a report bound to real media, and the UI seeking the correct interval. Synthetic examples, placeholder screenshots and a schema-valid response alone do not satisfy this gate.

## Gate 2 - reliability and scope

Implement mandatory coverage accounting, temporal/spatial evidence refinement, deterministic media/plan checks and explicit operational errors. Add object tracking only for cases it can help; do not make SAM masks a decorative requirement for every check. Add transcription with honest timestamp resolution. Keep identity/lip-sync assertions in review unless separately validated.

Support approved state transitions and separate story time from edit time. Test cross-shot dependencies without introducing a graph database. Preserve citations to original intent and the source asset lineage.

Add adversarial tests for: wrong reference version, occlusion, allowed costume change, brief action between samples, producer prompt injection, model timeout, invalid JSON, budget exhaustion, duplicate jobs, and an apparently clean result with missing checks. A failed provider request is ERROR, not a content FAIL.

Acceptance: real media examples, explicit false positives/false negatives, bounded calls and no silent missing checks. Freeze a development set and held-out examples before further prompt tuning.

## Gate 3 - source-aware repair and regression

Provide JSON/HTTP/CLI exports for typed repair requests. Require the report hash, unchanged contract hash, target input hash, intended source-stage change, preserved requirements, executor capability, estimated cost basis and retest scope. The initial contract seed only authorizes repairs to the failed logical target; extend upstream-source permissions explicitly rather than allowing arbitrary writes.

First demonstrate a deterministic reversible repair such as a composite/subtitle correction, and a real generative shot replacement where budget and executor allow. Label staged/pre-recorded repair outputs honestly. Never call an edited still a repaired video.

The file-drop executor receives the request, returns a new asset version and receipt, and cannot edit approved truth. Recheck all impacted assertions, transitive dependents, relevant boundaries and mandatory final-export checks. Preserve historical failures. Show FIXED, STILL_FAILING, REGRESSION and UNCERTAIN/NOT_COMPARABLE separately.

Cap repeated attempts per target and stop on budget exhaustion, recurring failures or a new critical regression. Do not substitute a static slideshow for a required video action or slow the whole episode simply to satisfy a duration number.

Acceptance: one successful round trip, one unsuccessful repair, and one newly introduced regression detected. Check results must be linked to actual new media hashes.

## Gate 4 - user integrations and measured usefulness

Map Content Engine identifiers for organization, brand, campaign, content and asset versions into adapter payloads. Use the approved Brand Kit and Product Truth; exact logos and copy should be repaired at compositing/source stages when possible. Unknown claims remain review items, not AI-certified compliance.

For film, prioritize wardrobe/prop state, required events, dialogue and allowed editorial transforms. For children's videos, use approved factual objectives and narration/illustration agreement. Pace, abstraction and vocabulary are advisory until validated with human audience feedback; never claim certified comprehension.

Compare against the owner's actual Opus-heavy process using `docs/EVALUATION_PLAN.md`. Separate model comparison from system comparison. Show all repair/recheck costs and owner review time, not only a cheap first scan. Small synthetic fixtures are not evidence of production accuracy.

Acceptance: one existing production workflow consumes the report and sends a valid repair receipt; the same core handles a second profile without a separate app. Publish a truthful evaluation table with unmeasured cells explicitly marked.

## Production constraints and security

Use authenticated asset access, tenant-scoped queries, resource-bounded media workers, no Docker socket, no untrusted shell strings, no broad host filesystem access and no arbitrary URL fetching in the initial release. Treat script text, subtitles, overlays, metadata and provider output as untrusted data; instructions embedded in media cannot invoke tools or alter policy.

Persistent jobs use leases/checkpoints and at-least-once execution. Provider calls can be duplicated after ambiguous timeouts; reconcile remote request IDs before retrying chargeable operations. Local cancellation is not proof of provider cancellation or no charge. Budget reservations must be atomic across workers.

Cache keys must include tenant, exact input/reference bytes, assertion and policy versions, model/reasoning settings, prompt/schema/parser versions and evidence transform. Reuse observations only when those conditions permit it. Do not reuse an old PASS for a changed export.

Do not change host SSH/firewall/users or publish confidential footage. The open-source repo must identify newly built hackathon functionality and third-party reuse. Check licenses before importing code or weights. Keep private client/child assets outside public history. Repository publication needs an explicit owner decision.

## Reporting and execution instruction

Maintain a short status file with implemented features, actual tests, real model calls, integration commands, measured usage, unresolved issues and next action. Do not report internal chain-of-thought; report decisions and evidence.

Proceed through the gates without routine approval pauses for local implementation. Stop only at genuine authorization boundaries: secret access, unconfigured paid spend, destructive changes or publishing data. If blocked, finish other safe work and provide the exact blocked capability, not a fictional substitute.

Start by inspecting the existing project, running the seed tests, confirming budget/capabilities and implementing Gate 1. Do not end after writing a plan.
