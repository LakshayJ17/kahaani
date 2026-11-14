"""Cloudflare Workers AI image models (free daily allowance).

- FLUX.2 [klein] (default): multipart input, takes a seed AND reference images, so every
  page is drawn from the approved hero picture. Big win for consistency.
- FLUX.1 [schnell]: JSON input, prompt + steps only (no seed, no reference).
"""

import base64
import logging

import httpx

from kahaani.cache import DiskCache
from kahaani.providers.errors import ProviderError, QuotaExhausted, TransientError
from kahaani.providers.image_base import ImageGen

log = logging.getLogger(__name__)
DEFAULT_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"


class CloudflareImageGen(ImageGen):
    name = "cloudflare"

    def __init__(
        self,
        account_id: str,
        api_token: str,
        model: str = DEFAULT_MODEL,
        cache: DiskCache | None = None,
        steps: int = 6,
    ):
        super().__init__(model, cache)
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._steps = steps  # schnell only: up to 8; more = more detail and more quota
        self.multipart = "flux-2" in model
        self.uses_reference = self.multipart

    def _generate(self, prompt: str, seed: int | None, ref: bytes | None, size: int) -> bytes:
        try:
            if self.multipart:
                data = {"prompt": prompt, "width": str(size), "height": str(size)}
                if seed is not None:
                    data["seed"] = str(seed)
                files = {"input_image_0": ("ref.jpg", ref, "image/jpeg")} if ref else None
                # httpx only sends multipart when there's a file; force it with an empty part.
                resp = httpx.post(
                    self._url,
                    data=data,
                    files=files or {"_": (None, "")},
                    headers=self._headers,
                    timeout=180,
                )
            else:
                body = {"prompt": prompt[:2048], "steps": self._steps}
                resp = httpx.post(self._url, json=body, headers=self._headers, timeout=120)
        except httpx.TransportError as e:
            raise TransientError(f"cloudflare {type(e).__name__}") from e

        if resp.status_code >= 400:
            message = _error_message(resp).lower()
            if "neuron" in message or "daily" in message or "quota" in message:
                raise QuotaExhausted("cloudflare daily free allowance used up")
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientError(f"cloudflare HTTP {resp.status_code}")
            log.warning("cloudflare error %s: %s", resp.status_code, message[:200])
            raise ProviderError(f"cloudflare HTTP {resp.status_code}")

        if resp.headers.get("content-type", "").startswith("image/"):
            return resp.content
        try:
            return base64.b64decode(resp.json()["result"]["image"])
        except (KeyError, ValueError, TypeError) as e:
            raise ProviderError("cloudflare returned no image") from e


def _error_message(resp: httpx.Response) -> str:
    try:
        return " ".join(e.get("message", "") for e in resp.json().get("errors", []))
    except ValueError:
        return resp.text[:300]
