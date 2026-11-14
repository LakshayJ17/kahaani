"""Data models shared by every pipeline step."""

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Lesson = Literal[
    "sharing",
    "bravery",
    "honesty",
    "kindness",
    "trying new food",
    "sleeping on time",
    "custom",
]
Mood = Literal["happy", "curious", "worried", "brave", "calm", "proud"]
# A child's learned taste (see kahaani.taste); fixed vocabulary, never free text.
TasteToken = Literal[
    "tone:funny",
    "tone:calm",
    "length:shorter",
    "length:longer",
    "words:simpler",
    "words:richer",
    "plot:adventure",
    "lesson:subtle",
]


class Brief(BaseModel):
    """What the parent types into the form."""

    child_name: str = Field(min_length=1, max_length=20)
    age: int = Field(ge=3, le=8)
    appearance: str = Field(max_length=150)  # "curly black hair, brown skin, round glasses"
    favourites: str = Field(max_length=100)  # "elephants, mangoes"
    lesson: Lesson
    custom_lesson: str | None = Field(default=None, max_length=80)
    language: Literal["hi", "en"]
    style: Literal["watercolour", "cartoon", "folk"]
    pages: Literal[4, 8] = 4
    # Hindi verbs agree with the hero's gender, so stories (and shared templates) need it.
    hero: Literal["girl", "boy"] | None = None
    taste: list[TasteToken] = Field(default_factory=list)

    @field_validator("child_name", "appearance", "favourites", "custom_lesson")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v is not None else None

    @field_validator("child_name")
    @classmethod
    def _name_letters_only(cls, v: str) -> str:
        # Letters (any script, incl. Devanagari vowel signs) and single spaces only.
        ok = all(c == " " or unicodedata.category(c)[0] in ("L", "M") for c in v)
        if not v or not ok:
            raise ValueError("name may contain only letters and spaces")
        return v

    @model_validator(mode="after")
    def _custom_lesson_needed(self) -> "Brief":
        if self.lesson == "custom" and not self.custom_lesson:
            raise ValueError("custom_lesson is required when lesson is 'custom'")
        if self.lesson != "custom":
            self.custom_lesson = None
        return self

    @property
    def lesson_text(self) -> str:
        return self.custom_lesson if self.lesson == "custom" else self.lesson


class CharacterSheet(BaseModel):
    description: str  # fixed English description reused in EVERY image prompt
    outfit: str
    companion: str | None  # e.g. "a small grey baby elephant"


class Page(BaseModel):
    number: int
    text: str  # in the chosen language, age-appropriate
    scene: str  # English, for the image model; no text in the image
    mood: Mood


class Story(BaseModel):
    title: str
    # The child's name exactly as written in the story text. Lets us check the
    # name appears even when a Latin-script name is written in Devanagari.
    hero_name: str
    character: CharacterSheet
    pages: list[Page]
