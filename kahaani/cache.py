"""Disk cache keyed by a hash of everything that affects a provider's output."""

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(*parts: Any) -> str:
    """sha256 over the parts, in order. Dicts are serialised with sorted keys."""
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            part = "bytes:" + hashlib.sha256(part).hexdigest()
        elif not isinstance(part, str):
            part = json.dumps(part, sort_keys=True, ensure_ascii=False, default=str)
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")  # separator, so ("ab", "c") != ("a", "bc")
    return h.hexdigest()


class DiskCache:
    """Stores values as files under <root>/<namespace>/<key[:2]>/<key>.<ext>."""

    def __init__(self, root: Path | str, namespace: str = "llm"):
        self.dir = Path(root) / namespace

    def _path(self, key: str, ext: str) -> Path:
        return self.dir / key[:2] / f"{key}.{ext}"

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic, so a crash never leaves a half-written entry

    def get(self, key: str) -> Any | None:
        try:
            return json.loads(self._path(key, "json").read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any) -> None:
        self._write(self._path(key, "json"), json.dumps(value, ensure_ascii=False).encode())

    def get_bytes(self, key: str) -> bytes | None:
        try:
            return self._path(key, "bin").read_bytes()
        except FileNotFoundError:
            return None

    def set_bytes(self, key: str, value: bytes) -> None:
        self._write(self._path(key, "bin"), value)
