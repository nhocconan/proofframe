"""Deterministic comparison of neutral observations with approved values. No model calls."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

# Typographic variants a reader cannot distinguish reliably; letters/diacritics/case stay exact.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
CANNOT_DETERMINE = "cannot_determine"


def normalize_text(value: str) -> str:
    v = unicodedata.normalize("NFC", value).translate(_DASHES).translate(_QUOTES)
    v = re.sub(r"\s*-\s*", " - ", v)
    return re.sub(r"\s+", " ", v).strip()


@dataclass(frozen=True)
class FrameReading:
    label: str
    evidence_id: str
    t_ms: int
    subject_visible: bool
    visibility: str  # clear | partial | not_visible
    value: str


@dataclass(frozen=True)
class Verdict:
    status: str
    observed: str | None
    evidence_ids: tuple[str, ...]
    rationale: str


def decide(comparator: str, expected: str, frames: list[FrameReading], *, min_items: int,
           localized_values: list[str], temporal: str = "throughout") -> Verdict:
    """PASS needs >= min_items clear matching frames and no clear contradiction.
    FAIL needs a consistent clear contradiction on >= 2 frames (or 1 frame + agreeing video pass),
    with no clear matching frame. Everything else is UNCERTAIN — never PASS by default."""
    norm = normalize_text if comparator == "exact_text_nfc" else (lambda s: s.strip().lower())
    exp = norm(expected)
    clear = [f for f in frames if f.subject_visible and f.visibility == "clear"
             and f.value and f.value != CANNOT_DETERMINE]
    match = [f for f in clear if norm(f.value) == exp]
    miss = [f for f in clear if norm(f.value) != exp]
    loc = [norm(v) for v in localized_values if v and v != CANNOT_DETERMINE]
    observed_values = sorted({f.value for f in clear})
    observed = " | ".join(observed_values) if observed_values else None
    summary = (f"{len(frames)} frames inspected; {len(clear)} clear readings; {len(match)} match, "
               f"{len(miss)} differ; video-pass values: {sorted(set(localized_values)) or 'none'}.")
    if temporal == "occurs":
        if len(match) >= min_items:
            return Verdict("PASS", observed, tuple(f.evidence_id for f in match),
                           summary + " Event/state observed in clear frames (other frames may precede/follow it).")
        return Verdict("UNCERTAIN", observed, tuple(f.evidence_id for f in match + miss),
                       summary + " Event/state not observed in enough sampled frames; sampled evidence cannot prove"
                       " it never occurs (could fall between samples).")
    if match and not miss:
        if len(match) >= min_items:
            note = "" if (not loc or exp in loc) else " Video pass reported a different value; frame evidence governs."
            return Verdict("PASS", observed, tuple(f.evidence_id for f in match), summary + note)
        return Verdict("UNCERTAIN", observed, tuple(f.evidence_id for f in match),
                       summary + f" Fewer than the required {min_items} matching items.")
    if miss and not match:
        wrong = {norm(f.value) for f in miss}
        consistent = len(wrong) == 1
        corroborated = bool(set(loc) & wrong)
        if consistent and (len(miss) >= 2 or corroborated):
            return Verdict("FAIL", observed, tuple(f.evidence_id for f in miss),
                           summary + " Consistent clear contradiction of the approved value.")
        return Verdict("UNCERTAIN", observed, tuple(f.evidence_id for f in miss),
                       summary + " Contradiction not consistent/corroborated enough to FAIL.")
    if match and miss:
        return Verdict("UNCERTAIN", observed, tuple(f.evidence_id for f in match + miss),
                       summary + " Frames disagree (possible change mid-scope or misreading); needs review.")
    partial = [f for f in frames if f.subject_visible and f.visibility == "partial"]
    seen = [f for f in frames if f.subject_visible]
    why = ("attribute only partially visible / value not determinable" if partial
           else "subject visible but the attribute could not be read in any sampled frame" if seen
           else "subject not visible in sampled frames (absence from samples is not proof of absence)")
    return Verdict("UNCERTAIN", observed, tuple(f.evidence_id for f in partial), summary + f" {why}.")


COVERAGE_STEP_MS = 250
COVERAGE_MIN_FRAMES = 4
COVERAGE_MAX_FRAMES = 16


def coverage_grid(lo: int, hi: int) -> list[int]:
    """Uniform frame times for a coverage check: one frame at the centre of each of N equal sub-intervals
    (N = span / 250 ms, clamped to 4..16). Model-suggested times are NOT used, so the fraction is unbiased."""
    n = min(COVERAGE_MAX_FRAMES, max(COVERAGE_MIN_FRAMES, (hi - lo) // COVERAGE_STEP_MS))
    return [int(lo + (hi - lo) * (i + 0.5) / n) for i in range(n)]


@dataclass(frozen=True)
class Coverage:
    sampled: int          # frames in the uniform grid (denominator)
    matched: int          # clear frames reading exactly the approved value
    absent: int           # frames where the observer reports no such subject/text
    unreadable: int       # partial / cannot-determine frames (could be either way)
    contradicted: int     # clear frames reading a different value
    fraction_low: float   # matched / sampled
    fraction_high: float  # (matched + unreadable + contradicted) / sampled: every doubtful frame a misread
    first_match_ms: int | None
    last_match_ms: int | None
    missing_ms: tuple[int, ...]  # frame times with the value clearly absent or different

    def as_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


def decide_coverage(comparator: str, expected: str, frames: list[FrameReading], *, sampled: int,
                    min_coverage: float, localized_values: list[str]) -> tuple[Verdict, Coverage]:
    """The approved value must be visible in >= min_coverage of a uniform frame grid over the scope.

    PASS: matched/sampled >= min_coverage and no clear contradiction.
    FAIL: the value is demonstrably shown (>= 1 clear match, so the observer can read it), yet even counting every
          unreadable or differently-read frame as a misread match the fraction stays below min_coverage, with >= 2
          frames where the observer reports no such text/subject at all;
          or the existing exact-value FAIL rule (consistent clear contradiction, no match) holds.
    Everything else UNCERTAIN. Frames the model did not return count as unreadable, never as matches.
    This is a fraction of SAMPLED frames, not of decoded frames; events shorter than the grid step can be missed.
    """
    norm = normalize_text if comparator == "exact_text_nfc" else (lambda s: s.strip().lower())
    exp = norm(expected)
    match, absent, unreadable, wrong = [], [], [], []
    for f in frames:
        value = (f.value or "").strip()
        if f.subject_visible and f.visibility == "clear" and value and value != CANNOT_DETERMINE:
            (match if norm(value) == exp else wrong).append(f)
        elif (not f.subject_visible) or (f.visibility == "clear" and not value):
            absent.append(f)
        else:
            unreadable.append(f)
    unreadable_n = len(unreadable) + max(0, sampled - len(frames))
    cov = Coverage(sampled=sampled, matched=len(match), absent=len(absent), unreadable=unreadable_n,
                   contradicted=len(wrong), fraction_low=len(match) / sampled,
                   fraction_high=(len(match) + unreadable_n + len(wrong)) / sampled,
                   first_match_ms=min((f.t_ms for f in match), default=None),
                   last_match_ms=max((f.t_ms for f in match), default=None),
                   missing_ms=tuple(sorted(f.t_ms for f in absent + wrong)))
    ids = tuple(f.evidence_id for f in match + absent + wrong)
    observed_values = sorted({f.value for f in match + wrong})
    observed = " | ".join(observed_values) if observed_values else None
    summary = (f"coverage {len(match)}/{sampled} sampled frames ({cov.fraction_low:.0%}, at most "
               f"{cov.fraction_high:.0%} if every unreadable or differing frame were a misread); required "
               f"{min_coverage:.0%}; "
               f"{len(absent)} without it, {len(wrong)} with a different value, {unreadable_n} unreadable.")
    if match and not wrong and cov.fraction_low >= min_coverage:
        return Verdict("PASS", observed, ids, summary), cov
    if not match:
        base = decide(comparator, expected, frames, min_items=1, localized_values=localized_values)
        if base.status == "FAIL":
            return Verdict("FAIL", base.observed, base.evidence_ids, summary + " " + base.rationale), cov
        return Verdict("UNCERTAIN", observed, ids,
                       summary + " Approved value not read in any sampled frame; absence from samples is not "
                       "proof that it is never shown."), cov
    if cov.fraction_high < min_coverage and len(absent) >= 2:
        where = ", ".join(f"{t / 1000:.2f}s" for t in sorted(f.t_ms for f in absent)[:8])
        return Verdict("FAIL", observed, ids,
                       summary + f" Shown for too little of its window; missing at {where}."), cov
    return Verdict("UNCERTAIN", observed, ids, summary + " Coverage cannot be established either way."), cov


def numeric_status(actual: int | float, expected: str, tolerance: int | float,
                   relation: str = "equals", resolution: float = 0) -> str:
    """Compare a measurement interval against an approved numeric requirement."""
    try:
        value, target, margin, step = map(Decimal, map(str, (actual, expected, tolerance, resolution)))
    except InvalidOperation as exc:
        raise ValueError("technical values must be finite numbers") from exc
    if not all(n.is_finite() for n in (value, target, margin, step)) or margin < 0 or step < 0:
        raise ValueError("technical values must be finite; tolerance/resolution must be nonnegative")
    if any(abs(n.as_tuple().exponent) > 1000 or len(n.as_tuple().digits) > 1000
           for n in (value, target, margin, step)):
        raise ValueError("technical numeric precision exceeds supported bounds")
    value, target, margin, step = map(Fraction, (value, target, margin, step))
    lo, hi = value - step / 2, value + step / 2
    lower, upper = target - margin, target + margin
    if relation == "at_most":
        return "PASS" if hi <= upper else "FAIL" if lo > upper else "UNCERTAIN"
    if relation == "at_least":
        return "PASS" if lo >= lower else "FAIL" if hi < lower else "UNCERTAIN"
    if relation != "equals":
        raise ValueError("unknown technical relation")
    return "PASS" if lo >= lower and hi <= upper else "FAIL" if hi < lower or lo > upper else "UNCERTAIN"


def technical(metric: str, expected: str, tolerance: int | float, probe: dict,
              relation: str = "equals") -> tuple[str, str, str]:
    """Returns (status, observed, rationale) for an ffprobe-based check."""
    actual = probe.get(metric)
    if actual is None:
        return "ERROR", "null", f"ffprobe did not report {metric}"
    if metric == "has_audio":
        ok = str(bool(actual)).lower() == expected.strip().lower()
        return ("PASS" if ok else "FAIL"), str(bool(actual)).lower(), f"ffprobe audio stream present={actual}"
    status = numeric_status(actual, expected, tolerance, relation)
    return status, str(actual), f"ffprobe {metric}={actual}, {relation} {expected}±{tolerance}"


REGRESSION_CLASSES = ("FIXED", "STILL_FAILING", "REGRESSION", "UNCERTAIN", "NOT_COMPARABLE", "UNCHANGED_PASS")


def classify(before: str | None, after: str) -> str:
    if before is None:
        return "NOT_COMPARABLE"
    if after in ("UNCERTAIN", "NOT_CHECKED", "ERROR"):
        return "UNCERTAIN"
    if before == "PASS":
        return "UNCHANGED_PASS" if after == "PASS" else "REGRESSION"
    if before in ("FAIL", "UNCERTAIN", "NOT_CHECKED", "ERROR"):
        if after == "PASS":
            return "FIXED" if before == "FAIL" else "NOT_COMPARABLE"
        return "STILL_FAILING" if before == "FAIL" else "NOT_COMPARABLE"
    return "NOT_COMPARABLE"
