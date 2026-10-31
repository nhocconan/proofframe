"""Deterministic dialogue comparison. ASR observes blind audio; approved text stays here."""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .compare import normalize_text

_DIGITS = {"không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4,
           "năm": 5, "lăm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9}
_NUMBER_WORDS = set(_DIGITS) | {"mười", "mươi", "trăm", "lẻ", "linh", "mốt"}


def _plain_tokens(value: str) -> list[str]:
    folded = normalize_text(value).casefold()
    return "".join(ch for ch in folded if not unicodedata.category(ch).startswith("P")).split()


def _is_year_noun(words: list[str], index: int, output: list[str]) -> bool:
    """Keep ``năm`` as "year" after ``hồi`` or a ``tháng <number>`` phrase.

    Elsewhere it is numeric in a number run or immediately before ``giờ``. This
    deliberately narrow heuristic handles locked-script dates and times without
    pretending to perform general Vietnamese semantic parsing.
    """
    if words[index] != "năm":
        return False
    if index and words[index - 1] == "hồi":
        return True
    return index >= 2 and words[index - 2] == "tháng" and words[index - 1] in _NUMBER_WORDS


def _positional_number(words: list[str]) -> int | None:
    """Parse one conservative Vietnamese number expression from 0 through 999."""
    if not words:
        return None
    if len(words) == 1:
        return 10 if words[0] == "mười" else _DIGITS.get(words[0])
    total = 0
    pos = 0
    if "trăm" in words:
        if len(words) < 2 or words[0] not in _DIGITS or words[1] != "trăm":
            return None
        total, pos = _DIGITS[words[0]] * 100, 2
        if pos < len(words) and words[pos] in {"lẻ", "linh"}:
            pos += 1
            if pos == len(words):
                return None
    rest = words[pos:]
    if not rest:
        return total
    if rest[0] == "mười":
        tens, rest = 10, rest[1:]
    elif len(rest) >= 2 and rest[0] in _DIGITS and rest[1] == "mươi":
        tens, rest = _DIGITS[rest[0]] * 10, rest[2:]
    elif total and len(rest) == 1 and rest[0] in _DIGITS:
        return total + _DIGITS[rest[0]]
    else:
        return None
    if not rest:
        return total + tens
    if len(rest) != 1:
        return None
    unit = {"mốt": 1, "lăm": 5, "tư": 4}.get(rest[0], _DIGITS.get(rest[0]))
    return None if unit is None else total + tens + unit


def canonicalize_numbers(value: str) -> list[str]:
    """Return comparison tokens with conservative Vietnamese number normalization."""
    words = _plain_tokens(value)
    output: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        if word.isdigit():
            output.append(str(int(word)))
            i += 1
            continue
        if word not in _NUMBER_WORDS or _is_year_noun(words, i, output):
            output.append(word)
            i += 1
            continue
        end = i
        while end < len(words) and words[end] in _NUMBER_WORDS and not _is_year_noun(words, end, output):
            end += 1
        run = words[i:end]
        if len(run) >= 2 and all(part in _DIGITS for part in run):
            output.append("".join(str(_DIGITS[part]) for part in run))
            i = end
            continue
        number = _positional_number(run)
        if number is not None:
            output.append(str(number))
            i = end
            continue
        matched = False
        for stop in range(end - 1, i, -1):
            number = _positional_number(words[i:stop])
            if number is not None:
                output.append(str(number))
                i = stop
                matched = True
                break
        if not matched:
            output.append(word)
            i += 1
    return output


def tokens(value: str) -> list[str]:
    return canonicalize_numbers(value)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=tokens(a), b=tokens(b), autojunk=False).ratio()


def token_diff(expected: str, heard: str) -> str:
    exp, got = tokens(expected), tokens(heard)
    parts: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=exp, b=got, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        left, right = " ".join(exp[i1:i2]) or "∅", " ".join(got[j1:j2]) or "∅"
        parts.append(f"expected [{left}] → heard [{right}]")
    return "; ".join(parts) or "no token differences"


@dataclass(frozen=True)
class DialogueVerdict:
    status: str
    rationale: str


def decide_provider_transcripts(expected: str, transcripts: list[tuple[str, str]], *,
                                independent_provider_enabled: bool = True,
                                provider_errors: list[tuple[str, str]] | None = None) -> DialogueVerdict:
    """Adjudicate provider votes without treating two modes of one ASR as independent."""
    expected_tokens = tuple(tokens(expected))
    grouped: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    descriptions: list[str] = []
    for provider, transcript in transcripts:
        canonical = tuple(tokens(transcript))
        grouped[provider].append(canonical)
        descriptions.append(f"{provider}={transcript!r} (canonical={' '.join(canonical)!r})")

    votes: dict[str, tuple[str, tuple[str, ...] | None]] = {}
    for provider, readings in grouped.items():
        if any(not reading for reading in readings):
            votes[provider] = ("SPLIT", None)
        elif all(reading == expected_tokens for reading in readings):
            votes[provider] = ("MATCH", expected_tokens)
        elif len(set(readings)) == 1:
            votes[provider] = ("DIFFER", readings[0])
        else:
            votes[provider] = ("SPLIT", None)

    matches = [provider for provider, (vote, _) in votes.items() if vote == "MATCH"]
    differs = [(provider, reading) for provider, (vote, reading) in votes.items() if vote == "DIFFER"]
    errors = provider_errors or []
    detail = "; ".join(descriptions + [f"{p}=ERROR({e})" for p, e in errors]) or "no usable transcripts"
    if matches and not differs and not errors:
        return DialogueVerdict("PASS", f"Provider vote MATCH ({', '.join(matches)}). Evidence: {detail}.")
    if not matches and not errors:
        by_reading: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for provider, reading in differs:
            assert reading is not None
            by_reading[reading].append(provider)
        if independent_provider_enabled:
            agreed = next(((reading, providers) for reading, providers in by_reading.items()
                           if len(set(providers)) >= 2), None)
        else:
            meta = grouped.get("meta", [])
            agreed = ((meta[0], ["meta", "meta"]) if len(meta) >= 2 and meta[0] and len(set(meta)) == 1
                      and meta[0] != expected_tokens else None)
        if agreed:
            return DialogueVerdict(
                "FAIL", f"Providers agree on differing dialogue: {token_diff(expected, ' '.join(agreed[0]))}. "
                f"Evidence: {detail}.")
    return DialogueVerdict(
        "UNCERTAIN",
        f"Possibly unintelligible or contested: two blind transcriptions disagree, evidence is split, "
        f"missing, or errored. Evidence: {detail}.")


def decide(expected: str, first: str, second: str | None) -> DialogueVerdict:
    """Compatibility entry point for the legacy Meta-only double-transcription path."""
    items = [("meta", first)] + ([("meta", second)] if second is not None else [])
    return decide_provider_transcripts(expected, items, independent_provider_enabled=False)
