"""Deterministic, content-agnostic contracts for scans without an approved brief."""
from __future__ import annotations

from typing import Any

from proofframe_contracts.models import Contract


def build_auto_contract(asset_id: str, probe: dict[str, Any], tenant: str) -> dict[str, Any]:
    """Build a video-only scan contract bound to an already-ingested media hash.

    The expected values below are detector limits, not claims about the video's
    intended content. Visual checks deliberately assert only generic anomaly audits.
    """
    media_sha256 = str(probe["sha256"])
    if len(media_sha256) != 64:
        raise ValueError("probe needs the ingested asset sha256")
    duration_ms = probe.get("duration_ms")
    identity = media_sha256[:12]
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
            assertions.append(row)

    qc = (
        ("qc-black", "black_duration_ms", "3000", "at_most", "black intervals"),
        ("qc-freeze", "freeze_duration_ms", "10000", "at_most", "frozen intervals"),
        ("qc-silence", "silence_duration_ms", "30000", "at_most", "silent intervals"),
    )
    if probe.get("has_audio"):
        qc += (
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
        "assets": [{"asset_id": asset_id, "media_type": "video"}],
        "assertions": assertions,
    })
    return contract.model_dump(mode="json")
