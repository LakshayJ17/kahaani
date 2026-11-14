"""Quality review: decides whether a generated book is good enough to show.

Runs after the safety checks, as a second pair of eyes:
- story text: an AI editor checks grammar and spelling (including Hindi), sense and flow,
  double meanings, abuse, age fit and text/scene match, and fixes small grammar slips;
- generated text is also checked by rules for prompt-injection leftovers (links, "as an AI",
  instructions, code);
- pictures are checked in code for broken, tiny, blank or flat images (the vision model
  separately checks safety, distortion and scene match, see safety.check_images).

Every check is recorded in a QualityReport, which travels with the book and is shown to the
parent as "How this book was checked".
"""

import io
import json
import logging
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel

from kahaani.pipeline import planner
from kahaani.pipeline.safety import STORY_BLOCKED_RE
from kahaani.providers.llm_base import LLM
from kahaani.schemas import Brief, Story

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

Status = Literal["passed", "fixed", "flagged", "skipped"]


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""


@dataclass
class QualityReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: Status, detail: str = "") -> None:
        # One entry per check name; a later result replaces an earlier one.
        self.checks = [c for c in self.checks if c.name != name]
        self.checks.append(Check(name, status, detail))

    @property
    def flagged(self) -> list[Check]:
        return [c for c in self.checks if c.status == "flagged"]

    def as_list(self) -> list[dict]:
        return [{"name": c.name, "status": c.status, "detail": c.detail} for c in self.checks]


# ----------------------------------------------------------------------------- story


class _PageReview(BaseModel):
    number: int
    grammar_ok: bool
    makes_sense: bool
    issues: list[str]
    corrected_text: str


class _StoryReview(BaseModel):
    pages: list[_PageReview]
    coherent: bool
    double_meaning: bool
    abusive_or_unsafe: bool
    age_appropriate: bool
    text_matches_scenes: bool
    summary: str


# Things a children's story should never contain; usually a sign that typed text steered
# the writer (prompt injection) or the model broke character.
LEAKAGE = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w-]+\.\w+|```|[{}<>]|\b(as an ai|language model|chatgpt|"
    r"gemini|openai|prompt|system message|json)\b",
    re.IGNORECASE,
)


@dataclass
class StoryVerdict:
    story: Story  # possibly with grammar fixes applied
    decision: Literal["show", "rewrite", "reject"]
    report: QualityReport
    reason: str = ""


@cache
def _template() -> Template:
    return Template((PROMPTS / "review_story.txt").read_text("utf-8"))


def leakage_problems(story: Story) -> list[str]:
    fields = {"title": story.title, **{f"page {p.number}": p.text for p in story.pages}}
    fields |= {f"page {p.number} scene": p.scene for p in story.pages}
    return [name for name, text in fields.items() if LEAKAGE.search(text)]


def _apply_fixes(story: Story, brief: Brief, review: _StoryReview) -> tuple[Story, list[int]]:
    """Use the editor's corrected text where it doesn't break any of our rules."""
    fixes = {
        r.number: r.corrected_text.strip()
        for r in review.pages
        if not r.grammar_ok and r.corrected_text.strip()
    }
    if not fixes:
        return story, []
    pages = [
        p.model_copy(update={"text": fixes[p.number]}) if p.number in fixes else p
        for p in story.pages
    ]
    fixed = story.model_copy(update={"pages": pages})
    # The fix must still pass the age/length/script/name rules and the word blocklist.
    if planner.validate_story(fixed, brief) or STORY_BLOCKED_RE.search(
        " ".join(p.text for p in fixed.pages)
    ):
        log.info("reviewer fixes rejected by validator; keeping original text")
        return story, []
    return fixed, sorted(fixes)


def review_story(story: Story, brief: Brief, llm: LLM | None) -> StoryVerdict:
    report = QualityReport()

    leaks = leakage_problems(story)
    if leaks:
        report.add("No hidden instructions", "flagged", ", ".join(leaks))
        return StoryVerdict(story, "rewrite", report, "possible prompt-injection leftovers")
    report.add("No hidden instructions", "passed")

    if llm is None:
        report.add("Editor's review", "skipped", "No review model available")
        return StoryVerdict(story, "show", report)

    data = {
        "title": story.title,
        "pages": [
            {"number": p.number, "text": p.text, "illustration_notes": p.scene} for p in story.pages
        ],
    }
    prompt = _template().substitute(
        language="Hindi" if brief.language == "hi" else "English",
        age=brief.age,
        lesson=brief.lesson_text,
        story_json=json.dumps(data, ensure_ascii=False, indent=1).replace("<", "\\u003c"),
    )
    review = _StoryReview.model_validate(llm.generate_json(prompt, _StoryReview, temperature=0.0))
    log.info(
        "review coherent=%s double=%s unsafe=%s age=%s grammar_issues=%d",
        review.coherent,
        review.double_meaning,
        review.abusive_or_unsafe,
        review.age_appropriate,
        sum(not r.grammar_ok for r in review.pages),
    )

    if review.abusive_or_unsafe:
        report.add("Kind and safe words", "flagged", review.summary)
        return StoryVerdict(story, "reject", report, "unsafe or abusive content")
    report.add("Kind and safe words", "passed")

    if review.double_meaning:
        report.add("No double meanings", "flagged", review.summary)
        return StoryVerdict(story, "rewrite", report, "a phrase with a double meaning")
    report.add("No double meanings", "passed")

    nonsense = [r.number for r in review.pages if not r.makes_sense]
    if not review.coherent or nonsense:
        detail = f"pages {nonsense}" if nonsense else "story doesn't hang together"
        report.add("Makes sense", "flagged", detail)
        return StoryVerdict(story, "rewrite", report, "parts of the story don't make sense")
    report.add("Makes sense", "passed")

    if not review.age_appropriate:
        report.add("Right for the age", "flagged", review.summary)
        return StoryVerdict(story, "rewrite", report, "not right for the child's age")
    report.add("Right for the age", "passed")

    story, fixed_pages = _apply_fixes(story, brief, review)
    still_wrong = [
        r.number for r in review.pages if not r.grammar_ok and r.number not in fixed_pages
    ]
    if fixed_pages:
        report.add("Grammar and spelling", "fixed", f"corrected pages {fixed_pages}")
    elif still_wrong:
        report.add("Grammar and spelling", "flagged", f"pages {still_wrong}")
        return StoryVerdict(story, "rewrite", report, "grammar mistakes that couldn't be fixed")
    else:
        report.add("Grammar and spelling", "passed")

    # Drift between text and illustration notes isn't worth a rewrite on its own: the
    # picture check later confirms each image matches its page.
    note = "" if review.text_matches_scenes else "minor drift between notes and text"
    report.add("Illustration notes match the words", "passed", note)
    return StoryVerdict(story, "show", report)


# ----------------------------------------------------------------------------- images


def image_problem(data: bytes, min_side: int = 256) -> str | None:
    """Return why an image is broken, or None if it looks like a real picture."""
    from PIL import Image, ImageStat

    if not data:
        return "empty file"
    try:
        Image.open(io.BytesIO(data)).verify()  # catches truncated/corrupt files
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:  # PIL raises many types for bad data
        return "can't be opened"
    if min(img.size) < min_side:
        return f"too small ({img.size[0]}x{img.size[1]})"
    gray = img.convert("L").resize((128, 128))
    mean, std = ImageStat.Stat(gray).mean[0], ImageStat.Stat(gray).stddev[0]
    if mean < 12:
        return "almost completely black"
    if mean > 248 and std < 6:
        return "almost completely white"
    if std < 6:
        return "a single flat colour"
    colours = img.convert("RGB").resize((64, 64)).quantize(colors=8).getcolors() or []
    top = max((n for n, _ in colours), default=0)
    if top / (64 * 64) > 0.94:
        return "mostly one colour"
    return None
