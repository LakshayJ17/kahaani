"""File storage for book pictures and narration.

- LocalBlobs: a folder (local dev, tests).
- SupabaseBlobs: a PRIVATE Supabase Storage bucket, reached with the service-role key.
  Files are never public; the API checks who is signed in and streams them itself.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.retry import with_retries


class Blobs(ABC):
    @abstractmethod
    def put(self, path: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, path: str) -> bytes: ...

    @abstractmethod
    def delete(self, paths: list[str]) -> None: ...


def _safe(path: str) -> str:
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("bad blob path")
    return path


class LocalBlobs(Blobs):
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def put(self, path: str, data: bytes, content_type: str) -> None:
        p = self.root / _safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, path: str) -> bytes:
        try:
            return (self.root / _safe(path)).read_bytes()
        except FileNotFoundError as e:
            raise KeyError(path) from e

    def delete(self, paths: list[str]) -> None:
        for path in paths:
            (self.root / _safe(path)).unlink(missing_ok=True)


def supabase_headers(key: str) -> dict[str, str]:
    """Headers for server-side Supabase calls. New secret keys (sb_secret_...) aren't JWTs and
    go in `apikey` only; legacy service_role keys are JWTs and also go in Authorization."""
    if key.startswith("sb_"):
        return {"apikey": key}
    return {"apikey": key, "Authorization": f"Bearer {key}"}


class SupabaseBlobs(Blobs):
    def __init__(self, url: str, service_key: str, bucket: str = "kahaani"):
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self.headers = supabase_headers(service_key)

    def ensure_bucket(self) -> None:
        r = httpx.post(
            f"{self.base}/bucket",
            headers=self.headers,
            timeout=30,
            json={"id": self.bucket, "name": self.bucket, "public": False},
        )
        if r.status_code not in (200, 201, 400, 409):  # 400/409: already exists
            raise ProviderError(f"supabase storage HTTP {r.status_code}")

    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        def go():
            try:
                r = httpx.request(
                    method,
                    f"{self.base}/{path}",
                    headers={**self.headers, **kw.pop("headers", {})},
                    timeout=60,
                    **kw,
                )
            except httpx.TransportError as e:
                raise TransientError(f"supabase storage {type(e).__name__}") from e
            if r.status_code == 429 or r.status_code >= 500:
                raise TransientError(f"supabase storage HTTP {r.status_code}")
            return r

        return with_retries(go)

    def put(self, path: str, data: bytes, content_type: str) -> None:
        r = self._call(
            "POST",
            f"object/{self.bucket}/{_safe(path)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        if r.status_code >= 400:
            raise ProviderError(f"supabase storage upload HTTP {r.status_code}")

    def get(self, path: str) -> bytes:
        r = self._call("GET", f"object/authenticated/{self.bucket}/{_safe(path)}")
        if r.status_code in (400, 404):
            raise KeyError(path)
        if r.status_code >= 400:
            raise ProviderError(f"supabase storage download HTTP {r.status_code}")
        return r.content

    def delete(self, paths: list[str]) -> None:
        if paths:
            self._call(
                "DELETE", f"object/{self.bucket}", json={"prefixes": [_safe(p) for p in paths]}
            )
