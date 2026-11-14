"""Offline stand-in images: simple shapes, no API, no quota.

Used for tests and for working on layout before Cloudflare is set up. The hero
is drawn from a hash of the character text, so they look 'consistent' across pages.
"""

import hashlib
import io
import re

from PIL import Image, ImageDraw, ImageFilter

from kahaani.cache import DiskCache
from kahaani.providers.image_base import ImageGen


def _colour(seed: bytes, i: int) -> tuple[int, int, int]:
    h = hashlib.sha256(seed + bytes([i])).digest()
    return (60 + h[0] % 180, 60 + h[1] % 180, 60 + h[2] % 180)


class PlaceholderImageGen(ImageGen):
    name = "placeholder"

    def __init__(self, cache: DiskCache | None = None):
        super().__init__("shapes-v1", cache)

    def _generate(self, prompt: str, seed: int | None, ref: bytes | None, size: int) -> bytes:
        size = min(size, 768)
        # Character part of the prompt (before "Scene:") decides the hero's colours.
        hero_text = re.split(r"Scene:|Full body", prompt, maxsplit=1)[0]
        hero_text = hero_text.replace("Character reference: ", "").encode()
        scene_text = prompt.encode() + str(seed).encode()

        img = Image.new("RGB", (size, size), _colour(scene_text, 0))
        d = ImageDraw.Draw(img)
        sky, ground = _colour(scene_text, 1), _colour(scene_text, 2)
        for y in range(size):  # sky gradient
            t = y / size
            d.line([(0, y), (size, y)], fill=tuple(int(a * (1 - t) + 255 * t) for a in sky))
        d.rectangle([0, int(size * 0.7), size, size], fill=ground)
        h = hashlib.sha256(scene_text).digest()
        for i in range(5):  # scenery blobs
            x, y, r = h[i] * size // 255, h[i + 5] * size // 400, 20 + h[i + 10] % 60
            d.ellipse([x - r, y - r, x + r, y + r], fill=_colour(scene_text, 3 + i))
        # The hero: body, head, hair.
        cx, base = size // 2 + (h[20] % 120 - 60), int(size * 0.78)
        d.rounded_rectangle([cx - 60, base - 200, cx + 60, base], 30, fill=_colour(hero_text, 7))
        d.ellipse([cx - 55, base - 320, cx + 55, base - 210], fill=(176, 120, 80))
        d.chord([cx - 60, base - 330, cx + 60, base - 250], 180, 360, fill=_colour(hero_text, 8))
        img = img.filter(ImageFilter.SMOOTH)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
