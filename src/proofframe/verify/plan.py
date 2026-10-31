"""Pre-run cost plan: estimate a run from free FFmpeg facts, shrink the audits to fit the remaining budget.

Without this, the audits that run last (continuity) found an empty budget on long films, spent money on
earlier stages and reported nothing. The plan is computed before any paid call; every reduction is recorded
and surfaced as a limitation of the affected check. Costs are per-call averages measured on live runs
(evaluator 0.12, muse-spark-1.3, owner clip; BUILD_STATUS.md) plus 10 % margin; adjudication is counted at its
cap, so short clips are over-estimated (60 s: est. ≈ $0.88 vs $0.64 measured). An estimate, not a quote.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import anomaly, continuity

COST = {  # USD per call, measured averages (run-ee24dd80868649a4b3b1)
    "localize_minute": 0.006,  # declared assertion: 1 fps localization pass, per started minute
    "confirm": 0.008,          # declared assertion: frame confirmation
    "hunt_minute": 0.030,      # artifact scan: 2 fps 854 px video hunt, per started minute
    "grid": 0.011,             # one batch of 10 frames
    "scan_adjudicate": 0.012,
    "continuity_log": 0.033,
    "continuity_pair": 0.011,
    "continuity_adjudicate": 0.012,
    "asr_minute": 0.0024,
}
MARGIN = 1.10
CONFIRM_FRAMES = 6  # frames behind the measured "confirm" average (pipeline.MAX_FRAMES)
# Reductions in order of least detection value lost (registry pairs and caps first, adjacent pairs never).
STEPS = [
    ("max_registry_pairs", 6, "long-range registry pairs 12 → 6"),
    ("max_suspicions", 16, "cross-shot adjudications capped 24 → 16"),
    ("grid_step_ms", 3000, "artifact-scan frame grid every 2 s → 3 s"),
    ("max_registry_pairs", 0, "long-range registry pairs dropped (adjacent and insert pairs kept)"),
    ("max_suspicions", 10, "cross-shot adjudications capped 16 → 10"),
    ("grid_step_ms", 4000, "artifact-scan frame grid every 3 s → 4 s"),
    ("max_candidates", 4, "artifact-scan adjudications capped 6 → 4"),
]
SCAN_KNOBS = {"grid_step_ms", "max_candidates"}


@dataclass
class RunPlan:
    grid_step_ms: int = anomaly.GRID_STEP_MS
    max_candidates: int = anomaly.MAX_CANDIDATES
    max_registry_pairs: int = continuity.MAX_REGISTRY_PAIRS
    max_suspicions: int = continuity.MAX_SUSPICIONS
    full_estimate_usd: float = 0.0
    estimate_usd: float = 0.0
    budget_usd: float | None = None
    reductions: list[str] = field(default_factory=list)
    fits: bool = True

    def as_dict(self) -> dict:
        d = asdict(self)
        d["full_estimate_usd"] = round(d["full_estimate_usd"], 3)
        d["estimate_usd"] = round(d["estimate_usd"], 3)
        d["basis"] = ("visual per-call averages from live runs plus probe-measured ASR duration rate, "
                      "+ 10 % margin; adjudication counted at its cap")
        return d

    def limits(self, stage: str) -> list[str]:
        """Reductions affecting one stage ('scan' | 'continuity'), as one check limitation."""
        mine = [r for r in self.reductions if r.startswith("artifact-scan") == (stage == "scan")]
        if not mine:
            return []
        return [f"budget plan (est. ${self.full_estimate_usd:.2f} full vs ${self.budget_usd:.2f} available): "
                + "; ".join(mine)]


@dataclass
class Workload:
    """Free facts about the selected checks (no paid call needed to compute them)."""
    assertion_minutes: list[int] = field(default_factory=list)  # one entry per visual assertion
    scan_spans_ms: list[int] = field(default_factory=list)       # one entry per artifact scan
    continuity_shots: list[list[tuple[int, int]]] = field(default_factory=list)  # one entry per audit
    asr_minutes: list[int] = field(default_factory=list)  # one entry per transcription pass
    coverage_frames: list[int] = field(default_factory=list)  # grid size of each min_coverage assertion


def _minutes(span_ms: int) -> int:
    return max(1, -(-span_ms // 60_000))


def estimate(w: Workload, p: RunPlan) -> float:
    c = COST
    total = sum(m * c["localize_minute"] + c["confirm"] for m in w.assertion_minutes)
    total += sum(m * c["asr_minute"] for m in w.asr_minutes)
    # a coverage grid confirms up to 16 frames instead of ~6: scale the confirmation by frame count
    total += sum(max(0, n - CONFIRM_FRAMES) / CONFIRM_FRAMES * c["confirm"] for n in w.coverage_frames)
    for span in w.scan_spans_ms:
        grid = max(1, span // p.grid_step_ms)
        total += _minutes(span) * c["hunt_minute"] + -(-grid // anomaly.GRID_BATCH) * c["grid"]
        total += p.max_candidates * c["scan_adjudicate"]
    for shots in w.continuity_shots:
        n = len(shots)
        keys = continuity.plan_keyframes(shots)
        inserts = sum(1 for i in range(1, n - 1) if shots[i][1] - shots[i][0] <= continuity.INSERT_MAX_MS)
        total += len(continuity.batches(keys)) * c["continuity_log"]
        total += (max(0, n - 1) + inserts + p.max_registry_pairs) * c["continuity_pair"]
        total += p.max_suspicions * c["continuity_adjudicate"]
    return total * MARGIN


def fit(w: Workload, budget_usd: float | None) -> RunPlan:
    """Full plan when it fits (or when the remaining budget is unknown); otherwise apply STEPS in order."""
    p = RunPlan(budget_usd=None if budget_usd is None else round(budget_usd, 4))
    p.full_estimate_usd = p.estimate_usd = estimate(w, p)
    if budget_usd is None:
        return p
    for attr, value, why in STEPS:
        if p.estimate_usd <= budget_usd:
            break
        stage_present = w.scan_spans_ms if attr in SCAN_KNOBS else w.continuity_shots
        if not stage_present or getattr(p, attr) == value:
            continue
        setattr(p, attr, value)
        p.reductions.append(why)
        p.estimate_usd = estimate(w, p)
    p.fits = p.estimate_usd <= budget_usd
    return p
