"""The LLM interface every provider implements."""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from kahaani.cache import DiskCache, cache_key
from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.retry import with_retries

log = logging.getLogger(__name__)


class LLM(ABC):
    name: str = "base"

    def __init__(self, model: str, cache: DiskCache | None = None):
        self.model = model
        self.cache = cache

    def generate_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        *,
        system: str | None = None,
        temperature: float = 0.8,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object shaped like `schema`. Cached and retried.

        `images` (PNG/JPEG bytes) are sent along with the prompt, for vision checks.

        The result is NOT validated against the schema here; callers do that,
        so they can feed validation errors back into a retry prompt.
        """
        key = cache_key(
            self.name,
            self.model,
            system or "",
            prompt,
            schema.model_json_schema(),
            temperature,
            *(images or []),
        )
        if self.cache and (hit := self.cache.get(key)) is not None:
            log.info("llm cache hit provider=%s", self.name)
            return hit

        start = time.perf_counter()
        result = with_retries(
            lambda: self._generate_json(prompt, schema, system, temperature, images or [])
        )
        log.info(
            "llm call provider=%s model=%s secs=%.1f",
            self.name,
            self.model,
            time.perf_counter() - start,
        )
        if self.cache:
            self.cache.set(key, result)
        return result

    supports_images: bool = False

    @abstractmethod
    def _generate_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float,
        images: list[bytes],
    ) -> dict[str, Any]:
        """One raw call. Raise TransientError for retryable failures, ProviderError otherwise."""


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse model output as a JSON object, tolerating ```json fences."""
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"model returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ProviderError("model returned JSON that is not an object")
    return data


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def schema_instructions(schema: type[BaseModel]) -> str:
    """For providers without native schema support: describe the schema in the prompt."""
    return (
        "Respond with ONLY a JSON object (no markdown, no commentary) that matches "
        "this JSON Schema:\n" + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


def check_http(resp: httpx.Response, provider: str) -> None:
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientError(f"{provider} HTTP {resp.status_code}", retry_after=_retry_after(resp))
    if resp.status_code >= 400:
        # Body may echo the prompt, so don't include it.
        raise ProviderError(f"{provider} HTTP {resp.status_code}")
