"""The image-generation interface every provider implements."""

import logging
import time
from abc import ABC, abstractmethod

from kahaani.cache import DiskCache, cache_key
from kahaani.providers.retry import with_retries

log = logging.getLogger(__name__)


class ImageGen(ABC):
    name: str = "base"
    # Whether `ref` (a reference image of the hero) is actually used for conditioning.
    uses_reference: bool = False

    def __init__(self, model: str, cache: DiskCache | None = None):
        self.model = model
        self.cache = cache

    def generate(
        self,
        prompt: str,
        *,
        seed: int | None = None,
        ref: bytes | None = None,
        size: int = 1024,
    ) -> bytes:
        """Return image bytes (PNG or JPEG). Cached and retried."""
        key = cache_key(self.name, self.model, prompt, seed, ref or b"", size)
        if self.cache and (hit := self.cache.get_bytes(key)) is not None:
            log.info("image cache hit provider=%s", self.name)
            return hit
        start = time.perf_counter()
        image = with_retries(lambda: self._generate(prompt, seed, ref, size))
        log.info("image provider=%s secs=%.1f", self.name, time.perf_counter() - start)
        if self.cache:
            self.cache.set_bytes(key, image)
        return image

    @abstractmethod
    def _generate(self, prompt: str, seed: int | None, ref: bytes | None, size: int) -> bytes:
        """One raw call. Raise TransientError for retryable failures, ProviderError otherwise."""
