"""Content-addressed local blob store: <data>/blobs/<aa>/<sha256>, write-once, read-only."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{64}$")


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalStore:
    def __init__(self, data_dir: Path | str):
        self.root = Path(data_dir) / "blobs"
        self.tmp = Path(data_dir) / "tmp"
        self.root.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)

    def path_for(self, sha256: str) -> Path:
        if not _SHA.match(sha256):
            raise ValueError("invalid sha256")
        return self.root / sha256[:2] / sha256

    def exists(self, sha256: str) -> bool:
        return self.path_for(sha256).is_file()

    def media_type_for(self, sha256: str) -> str | None:
        meta = self.path_for(sha256).with_name(sha256 + ".type")
        try:
            return meta.read_text().strip() or None
        except OSError:
            return None

    def put_file(self, src: Path, *, media_type: str) -> str:
        """Copy src into the store (re-hashing during the copy); returns sha256."""
        src = Path(src)
        fd, tmp_name = tempfile.mkstemp(dir=self.tmp, prefix="put-")
        h = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            return self._commit(Path(tmp_name), h.hexdigest(), media_type)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def put_tmp(self, tmp_path: Path, sha256: str, *, media_type: str) -> str:
        """Adopt a temp file already on the store filesystem; re-hashes before commit."""
        actual = hash_file(tmp_path)
        if actual != sha256:
            raise ValueError("sha256 mismatch on put")
        return self._commit(tmp_path, actual, media_type, move=True)

    def _commit(self, tmp: Path, sha: str, media_type: str, move: bool = False) -> str:
        dest = self.path_for(sha)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.chmod(tmp, 0o444)
            os.replace(tmp, dest)  # atomic on the same filesystem
        elif move and tmp.exists():
            tmp.unlink()
        meta = dest.with_name(sha + ".type")
        if not meta.exists():
            mt = self.tmp / f"type-{sha}-{os.getpid()}"
            mt.write_text(media_type)
            os.chmod(mt, 0o444)
            os.replace(mt, meta)
        return sha

    def verify(self, sha256: str) -> bool:
        p = self.path_for(sha256)
        return p.is_file() and hash_file(p) == sha256
