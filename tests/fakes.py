import json
import re
from typing import Any

from kahaani.providers.llm_base import LLM


class FakeLLM(LLM):
    """Returns scripted responses in order and records every prompt it was sent."""

    name = "fake"

    def __init__(self, responses: list[Any], cache=None):
        super().__init__("fake-model", cache)
        self.responses = list(responses)
        self.prompts: list[str] = []

    supports_images = True

    def _generate_json(self, prompt, schema, system, temperature, images=()):
        self.prompts.append(prompt)
        self.images = list(images)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def story_dict(name="Meera", pages=4, lang="en", sentences_per_page=2) -> dict:
    if lang == "en":
        line = f"{name} loves mangoes."
        extra = " She smiles at the sun."
    else:
        line = "मीरा को आम पसंद हैं।"
        extra = " वह मुस्कुराती है।"
        name = "मीरा"
    text = line + extra * (sentences_per_page - 1)
    return {
        "title": "Mango Day" if lang == "en" else "आम का दिन",
        "hero_name": name,
        "character": {
            "description": "a 5-year-old Indian girl, curly black hair, round red glasses",
            "outfit": "yellow kurta with blue flowers",
            "companion": "a small grey baby elephant",
        },
        "pages": [
            {"number": i, "text": text, "scene": "A sunny mango orchard", "mood": "happy"}
            for i in range(1, pages + 1)
        ],
    }


class SchemaFakeLLM(LLM):
    """Answers by schema: a valid story, 'safe' verdicts, all-clear image checks.

    Override behaviour per schema name with `overrides`, e.g.
    {"_Verdict": {"safe": False, "reason": "x"}} or a callable(prompt, images) -> dict.
    """

    name = "schemafake"
    supports_images = True

    def __init__(self, story=None, overrides=None):
        super().__init__("fake", None)
        self.story = story or story_dict()
        self.overrides = overrides or {}
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def _generate_json(self, prompt, schema, system, temperature, images=()):
        name = schema.__name__
        self.calls.append(name)
        self.prompts.append(prompt)
        if name in self.overrides:
            o = self.overrides[name]
            return o(prompt, images) if callable(o) else o
        if name == "Story":
            # Like a real model, write about the child named in the brief.
            m = re.search(r'"child_name": "([^"]+)"', prompt)
            if m and self.story.get("hero_name") == "Meera" and m.group(1) != "Meera":
                return json.loads(json.dumps(self.story).replace("Meera", m.group(1)))
            return self.story
        if name == "_Verdict":
            return {"safe": True, "reason": "fine"}
        if name == "_InputVerdict":
            return {
                "intent": "describes_a_child",
                "injection_attempt": False,
                "safe": True,
                "reason": "fine",
            }
        if name == "_StoryReview":
            return {
                "pages": [],
                "coherent": True,
                "double_meaning": False,
                "abusive_or_unsafe": False,
                "offensive_or_stereotyped": False,
                "respect_notes": [],
                "age_appropriate": True,
                "text_matches_scenes": True,
                "summary": "good",
            }
        if name == "_ImagesVerdict":
            return {
                "images": [
                    {
                        "index": i,
                        "safe": True,
                        "has_text": False,
                        "malformed": False,
                        "matches_scene": True,
                        "respectful": True,
                        "reason": "ok",
                    }
                    for i in range(len(images))
                ]
            }
        if name == "_Spelling":
            return {"devanagari": "आरव"}
        if name == "_Character":
            return {
                "description": "a 5-year-old Indian boy with short black hair",
                "outfit": "green t-shirt and blue shorts",
            }
        if name == "Page":
            return {
                "number": 1,
                "text": "Meera laughs at the moon. She waves hello.",
                "scene": "Meera waving at the moon",
                "mood": "happy",
            }
        raise AssertionError(f"unexpected schema {name}")
