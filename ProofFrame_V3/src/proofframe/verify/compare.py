"""Deterministic comparison of neutral observations with approved values. No model calls."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

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


def technical(metric: str, expected: str, tolerance: int, probe: dict) -> tuple[str, str, str]:
    """Returns (status, observed, rationale) for an ffprobe-based check."""
    actual = probe.get(metric)
    if actual is None:
        return "ERROR", "null", f"ffprobe did not report {metric}"
    if metric == "has_audio":
        ok = str(bool(actual)).lower() == expected.strip().lower()
        return ("PASS" if ok else "FAIL"), str(bool(actual)).lower(), f"ffprobe audio stream present={actual}"
    ok = abs(int(actual) - int(expected)) <= tolerance
    return ("PASS" if ok else "FAIL"), str(actual), f"ffprobe {metric}={actual}, expected {expected}±{tolerance}"


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
