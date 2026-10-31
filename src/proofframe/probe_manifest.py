"""Validate the committed probe-benchmark manifest and (optionally) the media it names.

The manifest holds hashes and labels only. Media lives outside Git; `verify_media` re-hashes each file.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

LABEL_SOURCE_PREFIX = "human-adjudicated (Fable review 2026-10-31)"
I2V_LABELS = {"scene_changed", "new_props", "camera_holds", "motion_band", "artifact", "speech_present", "identity_kept"}
_HEX = re.compile(r"[0-9a-f]{64}")


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(manifest: dict) -> list[str]:
    """Return a list of problems; empty means the manifest is structurally sound."""
    errors: list[str] = []
    if manifest.get("synthetic") is not True or manifest.get("provenance_class") != "DEMO_SYNTHETIC":
        errors.append("manifest must declare itself synthetic / DEMO_SYNTHETIC")
    if "NOT a continuity benchmark" not in manifest.get("not_a", ""):
        errors.append("manifest must state it is not a continuity benchmark")
    if (manifest.get("media_storage") or {}).get("in_git") is not False:
        errors.append("media_storage.in_git must be false")
    still = (manifest.get("reference_still") or {}).get("sha256", "")
    if not _HEX.fullmatch(still):
        errors.append("reference still sha256 invalid")
    seen: set[str] = set()
    for clip in manifest.get("clips", []):
        cid = clip.get("clip_id", "?")
        if cid in seen:
            errors.append(f"duplicate clip_id {cid}")
        seen.add(cid)
        if not _HEX.fullmatch(clip.get("sha256", "")):
            errors.append(f"{cid}: sha256 invalid")
        if not str(clip.get("label_source", "")).startswith(LABEL_SOURCE_PREFIX):
            errors.append(f"{cid}: label_source must start with '{LABEL_SOURCE_PREFIX}'")
        if set(clip.get("labels", {})) != I2V_LABELS:
            errors.append(f"{cid}: label keys differ from the declared label set")
        mode = clip.get("generator", {}).get("mode")
        ref = clip.get("reference_still_sha256")
        if mode == "i2v" and ref != still:
            errors.append(f"{cid}: i2v clip must reference the still")
        if mode == "t2v" and ref is not None:
            errors.append(f"{cid}: t2v clip must have no reference")
        if mode not in ("i2v", "t2v"):
            errors.append(f"{cid}: unknown mode {mode!r}")
        if mode == "i2v" and any(clip["labels"].get(k) is None for k in ("scene_changed", "new_props", "camera_holds")):
            errors.append(f"{cid}: i2v clip needs scene_changed/new_props/camera_holds labels")
    if not manifest.get("clips"):
        errors.append("no clips")
    return errors


def verify_media(manifest: dict, media_dir: Path) -> list[str]:
    """Re-hash every named file under media_dir (and the reference still). Returns problems."""
    errors = []
    media_dir = Path(media_dir)
    items = [(manifest["reference_still"]["file"], manifest["reference_still"]["sha256"])]
    items += [(c["file"], c["sha256"]) for c in manifest["clips"]]
    for rel, expected in items:
        p = media_dir / rel
        if not p.is_file():
            errors.append(f"missing: {rel}")
            continue
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            errors.append(f"sha256 mismatch: {rel}")
    return errors
