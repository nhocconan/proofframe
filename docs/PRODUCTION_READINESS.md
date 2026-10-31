# ProofFrame — Production Readiness (2026-10-31)

The author will use ProofFrame in a real company project after the hackathon.
This note separates what is verified from what is still open. Every "verified"
item was exercised on the real stack or in the Docker test suite — nothing
here is aspirational.

## Verified (2026-10-31)

- Three modes live on the local stack: video-only autonomous scan,
  video+contract compliance, and dialogue verification (blind double-pass ASR
  against locked script lines, word-level diffs, duplicate-line detection).
- Full Docker test suite green: 331 tests, including a regression test for
  every fix listed below.
- Budget accounting: atomic reservations, enforced per-run/per-project caps
  (currently $15 / $140), 0 unknown-cost calls across all real runs so far;
  every run's estimated cost is recorded in its report.
- Fail-closed semantics: provider errors, budget stops and unverifiable
  checks surface as ERROR / UNCERTAIN / REVIEW, never PASS. Demonstrated in
  production: a full worker disk turned 20 checks to ERROR instead of
  passing them.
- Structured findings with evidence frames and timestamps, consumable as
  generator feedback; repair-roundtrip examples under `examples/`.
- Deterministic EDL → dialogue-contract compiler for the production
  pipeline (`scripts/compile_edl_contract.py`), validated against the
  contract model + JSON schema and against a real production EDL.

## Fixed during hardening (each was a real production-class bug)

- Per-run scratch leak filled the worker's 2 GB /tmp and ERRORed later runs
  → scratch is now removed on every exit path (pf-verify-0.17). If a worker
  image is ever rebuilt from a pre-fix state, purge `/tmp/pf-*` once.
- Chunked continuity audits ignored their scope, re-auditing the whole film
  per chunk (~6x continuity cost, duplicated findings) → audits are scoped,
  keeping one neighbouring shot on each side for boundary pairs.
- Decoded-QC coverage demanded 1 ms timestamp contiguity, ERRORing clean
  concat/re-encode files → tolerance is one frame duration; larger gaps or
  overlaps still fail closed.
- Dialogue comparator rejected typographically clean ASR (case/punctuation)
  → comparison is word-level after case/punctuation folding.

## Known limits — read before company production use

- Video-only recall is limited on story/logic/audio defect classes. On the
  EP01 regression set (19 human-labelled defects, not fully annotated):
  strict scorer recall 1/19, with ~12 distinct real defects adjudicated by
  hand (see `private/RUN1_ADJUDICATION.md`). Use contract + dialogue modes
  for those classes; video-only is a discovery scan, not a complete gate.
- The evaluation set is small (one episode, 19 labels). Grow it with company
  content before trusting thresholds; precision on unlabelled findings is
  currently unmeasurable, so keep a human adjudication step.
- Single worker, serial runs: a full-episode contract verification takes
  tens of minutes. Suitable for overnight QC gates, not yet a
  high-throughput service.
- The local stack is single-machine docker compose. A company deployment
  still needs: its own sizing, persistent volumes + Postgres backups,
  secret management beyond a repo `.env`, and access control on the API
  token.
- Costs are list-price estimates from API usage, not invoices; Meta model
  availability/pricing can change under the integration.
- Repository state: the hackathon work is currently UNCOMMITTED in the
  working tree (git identity is set to the author). Commit and tag a
  release before any company use.
