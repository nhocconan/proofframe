"""Case-contract declared elements: the suppression context for the blind audits.

A case (contract-mode) run carries an approved brief: assertions that name the
story's canonical elements (the hero prop and its attachments, a character's
watch, the notebook...). The blind audits (continuity, artifact scan) deliberately
never see the brief while observing. But when an audit CONFIRMS a defect on an
element the brief itself declares, the brief's own assertions are the qualified
judge of that element - the audit finding is downgraded to human review, never
deleted and never hidden: the finding keeps its evidence and records which
assertion declared the element. In video-only runs the auto-contract declares no
content elements, so nothing is downgraded there.

Matching is deterministic token overlap between the finding's entity (or, for
artifact-scan findings, its description) and an element's subject/attribute/
assertion-id tokens: at least two shared content tokens, at least one of them
from the assertion id (the curated names carry the head nouns: note, box,
watch, strap, knob...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EXCLUDED_KINDS = {"cross_shot_continuity", "generation_artifact_scan", "technical", "dialogue"}
_STOPWORDS = {"the", "a", "an", "of", "on", "in", "at", "to", "and", "or", "is", "are", "was", "were",
              "that", "this", "it", "its", "any", "every", "other", "seen", "shown", "clearly", "visible",
              "whether", "which", "how", "many", "much", "when", "while", "during", "before", "after",
              "into", "onto", "with", "without", "from", "by", "for", "as", "one", "two", "same"}
_SYNONYMS = {"aluminium": "aluminum", "colour": "color", "boombox": "radio"}


def tokens(text: str) -> set[str]:
    out = set()
    for tok in re.findall(r"[a-z0-9]+", text.lower().replace("'", " ")):
        if len(tok) < 3 or tok in _STOPWORDS:
            continue
        out.add(_SYNONYMS.get(tok, tok))
    return out


@dataclass(frozen=True)
class DeclaredElement:
    assertion_id: str
    tokens: frozenset[str]
    id_tokens: frozenset[str]


def from_contract(contract) -> list[DeclaredElement]:
    """Declared content elements of a case contract (audit/technical/dialogue assertions excluded)."""
    out = []
    for a in contract.assertions:
        o = a.observation
        if o is None or o.kind in _EXCLUDED_KINDS:
            continue
        id_tokens = tokens(a.assertion_id.replace("-", " "))
        toks = tokens(o.subject or "") | tokens(o.attribute or "") | id_tokens
        out.append(DeclaredElement(a.assertion_id, frozenset(toks), frozenset(id_tokens)))
    return out


def match(text: str, elements: list[DeclaredElement]) -> str | None:
    """Return the declaring assertion_id when `text` names a declared element, else None."""
    tt = tokens(text)
    best: tuple[str, int] | None = None
    for el in elements:
        shared = tt & el.tokens
        if len(shared) >= 2 and shared & el.id_tokens:
            if best is None or len(shared) > best[1]:
                best = (el.assertion_id, len(shared))
    return best[0] if best else None
