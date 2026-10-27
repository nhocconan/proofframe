# ProofFrame V3 - research, implementation handoff and tested contract seed

Prepared 2026-10-27. This package replaces earlier ProofFrame recommendations where they conflict.

## What is here

- A primary-source competitor analysis, source register and architecture for the user's real production workflows.
- A full implementation handoff for Claude Code / Codex.
- Newly authored Python/Pydantic contract models, fail-closed policy checks, repair binding checks and a small exact timeline mapper.
- Generated JSON Schemas, synthetic illustrative inputs, three policy-profile drafts and unit tests.

## What is NOT here

No video analyzer, Meta adapter, production backend/UI, media decoder, generator integration, authentication service, budget ledger or deployed product has been implemented in this package. No user's API key was used. No competitor's tests or model accuracy were reproduced. The 60 tests initially executed here validate our own contract logic, NOT video understanding. See `validation/TEST_RESULTS.txt` and `validation/ENVIRONMENT.json` for actual execution.

Metadata consistency does not prove that the referenced media exists, that its hash was honestly computed, or that a model interpreted it correctly. The application must verify files, compute hashes, protect canonical authority and bind records to authenticated execution traces. The seed's frozen models are convenient value records, not a security boundary or substitute for database immutability.

## Start the coding agent

Open the target repository and give the agent `HANDOFF_CLAUDE_CODE_CODEX.md` plus this folder. Do not overwrite an already implemented project with the seed. The agent should inspect existing code, run the tests and implement the first real media-to-evidence slice.

Copyable kickoff:

```text
Read ProofFrame_V3/HANDOFF_CLAUDE_CODE_CODEX.md and execute it in this repository.
This V3 supersedes earlier ProofFrame specifications where they conflict.
Inspect existing code first; preserve useful work. Run the supplied contract tests,
verify authorized Meta capabilities within configured spend bounds, then implement
Gate 1 using real owned footage and real evidence. Continue incrementally.
Do not stop after planning or report mocks/schema tests as a working video verifier.
```

Adjust only the folder prefix if the package is unpacked directly at the repository root.

## Run the seed locally

Requires Python 3.11+; Python 3.12 is a suggested application runtime, not a requirement inferred from the local test environment.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/export_schemas_and_examples.py
```

Dependencies are compatible ranges for this seed. `validation/ENVIRONMENT.json` records exact packages used for its tests; the implementing agent must create the full application's tested lockfiles. Installing dependencies requires normal network/package access.

## Document map

`docs/RESEARCH_AND_DECISIONS.md`: strengths, limits and reuse decisions for competitors and research.

`docs/IMPLEMENTATION_SPEC.md`: pipeline, authority model, media/time handling, provider capabilities, repair protocol, security and gates.

`docs/EVALUATION_PLAN.md`: comparison with the current Opus-heavy workflow, real-data holdouts, metrics and staged automation.

`docs/SOURCE_REGISTER.md`: primary source URLs, inspected file hashes and inspection limits.

`schemas/`: machine-readable schema exports for the narrow seed, not the entire planned service API.

`examples/`: synthetic contract/report/repair examples. Their `fixture://` media and repeated-letter hashes are placeholders; do not present them as real outputs.

`profiles/`: starting requirements and routing policies, NOT calibrated model-quality thresholds or implemented checkers.

## Adoption notes

Keep approved contract hashes stable across new output revisions. Generated media hashes are in each verification report/run manifest; canonical references are hash-bound in approved intent. Receipt validation compares against the current run snapshot and rejects stale changes. Production concurrency still needs a transaction/compare-and-swap in persistent storage.

The seed's exhaustive interval coverage means an instrumented scan covers the specified interval; it does not prove a semantic detector never makes mistakes. Native video input alone is not exhaustive inspection. Generic sparse evidence must not claim universal absence or identity correctness.

The public demo can use owned, non-sensitive fiction footage. Keep Content Engine client assets and private child footage out of the public repository. Choose the new project's public license explicitly and preserve third-party notices for any code actually imported.
