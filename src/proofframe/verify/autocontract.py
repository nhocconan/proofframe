"""Deterministic, content-agnostic contracts for scans without an approved brief."""
from __future__ import annotations

from typing import Any

from proofframe_contracts.models import Contract


# Cross-shot continuity has nothing to compare inside one continuous shot. Approved up front so the policy
# excludes it instead of turning every single-shot clip into REVIEW; within-shot changes stay with gen-artifacts.
SINGLE_SHOT_EXCLUSION = ("not applicable when FFmpeg hard-cut detection finds one continuous shot: no cross-shot "
                         "pairs exist (dissolves can be missed; within-shot changes are the artifact scan's job)")


def build_auto_contract(asset_id: str, probe: dict[str, Any], tenant: str,
                        reference: dict[str, str] | None = None) -> dict[str, Any]:
    """Build a video-only scan contract bound to an already-ingested media hash.

    `reference` ({"asset_id", "sha256"}) is an optional still the clip was generated from (image-to-video).
    It adds one hash-bound `canonical_reference` slot and the `reference-match` check; without it that check
    does not exist (no reference, no reference claim).

    The expected values below are detector limits, not claims about the video's
    intended content. Visual checks deliberately assert only generic anomaly audits.
    """
    media_sha256 = str(probe["sha256"])
    if len(media_sha256) != 64:
        raise ValueError("probe needs the ingested asset sha256")
    duration_ms = probe.get("duration_ms")
    identity = media_sha256[:12]
    if reference is not None:
        if len(str(reference.get("sha256", ""))) != 64 or not reference.get("asset_id"):
            raise ValueError("reference needs asset_id and the ingested sha256")
        if reference["asset_id"] == asset_id:
            raise ValueError("reference asset_id must differ from the video asset_id")
        identity = f"{identity}-ref{str(reference['sha256'])[:12]}"
    scopes: list[tuple[int, int] | None] = [None]
    if isinstance(duration_ms, int) and duration_ms > 180_000:
        scopes = [(start, min(start + 90_000, duration_ms))
                  for start in range(0, duration_ms, 90_000)]

    assertions: list[dict[str, Any]] = []
    audits = (
        ("gen-artifacts", "/profile/film/no_generation_artifacts",
         "no confirmed major generation defects (anatomy, objects, text, physics, within-shot continuity)",
         "no confirmed major defects", "generation_artifact_scan", "the whole video",
         "visual generation defects", "anomaly_scan"),
        ("continuity", "/profile/film/cross_shot_continuity",
         "no confirmed cross-shot continuity errors (props, wardrobe, set, presence, holders)",
         "no confirmed major errors", "cross_shot_continuity", "the whole film",
         "cross-shot continuity", "continuity_audit"),
    )
    for base_id, pointer, predicate, expected, kind, subject, attribute, comparator in audits:
        for index, scope in enumerate(scopes, 1):
            row: dict[str, Any] = {
                "assertion_id": base_id if scope is None else f"{base_id}-{index:02d}",
                "source_pointer": pointer,
                "target_asset_id": asset_id,
                "predicate": predicate,
                "expected": expected,
                "blocking": True,
                "stage": "assembly",
                "global_sentinel": True,
                "coverage": {"kind": "sampled", "minimum_items": 1},
                "observation": {"kind": kind, "subject": subject, "attribute": attribute,
                                "comparator": comparator},
            }
            if scope is not None:
                row["scope"] = {"start_ms": scope[0], "end_ms": scope[1]}
            if kind == "cross_shot_continuity":
                row["approved_exclusion"] = SINGLE_SHOT_EXCLUSION
            assertions.append(row)

    if reference is not None:
        assertions.append({
            "assertion_id": "reference-match",
            "source_pointer": "/video_only/reference_match",
            "target_asset_id": asset_id,
            "reference_asset_ids": [reference["asset_id"]],
            "predicate": "clip frames show the same props and setting as the supplied reference still",
            "expected": "no props added or missing and no setting change beyond camera framing",
            "blocking": True,
            "stage": "assembly",
            "global_sentinel": True,
            "coverage": {"kind": "sampled", "minimum_items": 1},
            "observation": {"kind": "reference_match", "subject": "clip frames compared with the reference still",
                            "attribute": "props and setting versus the reference", "comparator": "reference_match"},
        })

    qc = (
        ("qc-black", "black_duration_ms", "3000", "at_most", "black intervals"),
        ("qc-freeze", "freeze_duration_ms", "10000", "at_most", "frozen intervals"),
    )
    # Audio QC needs an audio stream: without one the detectors can only ERROR ("audio stream required").
    # A missing track is not a defect this advisory can measure, so those assertions are not created
    # (absent audio is surfaced by the probe metadata, never as a PASS).
    if probe.get("has_audio"):
        qc += (
            ("qc-silence", "silence_duration_ms", "30000", "at_most", "silent intervals"),
            ("qc-loudness", "integrated_loudness_lufs", "-30", "at_least", "integrated loudness"),
            ("qc-true-peak", "true_peak_dbtp", "0", "at_most", "true peak"),
        )
    # Decoded-QC detectors cap one scope at 300 s (see verify/technical.py and
    # verify/audio.py): on longer media a whole-video scope would ERROR instead
    # of measuring. Reuse the 90 s audit chunks for the advisories so long
    # media is actually measured; thresholds stay generous per chunk, and
    # loudness/true-peak become per-chunk advisory floors, never a
    # whole-programme compliance claim.
    qc_scopes: list[tuple[int, int] | None] = [None]
    if isinstance(duration_ms, int) and duration_ms > 300_000:
        qc_scopes = scopes
    for assertion_id, metric, expected, relation, attribute in qc:
        for index, scope in enumerate(qc_scopes, 1):
            row = {
                "assertion_id": assertion_id if scope is None else f"{assertion_id}-{index:02d}",
                "source_pointer": f"/video_only/advisory/{metric}",
                "target_asset_id": asset_id,
                "predicate": f"advisory decoded QC: {attribute}",
                "expected": expected,
                "blocking": False,
                "stage": "assembly",
                "global_sentinel": True,
                "coverage": {"kind": "artifact", "minimum_items": 1},
                "observation": {"kind": "technical", "subject": "delivery", "attribute": attribute,
                                "comparator": "technical", "technical_metric": metric,
                                "technical_relation": relation},
            }
            if scope is not None:
                row["scope"] = {"start_ms": scope[0], "end_ms": scope[1]}
            assertions.append(row)

    contract = Contract.model_validate({
        "contract_id": f"auto-{identity}",
        "revision": 1,
        "tenant_id": tenant,
        "profile": "film",
        "profile_revision": "video-only-no-brief-v1",
        "assets": [{"asset_id": asset_id, "media_type": "video"}] + (
            [] if reference is None else [{"asset_id": reference["asset_id"], "media_type": "image",
                                           "role": "canonical_reference",
                                           "canonical_sha256": str(reference["sha256"])}]),
        "assertions": assertions,
    })
    return contract.model_dump(mode="json")
