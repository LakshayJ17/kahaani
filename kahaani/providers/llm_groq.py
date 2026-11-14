from typing import Any

import httpx
from pydantic import BaseModel

from kahaani.cache import DiskCache
from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.llm_base import LLM, check_http, parse_json_object, schema_instructions

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(LLM):
    """Groq's OpenAI-compatible API in JSON mode."""

    name = "groq"

    def __init__(self, api_key: str, model: str, cache: DiskCache | None = None):
        super().__init__(model, cache)
        self._api_key = api_key

    def _generate_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float,
        images: list[bytes],
    ) -> dict[str, Any]:
        if images:
            raise ProviderError("groq provider does not accept images")
        system_msg = "\n\n".join(s for s in (system, schema_instructions(schema)) if s)
        body = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            resp = httpx.post(
                GROQ_URL,
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=90,
            )
        except httpx.TransportError as e:
            raise TransientError(f"groq {type(e).__name__}") from e
        check_http(resp, "groq")
        return parse_json_object(resp.json()["choices"][0]["message"]["content"])
