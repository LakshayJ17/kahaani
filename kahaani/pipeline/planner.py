"""Step 2: turn a Brief into a validated Story with one LLM call (plus one repair retry)."""

import json
import logging
import math
import re
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

from pydantic import ValidationError

from kahaani.providers.llm_base import LLM
from kahaani.schemas import Brief, Story
from kahaani.taste import prompt_section

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True)
class AgeRule:
    min_sentences: int
    max_sentences: int
    max_words_per_sentence: int
    guidance: str


AGE_RULES: dict[tuple[int, int], AgeRule] = {
    (3, 4): AgeRule(
        1,
        2,
        10,
        "1-2 short sentences per page. Very simple, everyday words. "
        "Use a little repetition or a repeated phrase the child can join in with.",
    ),
    (5, 6): AgeRule(
        2, 3, 14, "2-3 sentences per page. Simple words. A small problem and a clear solution."
    ),
    (7, 8): AgeRule(
        3,
        4,
        18,
        "3-4 sentences per page. A bit of humour. "
        "Show the lesson through what the hero does and how others feel. "
        "Never state the moral directly (no 'she learned that...', "
        "'sharing is good', or similar).",
    ),
}
# Sentence counting is approximate (dialogue, ellipses), so allow one extra.
SENTENCE_SLACK = 1

LANGUAGE_RULES = {
    "en": "Write title and page text in simple Indian English.",
    "hi": "Write title and page text in simple, natural, spoken Hindi in Devanagari script "
    "(the kind parents use at home, not formal or Sanskritised). Write the child's name "
    "in Devanagari too. Only the character and scene fields are in English.",
}

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Phrases that state the moral outright. Ages 7-8 should show it instead.
STATED_MORAL = re.compile(
    r"\b(learn(ed|t) that|reali[sz]ed that|understood that|the lesson|"
    r"(is|are) (always )?(so |very )?(important|the best))\b"
    r"|समझ (गया|गई|गए) कि|सीखा कि|सीख (मिली|ली)|सबसे अच्छी बात",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?।॥]+")


def age_rule(age: int) -> AgeRule:
    for (lo, hi), rule in AGE_RULES.items():
        if lo <= age <= hi:
            return rule
    raise ValueError(f"no age rule for age {age}")


def _age_rules_text(age: int, taste: list[str] | tuple[str, ...] = ()) -> str:
    rule = age_rule(age)
    lo, hi = rule.min_sentences, rule.max_sentences
    # A family's length preference picks one end of the age range, as an exact number;
    # a vague "use the low end" gets ignored by the model.
    if "length:shorter" in taste:
        count = f"exactly {lo} sentence{'s' if lo > 1 else ''}"
    elif "length:longer" in taste:
        count = f"exactly {hi} sentences"
    else:
        count = f"{lo} to {hi} sentences"
    return (
        f"{rule.guidance}\n"
        f"Every page must have {count}, and every sentence at most "
        f"{rule.max_words_per_sentence} words."
    )


@cache
def _template(name: str) -> Template:
    return Template((PROMPTS / name).read_text("utf-8"))


def build_prompt(brief: Brief) -> tuple[str, str]:
    """Return (system, user) prompts. User text is embedded as JSON data, never as prose."""
    brief_data = {
        "child_name": brief.child_name,
        "age": brief.age,
        "appearance": brief.appearance,
        "favourites": brief.favourites,
        "lesson": brief.lesson_text,
    }
    if brief.hero:
        brief_data["hero_is_a"] = brief.hero
    # Escape '<' so typed text can never close the <brief> block early.
    brief_json = json.dumps(brief_data, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    user = _template("planner_user.txt").substitute(
        brief_json=brief_json,
        page_count=brief.pages,
        language_rules=LANGUAGE_RULES[brief.language] + _hero_rule(brief),
        age=brief.age,
        age_rules=_age_rules_text(brief.age, brief.taste),
        lesson=brief.lesson if brief.lesson != "custom" else "the lesson in the brief",
    )
    return _template("planner_system.txt").template, user + prompt_section(brief.taste)


def _hero_rule(brief: Brief) -> str:
    if not brief.hero:
        return ""
    if brief.language == "hi":
        return (
            f"\nThe hero is a {brief.hero}: use matching Hindi verb and adjective forms "
            f"({'थी, गई, खुश हुई' if brief.hero == 'girl' else 'था, गया, खुश हुआ'})."
        )
    return f"\nThe hero is a {brief.hero}: use {'she/her' if brief.hero == 'girl' else 'he/him'}."


def split_sentences(text: str) -> list[str]:
    parts = SENTENCE_END.split(text)
    # Keep only fragments with a letter in them (drops stray quotes after "!").
    return [p.strip() for p in parts if any(c.isalpha() for c in p)]


def _letters(text: str) -> tuple[int, int]:
    """(Devanagari letters, other-script letters) in text."""
    dev = other = 0
    for c in text:
        if DEVANAGARI.match(c):
            dev += 1
        elif c.isalpha():
            other += 1
    return dev, other


def validate_story(story: Story, brief: Brief) -> list[str]:
    """Return human-readable problems (sent back to the LLM). Empty list means valid."""
    problems: list[str] = []
    rule = age_rule(brief.age)
    n = brief.pages

    if len(story.pages) != n:
        problems.append(f"There must be exactly {n} pages, but there are {len(story.pages)}.")
    numbers = [p.number for p in story.pages]
    if numbers != list(range(1, len(story.pages) + 1)):
        problems.append("Page numbers must be 1, 2, 3, ... in order.")

    hero = story.hero_name.strip()
    if not hero:
        problems.append("hero_name is empty.")
    elif brief.language == "en" and hero.casefold() != brief.child_name.casefold():
        problems.append(f'hero_name must be exactly "{brief.child_name}".')

    english_fields = {
        "character.description": story.character.description,
        "character.outfit": story.character.outfit,
        "character.companion": story.character.companion or "",
    }
    for page in story.pages:
        english_fields[f"page {page.number} scene"] = page.scene
    for field, value in english_fields.items():
        if DEVANAGARI.search(value):
            problems.append(f"{field} must be written in English.")

    pages_with_name = 0
    for page in story.pages:
        label = f"Page {page.number}"
        text = page.text.strip()
        if not text:
            problems.append(f"{label} has no text.")
            continue
        if hero and hero.casefold() in text.casefold():
            pages_with_name += 1

        sentences = split_sentences(text)
        max_s = rule.max_sentences + SENTENCE_SLACK
        if not rule.min_sentences <= len(sentences) <= max_s:
            problems.append(
                f"{label} has {len(sentences)} sentences; for age {brief.age} use "
                f"{rule.min_sentences}-{rule.max_sentences}."
            )
        longest = max((len(s.split()) for s in sentences), default=0)
        if longest > rule.max_words_per_sentence:
            problems.append(
                f"{label} has a {longest}-word sentence; for age {brief.age} keep sentences "
                f"under {rule.max_words_per_sentence} words."
            )

        dev, other = _letters(text)
        if brief.language == "hi" and other:
            problems.append(
                f"{label} text must be in Hindi, using only Devanagari script (no other letters)."
            )
        if brief.language == "en" and dev:
            problems.append(f"{label} text must be in English only.")
        if brief.age >= 7 and STATED_MORAL.search(text):
            problems.append(
                f"{label} states the moral directly; for age {brief.age} show it through "
                "what happens instead."
            )

    if hero and story.pages:
        if hero.casefold() not in story.pages[0].text.casefold():
            problems.append("The hero's name must appear on page 1.")
        if pages_with_name < math.ceil(len(story.pages) / 2):
            problems.append("Use the hero's name on most pages.")

    return problems


def _anonymise_scenes(story: Story, brief: Brief) -> Story:
    """Scenes go to the image API: replace the child's name with "the child"."""
    name = re.compile(r"\b" + re.escape(brief.child_name) + r"('s)?\b", re.IGNORECASE)

    def fix(scene: str) -> str:
        return name.sub(lambda m: "the child's" if m.group(1) else "the child", scene)

    pages = [p.model_copy(update={"scene": fix(p.scene)}) for p in story.pages]
    return story.model_copy(update={"pages": pages})


class StoryPlanningError(Exception):
    def __init__(self, problems: list[str], history: list[list[str]] | None = None):
        super().__init__(f"story failed validation after retry ({len(problems)} problems)")
        self.problems = problems
        self.history = history or [problems]


def _parse(raw: dict) -> tuple[Story | None, list[str]]:
    try:
        return Story.model_validate(raw), []
    except ValidationError as e:
        return None, [
            f"{'.'.join(str(x) for x in err['loc']) or 'root'}: {err['msg']}" for err in e.errors()
        ]


def plan_story(brief: Brief, llm: LLM, *, max_attempts: int = 2, variant: int = 0) -> Story:
    """Generate a Story; if it fails validation, retry with the problems listed.

    A non-zero `variant` asks for a different story (and so skips the cache).
    """
    return plan_story_with_stats(brief, llm, max_attempts=max_attempts, variant=variant)[0]


def plan_story_with_stats(
    brief: Brief, llm: LLM, *, max_attempts: int = 2, variant: int = 0
) -> tuple[Story, list[list[str]]]:
    """Like plan_story, but also returns the problems found on each attempt."""
    history: list[list[str]] = []
    system, user = build_prompt(brief)
    if variant:
        user += (
            f"\n\nWrite a completely different story from any earlier one (version {variant + 1})."
        )
    prompt = user
    problems: list[str] = []
    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        raw = llm.generate_json(prompt, Story, system=system)
        story, problems = _parse(raw)
        if story is not None:
            problems = validate_story(story, brief)
        log.info(
            "planner attempt=%d problems=%d secs=%.1f",
            attempt,
            len(problems),
            time.perf_counter() - start,
        )
        history.append(problems)
        if not problems:
            return _anonymise_scenes(story, brief), history
        prompt = user + _template("planner_retry.txt").substitute(
            previous=json.dumps(raw, ensure_ascii=False),
            problems="\n".join(f"- {p}" for p in problems),
        )
    raise StoryPlanningError(problems, history)


def _demo_brief(language: str, age: int, pages: int) -> Brief:
    return Brief(
        child_name="Meera",
        age=age,
        appearance="curly black hair, brown skin, round red glasses",
        favourites="elephants, mangoes",
        lesson="sharing",
        language=language,
        style="watercolour",
        pages=pages,
    )


def main() -> None:
    import argparse

    from kahaani.providers.errors import ProviderError
    from kahaani.providers.llm_chain import build_llm

    parser = argparse.ArgumentParser(description="Generate a story JSON for a demo brief.")
    parser.add_argument("--lang", choices=["en", "hi"], default="en")
    parser.add_argument("--age", type=int, default=5)
    parser.add_argument("--pages", type=int, choices=[4, 8], default=4)
    parser.add_argument("--brief", type=Path, help="JSON file with a Brief, instead of the demo")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.brief:
        brief = Brief.model_validate_json(args.brief.read_text("utf-8"))
    else:
        brief = _demo_brief(args.lang, args.age, args.pages)
    try:
        story = plan_story(brief, build_llm())
    except StoryPlanningError as e:
        print("Story failed validation:\n" + "\n".join(f"- {p}" for p in e.problems))
        raise SystemExit(1) from e
    except ProviderError as e:
        print(f"{e}\nCheck GEMINI_API_KEY / GROQ_API_KEY in .env (see .env.example).")
        raise SystemExit(1) from e
    print(story.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
