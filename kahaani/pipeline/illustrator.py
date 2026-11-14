"""Step 3-4: the hero reference image and page illustrations.

Consistency comes from fixed inputs on every page: the same character sentence, style
prefix and seed. Models that accept a reference image (FLUX.2 klein on Cloudflare,
SDXL + IP-Adapter) also get the approved hero picture, which helps the most.
"""

import hashlib

from kahaani.providers.image_base import ImageGen
from kahaani.schemas import Brief, Page, Story

STYLE_PREFIXES = {
    "watercolour": (
        "Soft watercolour children's picture-book illustration, gentle washes, "
        "warm pastel colours, visible paper texture"
    ),
    "cartoon": (
        "Bright cheerful 2D cartoon children's book illustration, clean bold outlines, "
        "flat vibrant colours, simple shapes"
    ),
    "folk": (
        "Indian folk art children's illustration inspired by Madhubani painting, "
        "bold black outlines, flat earthy reds, yellows and greens, decorative patterns"
    ),
}
NO_TEXT = "no text, no letters, no words, no writing"
GENTLE = "warm, gentle and friendly mood, cosy and well lit"


def character_prompt(story: Story) -> str:
    """The fixed hero description, reused word for word in every prompt."""
    c = story.character
    text = f"{c.description.rstrip('. ')}, wearing {c.outfit.rstrip('. ')}"
    return text


def companion_prompt(story: Story) -> str:
    comp = story.character.companion
    return f"With {comp.rstrip('. ')}" if comp else ""


def hero_prompt(brief: Brief, story: Story) -> str:
    parts = [
        STYLE_PREFIXES[brief.style],
        f"Character reference: {character_prompt(story)}",
        companion_prompt(story),
        "Full body, standing, facing the viewer, friendly smile, plain light background",
        f"Children's book illustration, soft lighting, {GENTLE}, {NO_TEXT}",
    ]
    return ". ".join(p for p in parts if p) + "."


def page_prompt(brief: Brief, story: Story, page: Page, extra: str = "") -> str:
    parts = [
        STYLE_PREFIXES[brief.style],
        character_prompt(story),
        companion_prompt(story),
        f"Scene: {page.scene.rstrip('. ')}",
        f"Mood: {page.mood}",
        extra,
        f"Children's book illustration, soft lighting, {GENTLE}, {NO_TEXT}",
    ]
    return ". ".join(p for p in parts if p) + "."


def reference_page_prompt(brief: Brief, story: Story, page: Page, extra: str = "") -> str:
    """For reference-image models: scene first, and use the reference for looks only.

    Without this the model tends to copy the reference pose and ignore the scene.
    """
    parts = [
        STYLE_PREFIXES[brief.style],
        f"Scene: {page.scene.rstrip('. ')}",
        f"Mood: {page.mood}",
        (
            "The main child is the same child as in the reference image "
            f"({character_prompt(story)}): keep their face, hairstyle, skin tone, accessories "
            "and outfit exactly as in the reference, adding nothing new, but draw a new pose, "
            "action and camera angle that fit the scene, in a full new background. "
            "Any other people look clearly different from the main child"
        ),
        companion_prompt(story),
        extra,
        f"Children's book illustration, {GENTLE}, {NO_TEXT}",
    ]
    return ". ".join(p for p in parts if p) + "."


def book_seed(story: Story, variant: int = 0) -> int:
    """Same seed for every page of a book. A new hero variant gets a new seed."""
    h = hashlib.sha256(f"{character_prompt(story)}|{variant}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 2_147_483_647


class Illustrator:
    def __init__(self, image_gen: ImageGen, size: int = 1024):
        self.gen = image_gen
        self.size = size

    def hero(self, brief: Brief, story: Story, variant: int = 0) -> bytes:
        return self.gen.generate(
            hero_prompt(brief, story), seed=book_seed(story, variant), size=self.size
        )

    def page(
        self,
        brief: Brief,
        story: Story,
        page: Page,
        *,
        hero: bytes | None,
        variant: int = 0,
        retry: int = 0,
    ) -> bytes:
        # A retry (after a failed check) nudges the seed and repeats "no text" more firmly.
        extra = "Absolutely no writing or signs anywhere in the picture" if retry else ""
        seed = book_seed(story, variant) + retry * 7919
        if self.gen.uses_reference and hero is not None:
            prompt = reference_page_prompt(brief, story, page, extra)
            return self.gen.generate(prompt, seed=seed, ref=hero, size=self.size)
        return self.gen.generate(page_prompt(brief, story, page, extra), seed=seed, size=self.size)
