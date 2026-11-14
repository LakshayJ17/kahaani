"""Layered child-safety checks.

1. Rules (instant, free): name format, lengths, blocklists, injection patterns, contact info.
2. LLM check on the free-text fields, with user text passed as data.
3. After generation: the story text gets the same LLM check, images get a vision check.

Messages returned to the user never quote what they typed.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel

from kahaani.providers.errors import ContentBlocked, ProviderError
from kahaani.providers.llm_base import LLM
from kahaani.schemas import Brief, Story

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

# Word-boundary matches, English, Hinglish and Hindi. Kept short and specific to
# avoid false alarms ("skill" must not match "kill").
BLOCKED_WORDS = [
    # violence / danger
    "kill",
    "killer",
    "revenge",
    "gore",
    "badla",
    "बदला",
    "killing",
    "murder",
    "blood",
    "bloody",
    "gun",
    "guns",
    "pistol",
    "rifle",
    "knife",
    "knives",
    "sword",
    "bomb",
    "explode",
    "explosion",
    "stab",
    "shoot",
    "shooting",
    "dead",
    "death",
    "die",
    "dies",
    "suicide",
    "torture",
    "war",
    "weapon",
    "weapons",
    "beat up",
    "punch",
    "kidnap",
    "hang",
    "poison",
    "fight",
    "fights",
    "fighting",
    "maar",
    "maarna",
    "maaro",
    "khoon",
    "chaku",
    "bandook",
    "goli",
    "मार",
    "मारो",
    "मारना",
    "खून",
    "चाकू",
    "बंदूक",
    "गोली",
    "हत्या",
    "मौत",
    "लड़ाई",
    # horror
    "ghost",
    "ghosts",
    "demon",
    "devil",
    "zombie",
    "monster",
    "monsters",
    "horror",
    "bhoot",
    "chudail",
    "भूत",
    "चुड़ैल",
    "राक्षस",
    # adult
    "sex",
    "sexy",
    "nude",
    "naked",
    "kiss",
    "kissing",
    "boyfriend",
    "girlfriend",
    "porn",
    "beer",
    "wine",
    "alcohol",
    "drunk",
    "daru",
    "sharab",
    "शराब",
    "दारू",
    "cigarette",
    "smoke",
    "smoking",
    "drugs",
    "weed",
    "gamble",
    "gambling",
    "casino",
    # insults
    "stupid",
    "idiot",
    "ugly",
    # body words like "fat" are left to the LLM check ("my fluffy fat cat" is fine)
    "dumb",
    "hate",
    "pagal",
    "gadha",
    "kutta",
    "बेवकूफ",
    "पागल",
    "गधा",
    "मोटा",
    "मोटी",
]
# Real public figures a parent might type. Not exhaustive; the LLM check covers the rest.
PUBLIC_FIGURES = [
    "modi",
    "narendra modi",
    "rahul gandhi",
    "gandhi",
    "kejriwal",
    "trump",
    "biden",
    "obama",
    "putin",
    "elon musk",
    "musk",
    "shah rukh",
    "shahrukh",
    "srk",
    "salman khan",
    "amitabh",
    "virat kohli",
    "kohli",
    "dhoni",
    "sachin",
    "tendulkar",
    "messi",
    "ronaldo",
    "taylor swift",
    "mr beast",
    "mrbeast",
    "spiderman",
    "spider-man",
    "batman",
    "elsa",
    "mickey mouse",
    "peppa",
    "doraemon",
    "chhota bheem",
    "chota bheem",
    "pokemon",
    "pikachu",
    "barbie",
    "hello kitty",
    "frozen",
    "motu patlu",
    "shinchan",
    "paw patrol",
    "मोदी",
    "गांधी",
]
INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier)",
    r"disregard (all |the )?(previous|above|instructions)",
    r"\b(system|developer) (prompt|message|instructions?)\b",
    r"\byou are now\b",
    r"\bact as\b",
    r"\bpretend (to be|you)\b",
    r"\bjailbreak\b",
    r"\bnew instructions?\b",
    r"\binstructions?:",
    r"\bprompt\b",
    r"\bignore\s*(all\s*)?(the\s*|your\s*|these\s*)?(rules|instructions)",
    r"\bbh?ool ja(o|na)\b",
    r"\bnirdesh\b",
    r"निर्देश",
    r"भूल जाओ",
    r"अनदेखा करो",
    r"</?\s*(brief|input|system|instructions?)\s*>",
    r"```",
    r"\{\{|\}\}",
    r"\$\{",
]
CONTACT_PATTERNS = [
    r"https?://",
    r"\bwww\.",
    r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    r"(\+?\d[\d\s-]{7,}\d)",
]


@dataclass
class SafetyResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    checked_by_llm: bool = False


class _Verdict(BaseModel):
    safe: bool
    reason: str


class _InputVerdict(BaseModel):
    """What the parent's text is trying to do, not just whether it's polite."""

    intent: Literal["describes_a_child", "instructions_to_ai", "off_topic", "harmful"]
    injection_attempt: bool
    safe: bool
    reason: str

    @property
    def ok(self) -> bool:
        return self.safe and not self.injection_attempt and self.intent == "describes_a_child"


class _ImageVerdict(BaseModel):
    index: int
    safe: bool
    has_text: bool
    malformed: bool
    matches_scene: bool
    respectful: bool
    reason: str


class _ImagesVerdict(BaseModel):
    images: list[_ImageVerdict]


@dataclass
class ImageCheck:
    safe: bool
    has_text: bool
    reason: str = ""
    malformed: bool = False  # distorted faces or bodies, extra limbs, melted shapes
    matches_scene: bool = True
    # No caricatures or stereotypes, symbols used with respect, and the hero's skin tone as
    # described (image models often draw children lighter than the parent described).
    respectful: bool = True

    @property
    def ok(self) -> bool:
        return (
            self.safe
            and not self.has_text
            and not self.malformed
            and self.matches_scene
            and self.respectful
        )


def _word_regex(words: list[str]) -> re.Pattern:
    # \b doesn't work with Devanagari (vowel signs aren't "word" chars to Python),
    # so treat the whole Devanagari block as letters in the lookarounds.
    alts = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    edge = "[\\w\u0900-\u097f]"
    return re.compile(rf"(?<!{edge})(?:{alts})(?!{edge})", re.IGNORECASE)


# Generated stories get a narrower list: a gentle "not a scary monster at all" is fine.
STORY_BLOCKED_WORDS = [
    "kill",
    "killed",
    "murder",
    "blood",
    "gun",
    "pistol",
    "knife",
    "knives",
    "sword",
    "bomb",
    "stab",
    "shoot",
    "dead",
    "death",
    "suicide",
    "torture",
    "weapon",
    "sex",
    "nude",
    "naked",
    "porn",
    "alcohol",
    "beer",
    "wine",
    "drunk",
    "cigarette",
    "drugs",
    # Foods that offend many Indian families.
    "beef",
    "pork",
    "bacon",
    "गोमांस",
    "खून",
    "चाकू",
    "बंदूक",
    "हत्या",
    "मौत",
    "शराब",
]

BLOCKED_RE = _word_regex(BLOCKED_WORDS)
STORY_BLOCKED_RE = _word_regex(STORY_BLOCKED_WORDS)
FIGURES_RE = _word_regex(PUBLIC_FIGURES)
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)
CONTACT_RE = re.compile("|".join(CONTACT_PATTERNS), re.IGNORECASE)


def _free_text(brief: Brief) -> dict[str, str]:
    fields = {
        "child_name": brief.child_name,
        "appearance": brief.appearance,
        "favourites": brief.favourites,
    }
    if brief.custom_lesson:
        fields["custom_lesson"] = brief.custom_lesson
    return fields


FIELD_LABELS = {
    "child_name": "name",
    "appearance": "looks",
    "favourites": "favourite things",
    "custom_lesson": "lesson",
}


def _squash_spaced_letters(text: str) -> str:
    """'i g n o r e  a l l' -> 'ignore all', so spaced-out tricks still match."""
    return re.sub(r"(?<!\w)(?:\w +){2,}\w(?!\w)", lambda m: re.sub(r" +", "", m.group(0)), text)


# Invisible characters used to hide words from filters (zero-width space, joiners used
# outside Devanagari, word joiner, BOM, bidi controls).
INVISIBLE = re.compile(r"[\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def normalise(text: str) -> str:
    """Fold look-alike and full-width letters (NFKC), drop invisible characters."""
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE.sub("", text)
    return " ".join(text.split())


def check_text_rules(fields: dict[str, str]) -> list[str]:
    """Rule checks on free-text fields. Returns user-facing reasons."""
    reasons = []
    for key, raw in fields.items():
        value = normalise(raw)
        label = FIELD_LABELS.get(key, key)
        squashed = _squash_spaced_letters(value)
        if INJECTION_RE.search(value) or INJECTION_RE.search(squashed):
            reasons.append(f"The {label} field looks like instructions, not a description.")
        elif CONTACT_RE.search(value):
            reasons.append(f"Please don't include links, emails or phone numbers ({label}).")
        elif FIGURES_RE.search(value):
            reasons.append(
                f"Please leave out real people and famous characters ({label}); "
                "we can only write original stories."
            )
        elif BLOCKED_RE.search(value):
            reasons.append(f"The {label} field has words that aren't suitable for this book.")
    return reasons


@cache
def _template(name: str) -> Template:
    return Template((PROMPTS / name).read_text("utf-8"))


def _llm_text_check(llm: LLM, data: dict, context: str) -> _Verdict:
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    prompt = _template("safety_text.txt").substitute(input_json=payload, context=context)
    try:
        raw = llm.generate_json(prompt, _Verdict, temperature=0.0)
    except ContentBlocked:
        return _Verdict(safe=False, reason="refused by the model's safety filter")
    return _Verdict.model_validate(raw)


INTENT_MESSAGES = {
    "injection": "Some details read like instructions to our AI rather than a description of "
    "your child. Please describe your child in plain words.",
    "off_topic": "Please describe your child: how they look, what they love, and the lesson "
    "you'd like.",
    "harmful": "Some details aren't suitable for a children's story. Please change them.",
}


def _intent_key(v: "_InputVerdict") -> str:
    if v.injection_attempt or v.intent == "instructions_to_ai":
        return "injection"
    return "off_topic" if v.intent == "off_topic" else "harmful"


def _llm_input_check(llm: LLM, data: dict, context: str) -> _InputVerdict:
    data = {k: normalise(v) for k, v in data.items()}
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    prompt = _template("safety_input.txt").substitute(input_json=payload, context=context)
    try:
        raw = llm.generate_json(prompt, _InputVerdict, temperature=0.0)
    except ContentBlocked:
        # The model's own safety filter refused even to read it: treat as harmful.
        return _InputVerdict(
            intent="harmful",
            injection_attempt=False,
            safe=False,
            reason="refused by the model's safety filter",
        )
    return _InputVerdict.model_validate(raw)


def check_brief(brief: Brief, llm: LLM | None) -> SafetyResult:
    fields = _free_text(brief)
    reasons = check_text_rules(fields)
    if reasons:
        log.info("brief blocked by rules (%d reasons)", len(reasons))
        return SafetyResult(False, reasons)
    if llm is None:
        return SafetyResult(True)
    verdict = _llm_input_check(
        llm, fields, "These are the form fields a parent filled in about their child."
    )
    if not verdict.ok:
        log.info(
            "brief blocked by llm check intent=%s injection=%s",
            verdict.intent,
            verdict.injection_attempt,
        )
        return SafetyResult(False, [INTENT_MESSAGES[_intent_key(verdict)]], checked_by_llm=True)
    return SafetyResult(True, checked_by_llm=True)


# Asking to change how a child looks (in a page-change request) is never allowed. "Fair skin"
# is a normal description in the form, so these only apply to change requests.
LOOKS_CHANGE_RE = re.compile(
    r"\b(fairer|lighter|whiter|paler|thinner|slimmer|skinnier|less dark|not so dark|"
    r"prettier|more beautiful|more handsome)\b|"
    r"\b(make|turn|draw)\b[^.]{0,30}\b(fair|white|light[- ]skinned|thin|slim|skinny)\b|"
    r"गोरा|गोरी|गोरे|पतला|पतली|सुंदर बना",
    re.IGNORECASE,
)


def check_instruction(text: str, llm: LLM | None) -> SafetyResult:
    """A parent's 'redo this page' request."""
    if LOOKS_CHANGE_RE.search(normalise(text)):
        return SafetyResult(
            False, ["We don't change how a child looks. Every child is drawn as described."]
        )
    reasons = check_text_rules({"custom_lesson": text})
    if reasons:
        return SafetyResult(False, ["That request can't be used. Please rephrase it."])
    if llm is None:
        return SafetyResult(True)
    verdict = _llm_input_check(
        llm, {"request": text}, "This is a parent's request to change one page of the story."
    )
    if not verdict.ok:
        log.info(
            "redo request blocked intent=%s injection=%s", verdict.intent, verdict.injection_attempt
        )
        return SafetyResult(False, ["That request can't be used. Please rephrase it."], True)
    return SafetyResult(True, checked_by_llm=True)


def check_story(story: Story, llm: LLM | None) -> SafetyResult:
    texts = [story.title] + [p.text for p in story.pages]
    scenes = [p.scene for p in story.pages]
    # Rules on generated text: blocklist only (generated text won't have injections).
    if STORY_BLOCKED_RE.search(" ".join(texts + scenes)):
        return SafetyResult(False, ["The story had unsuitable words."])
    if llm is None:
        return SafetyResult(True)
    data = {"title": story.title, "pages": texts[1:], "illustration_notes": scenes}
    verdict = _llm_text_check(llm, data, "This is a generated story for a young child.")
    if not verdict.safe:
        return SafetyResult(False, ["The story didn't pass the safety check."], True)
    return SafetyResult(True, checked_by_llm=True)


def check_images(
    images: list[bytes], vision: LLM | None, descriptions: list[str] | None = None
) -> list[ImageCheck] | None:
    """One vision call for all images. None if no vision model is available.

    `descriptions` says what each image should show, so the model can judge the match.
    """
    if not images or vision is None:
        return None
    descriptions = descriptions or ["a children's book illustration"] * len(images)
    listing = "\n".join(f"{i}: {d}" for i, d in enumerate(descriptions))
    prompt = _template("safety_images.txt").substitute(count=len(images), descriptions=listing)
    try:
        raw = vision.generate_json(prompt, _ImagesVerdict, temperature=0.0, images=images)
        verdicts = _ImagesVerdict.model_validate(raw).images
    except (ProviderError, ValueError) as e:
        log.warning("image check unavailable (%s)", type(e).__name__)
        return None
    by_index = {v.index: v for v in verdicts}
    out = []
    for i in range(len(images)):
        v = by_index.get(i)
        if v is None:  # the model skipped it: be strict and ask for a redraw
            out.append(ImageCheck(True, True, "no verdict"))
        else:
            out.append(
                ImageCheck(v.safe, v.has_text, v.reason, v.malformed, v.matches_scene, v.respectful)
            )
    return out
