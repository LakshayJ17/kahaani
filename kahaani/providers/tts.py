"""Text-to-speech. edge-tts is free and needs no key."""

import asyncio
import io
import logging
import math
import struct
import wave
from abc import ABC, abstractmethod

from kahaani.cache import DiskCache, cache_key
from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.retry import with_retries

log = logging.getLogger(__name__)

VOICES = {"hi": "hi-IN-SwaraNeural", "en": "en-IN-NeerjaNeural"}


class TTS(ABC):
    name = "base"
    ext = "mp3"

    def __init__(self, cache: DiskCache | None = None):
        self.cache = cache

    def synthesize(self, text: str, lang: str) -> bytes:
        key = cache_key(self.name, self._voice_id(lang), text)
        if self.cache and (hit := self.cache.get_bytes(key)) is not None:
            return hit
        audio = with_retries(lambda: self._synthesize(text, lang))
        if self.cache:
            self.cache.set_bytes(key, audio)
        return audio

    def _voice_id(self, lang: str) -> str:
        return lang

    @abstractmethod
    def _synthesize(self, text: str, lang: str) -> bytes: ...


class EdgeTTS(TTS):
    name = "edge"

    def __init__(self, rate: str = "-10%", cache: DiskCache | None = None):
        super().__init__(cache)
        self.rate = rate

    def _voice_id(self, lang: str) -> str:
        return f"{VOICES[lang]}@{self.rate}"

    def _synthesize(self, text: str, lang: str) -> bytes:
        import edge_tts

        async def run() -> bytes:
            out = bytearray()
            comm = edge_tts.Communicate(text, VOICES[lang], rate=self.rate)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    out += chunk["data"]
            return bytes(out)

        try:
            audio = _run_async(run())
        except Exception as e:  # network hiccups, service errors
            raise TransientError(f"edge-tts {type(e).__name__}") from e
        if not audio:
            raise ProviderError("edge-tts returned no audio")
        return audio


class ToneTTS(TTS):
    """Offline stand-in: a soft tone, ~0.06s per character. For tests and dev."""

    name = "tone"
    ext = "wav"

    def _synthesize(self, text: str, lang: str) -> bytes:
        rate, secs = 16000, max(0.5, min(6.0, len(text) * 0.06))
        frames = b"".join(
            struct.pack("<h", int(1500 * math.sin(2 * math.pi * 220 * i / rate)))
            for i in range(int(rate * secs))
        )
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(frames)
        return buf.getvalue()


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside an event loop (e.g. some UI frameworks): run in a fresh thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()
