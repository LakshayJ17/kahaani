from typing import Any

from pydantic import BaseModel

from kahaani.cache import DiskCache
from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.llm_base import LLM, parse_json_object


def _retry_delay(details: object) -> float | None:
    """Pull RetryInfo.retryDelay (e.g. "34s") out of a Gemini error body."""
    if not isinstance(details, dict):
        return None
    err = details.get("error", details)
    for item in err.get("details", []) if isinstance(err, dict) else []:
        delay = item.get("retryDelay") if isinstance(item, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    return None


def _mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class GeminiLLM(LLM):
    """Gemini via google-genai, using native structured output. Accepts images."""

    name = "gemini"
    supports_images = True

    def __init__(self, api_key: str, model: str, cache: DiskCache | None = None):
        super().__init__(model, cache)
        from google import genai  # imported lazily so tests don't need it
        from google.genai import types

        # Timeout in ms, so an overloaded model can't hang the app.
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45_000))

    def _generate_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        system: str | None,
        temperature: float,
        images: list[bytes],
    ) -> dict[str, Any]:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        contents: list[Any] = [prompt]
        contents += [types.Part.from_bytes(data=img, mime_type=_mime(img)) for img in images]
        try:
            resp = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as e:
            code = e.code or 0
            if code == 504:
                # Gateway timeout: the model is overloaded right now. Retrying it wastes
                # minutes, so move on to the next model in the chain instead.
                raise ProviderError("gemini HTTP 504 (overloaded)") from e
            if code == 429 or code >= 500:
                raise TransientError(
                    f"gemini HTTP {code}", retry_after=_retry_delay(e.details)
                ) from e
            raise ProviderError(f"gemini HTTP {code}") from e
        except Exception as e:  # network errors, our own timeout
            if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                raise ProviderError("gemini timed out (overloaded)") from e
            raise TransientError(f"gemini {type(e).__name__}") from e

        if not resp.text:
            raise ProviderError("gemini returned no text (possibly safety-blocked)")
        return parse_json_object(resp.text)
