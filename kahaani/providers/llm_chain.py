"""Try providers in order until one works, and build the chain from settings."""

import logging
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from kahaani.cache import DiskCache
from kahaani.config import Settings, get_settings
from kahaani.providers.errors import ContentBlocked, ProviderError, QuotaExhausted
from kahaani.providers.llm_base import LLM

log = logging.getLogger(__name__)

# After a provider fails, skip it for a while so every later call doesn't
# wait through the same timeouts again.
FAIL_COOLDOWN = 300.0  # seconds, for errors like overload or timeouts
QUOTA_COOLDOWN = 3600.0  # seconds, when a quota is used up


class FallbackLLM(LLM):
    name = "fallback"

    def __init__(self, providers: list[LLM], clock: Callable[[], float] = time.monotonic):
        if not providers:
            raise ValueError("no LLM providers configured; set GEMINI_API_KEY or GROQ_API_KEY")
        super().__init__(model="+".join(p.name for p in providers))
        self.providers = providers
        self.last_used: str | None = None  # "provider/model" that answered last
        self._clock = clock
        self._skip_until: dict[int, float] = {}

    def _healthy(self) -> list[LLM]:
        now = self._clock()
        healthy = [p for i, p in enumerate(self.providers) if self._skip_until.get(i, 0) <= now]
        # If everything is cooling down, try them all anyway rather than fail.
        return healthy or self.providers

    supports_images = True

    def generate_json(self, prompt, schema, *, system=None, temperature=0.8, images=None):
        errors: list[str] = []
        blocked = 0
        for provider in self._healthy():
            if images and not provider.supports_images:
                continue
            try:
                result = provider.generate_json(
                    prompt, schema, system=system, temperature=temperature, images=images
                )
            except ContentBlocked as e:
                # Don't rest the provider: it works, it just refused this text.
                blocked += 1
                errors.append(f"{provider.name}/{provider.model}: {e}")
                continue
            except ProviderError as e:
                label = f"{provider.name}/{provider.model}"
                cooldown = QUOTA_COOLDOWN if isinstance(e, QuotaExhausted) else FAIL_COOLDOWN
                self._skip_until[self.providers.index(provider)] = self._clock() + cooldown
                log.warning("provider %s failed (%s), skipping it for %.0fs", label, e, cooldown)
                errors.append(f"{label}: {e}")
                continue
            self.last_used = f"{provider.name}/{provider.model}"
            return result
        if blocked and blocked == len(errors):
            # Every model that answered refused on safety grounds: that's a verdict, not an outage.
            raise ContentBlocked("refused by every model's safety filter")
        raise ProviderError("all LLM providers failed: " + ("; ".join(errors) or "none usable"))

    def _generate_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float,
        images: list[bytes],
    ) -> dict[str, Any]:  # pragma: no cover - generate_json is overridden
        raise NotImplementedError


def build_llm(settings: Settings | None = None) -> LLM:
    s = settings or get_settings()
    cache = DiskCache(s.cache_dir, "llm") if s.cache_enabled else None
    providers: list[LLM] = []
    for name in s.llm_order:
        if name == "gemini" and s.gemini_api_key:
            from kahaani.providers.llm_gemini import GeminiLLM

            # Each Gemini model has its own free daily quota, so chain several.
            for model in s.gemini_models:
                providers.append(GeminiLLM(s.gemini_api_key, model, cache))
        elif name == "groq" and s.groq_api_key:
            from kahaani.providers.llm_groq import GroqLLM

            providers.append(GroqLLM(s.groq_api_key, s.groq_model, cache))
    return FallbackLLM(providers)


def build_vision(settings: Settings | None = None) -> LLM | None:
    """Gemini models that can look at images, or None without a Gemini key."""
    s = settings or get_settings()
    if not s.gemini_api_key or not s.vision_models:
        return None
    from kahaani.providers.llm_gemini import GeminiLLM

    cache = DiskCache(s.cache_dir, "vision") if s.cache_enabled else None
    return FallbackLLM([GeminiLLM(s.gemini_api_key, m, cache) for m in s.vision_models])
