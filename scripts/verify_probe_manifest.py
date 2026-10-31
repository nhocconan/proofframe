"""Check the probe benchmark manifest; with a media directory, re-hash every clip.

  python scripts/verify_probe_manifest.py examples/evaluation_dataset/probe-2026-10-31.manifest.json [MEDIA_DIR]
Exit 0 = valid (and all hashes match when MEDIA_DIR is given); prints the manifest sha256 (the lock value).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from proofframe import probe_manifest as pm


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print(__doc__)
        return 2
    path = Path(argv[0])
    manifest = pm.load(path)
    problems = pm.validate(manifest)
    if len(argv) == 2:
        problems += pm.verify_media(manifest, Path(argv[1]))
    for p in problems:
        print("FAIL:", p)
    print(f"manifest sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}; "
          f"{len(manifest['clips'])} clips; media {'verified' if len(argv) == 2 and not problems else 'not checked' if len(argv) == 1 else 'FAILED'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
