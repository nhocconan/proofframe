# ProofFrame — Run & Improvement History

Every paid verification run, what it found, and what changed because of it.
Costs are list-price estimates from each run's own report (not invoices).
Meta spend counts against the project's $140 cap; ElevenLabs Scribe spend is
billed separately by ElevenLabs and never touches the Meta ledger.

## Verification runs (chronological)

| Date (ICT) | Run | Target | Mode | Decision | Cost | Headline |
|---|---|---|---|---|---|---|
| 2026-10-30 | run-b3ee03d29f6d4c369649 | smoke assets | contract | ELIGIBLE | $0.00 | Early smoke run |
| 2026-10-30 | run-cebe314a0de34ab5900b | smoke assets | contract | REVIEW | $0.00 | Early smoke run |
| 2026-10-31 | run-7e1df17b73a44464a1c3 | EP01 V4 master (485.8s) | video-only | BLOCK | $11.81 | Baseline scan. Strict scorer vs 19 human-labelled defects: 1/19 exact; manual adjudication found ~12 distinct real defects incl. an R0 carry-handle design flip two human passes had missed |
| 2026-10-31 | run-009b7aae9d9d43cbbd54 | EP01 V4 master | contract (43 assertions) | BLOCK | $3.56 | Only blocking FAIL: r0-handle-folded (observed raised — real defect). 20/43 checks ERROR "No space left on device" — ProofFrame's own scratch leak, not the film |
| 2026-10-31 | run-76f4a398079f40cfa956 | C01 workprint (V5) | — | REVIEW | $0.00 | Died on the same full /tmp (worker scratch) |
| 2026-10-31 | run-a3d2f7b1a7aa4f2f818a | C01 workprint (V5) | video-only | BLOCK | $0.65 | Garbled dial text in macro S03; pendant-lamp continuity flag (later adjudicated a non-defect) |
| 2026-10-31 | run-775a39bfea1a4f7c9146 | C01 workprint (V5) | contract (scoped) | REVIEW | $0.49 | 8 PASS / 0 FAIL / 5 UNCERTAIN; all 5 adjudicated by the film team |
| 2026-10-31 | run-639d2d4b7c334bf997b4 | EP01 V4 master | contract (43 assertions) | BLOCK | $8.30 | Clean post-fix baseline: 15 PASS / 4 FAIL / 23 UNCERTAIN / 1 ERROR. r0-handle-folded still FAIL; continuity FAIL with 12 confirmed (lantern change, handle flips, bottle, watch wrist); the 1 ERROR is operational (Meta file 404), old qc-* overlap errors gone |
| 2026-10-31 | run-272d2c4067ad4cbcb964 | C01 workprint (V5), 13 locked lines | dialogue (Meta ASR only) | BLOCK | $0.0068 | 5 PASS / 4 FAIL / 4 UNCERTAIN. Independent adjudication: all 4 FAILs were ASR/comparator artifacts (digit rendering, segmentation echo) — the measurement that motivated the Scribe upgrade |
| 2026-10-31 | run-d10a4fe125264aed938c | C01 workprint (V5), 13 lines | dialogue (Meta + Scribe, provider voting) | BLOCK | $0.0110 total (Meta $0.0068 + Scribe $0.0042 external) | 8 PASS / 1 FAIL / 4 UNCERTAIN. Scribe broke the year tie (heard "1995", Meta heard "1999"). The 1 FAIL (dlg-c01-s04b, missing first word "hội") corroborated by two independent ASRs + word timestamps |
| 2026-10-31 | run-842bad0dbd8f41c5817f | EP01 V4 master | video-only (auto-contract rev 2) | BLOCK | $2.91 | Post-scope-fix regression: 17 PASS / 11 FAIL / 2 UNCERTAIN / 0 ERROR; 24 confirmed findings (5 gen-artifacts + 19 continuity), 17 rejected, 14 for review. Cost −75% vs the $11.81 baseline; duplication reduced to 2 boundary-pair defects reported in two adjacent chunks each |
| 2026-10-31 | run-cf6495aab4a6471db1a0 | C01 workprint REBUILT (S04B trim fixed), 13 lines | dialogue (Meta + Scribe) | REVIEW | $0.0110 total (Meta $0.0068 + Scribe $0.0042 external) | 10 PASS / 0 FAIL / 3 UNCERTAIN — first dialogue run with zero FAILs. dlg-c01-s04b PASS confirms the production fix; the catch→fix→re-verify loop closed |

Budget after the last run: Meta settled ≈ $27.78 of the $140 cap, reserved $0.

## Improvements, and the evidence that forced each one

- **Scratch cleanup (run lifecycle)** — run-009b's 20 ERRORs and run-76f4's death traced to run scratch (/tmp) never being deleted; the 2 GB worker tmpfs filled up. Fix: every run removes its own scratch in a finally block.
- **Budget caps raised to $140 project / $15 run** — the original $10/$2 caps made full-episode runs impossible; the author's credit policy (use-it-or-lose-it, card being removed) set the $140 ceiling instead.
- **Scoped continuity audits** — run-7e1d's continuity checks ignored their chunk scope and re-audited the whole film per chunk (same defect reported ~6×, ~6× cost). Fix: shots filtered to scope + one neighbour per side. Measured effect: run-842b cost $2.91 vs $11.81 baseline.
- **Decoded-QC tolerance = half a frame** — clean concat/re-encode files ERRORed on a fixed 1 ms contiguity bound. One full frame was too loose (a pre-existing audio-QC test caught a whole-frame hole passing); half a median frame duration is the shipped bound. Sub-frame seam jitter passes; real holes still fail closed.
- **Dialogue verification (P0-2)** — new observation kind: blind double-pass ASR (Muse Voice Transcribe) vs locked script lines, token-level diffs, duplicate-line detection, unintelligible-line flags.
- **Dialogue comparator folding** — case and punctuation are folded before comparison (a word-exact line FAILed over a final period).
- **EDL → dialogue contract compiler** (`scripts/compile_edl_contract.py`) — a workprint's edit decision list compiles deterministically into a dialogue contract; reproduced the hand-built C01 contract's 13 assertions and scopes exactly.
- **ElevenLabs Scribe as independent second ASR + provider-level voting + Vietnamese number canonicalization** — run-272d produced 7 false alarms out of 13 lines because both passes were the same model (correlated errors) and number renderings differed (spelled-out vs digits). Now: Meta's two passes count as one provider vote; FAIL requires two independent providers agreeing on the same differing reading; spelled-out Vietnamese numbers (digit-by-digit years, positional numbers, clock times) canonicalize to digits before comparison. Scribe also supplies word-level timestamps and, on this Vietnamese dialogue, proved the more stable transcriber — stated plainly: it handles Vietnamese better, which is why it is in the loop.
- **Residual duplication note** — boundary shot pairs are evaluated by both adjacent chunks (+1 neighbour rule), so a defect sitting exactly on a chunk boundary is reported twice (2 cases in run-842b). A pair-identity dedupe at merge time is the queued fix.

## Process rules that came out of these runs

- A stills-based or single-model pass is never "done": verdicts require motion/audio evidence or two independent observers.
- Operational ERRORs (disk, expired remote files) are reported separately from content defects, always.
- Every run is logged here with its cost before the next run starts.
