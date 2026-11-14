"""Orchestrates every step and reports progress.

Two phases, so the parent can approve the hero before pages are drawn:

    maker = BookMaker.from_settings()
    draft = maker.start(brief, progress)        # safety, story, hero picture
    draft = maker.new_hero(draft)               # optional: try another hero
    book = maker.finish(draft, progress)        # pages, narration, checks, PDF, MP4
    book = maker.redo_page(book, 3, "make it funnier", progress)
"""

import copy
import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from string import Template

from pydantic import ValidationError

from kahaani.config import Settings, get_settings
from kahaani.pipeline import assembler, narrator, planner, reviewer, safety
from kahaani.pipeline.illustrator import Illustrator
from kahaani.pipeline.reviewer import QualityReport
from kahaani.providers.errors import ProviderError
from kahaani.providers.image_base import ImageGen
from kahaani.providers.llm_base import LLM
from kahaani.providers.tts import TTS
from kahaani.schemas import Brief, Page, Story

log = logging.getLogger(__name__)
Progress = Callable[[float, str], None]
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def _quiet(_: float, __: str) -> None:
    pass


class BookError(Exception):
    """Something the parent should be told about, in plain words."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = reasons or []


@dataclass
class Draft:
    brief: Brief
    story: Story
    hero: bytes
    hero_variant: int = 0
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    quality: QualityReport = field(default_factory=QualityReport)
    reuse: str = "none"  # "none" | "story" | "story+pictures"
    template_id: str | None = None
    shared_pages: list[bytes] | None = None  # drawings reused from a template


@dataclass
class Book:
    brief: Brief
    story: Story
    hero: bytes
    hero_variant: int
    pages: list[bytes]  # one image per story page
    audio: list[bytes]  # [cover, page 1..n, end]
    audio_ext: str
    pdf: bytes
    video: bytes | None
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    quality: QualityReport = field(default_factory=QualityReport)
    reuse: str = "none"
    template_id: str | None = None


class _Timer:
    def __init__(self, timings: dict[str, float], name: str):
        self.timings, self.name = timings, name

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, *exc):
        took = time.perf_counter() - self.start
        self.timings[self.name] = round(self.timings.get(self.name, 0) + took, 2)
        log.info("stage=%s secs=%.1f", self.name, took)


class BookMaker:
    def __init__(
        self,
        llm: LLM,
        image_gen: ImageGen,
        tts: TTS,
        vision: LLM | None = None,
        settings: Settings | None = None,
        make_video: bool = True,
        library=None,
    ):
        self.llm = llm
        self.vision = vision
        # Quick yes/no safety checks go to the fast, high-quota models when available.
        self.checker = vision or llm
        self.illustrator = Illustrator(image_gen)
        self.tts = tts
        self.settings = settings or get_settings()
        self.make_video = make_video
        self.library = library  # kahaani.library.Library, for reusing matching stories

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kw) -> "BookMaker":
        from kahaani.cache import DiskCache
        from kahaani.providers.image_factory import build_image_gen
        from kahaani.providers.llm_chain import build_llm, build_vision
        from kahaani.providers.tts import EdgeTTS

        s = settings or get_settings()
        tts_cache = DiskCache(s.cache_dir, "tts") if s.cache_enabled else None
        return cls(
            llm=build_llm(s),
            image_gen=build_image_gen(s),
            tts=EdgeTTS(rate=s.tts_rate, cache=tts_cache),
            vision=build_vision(s),
            settings=s,
            **kw,
        )

    # ------------------------------------------------------------------ phase 1

    def start(
        self, brief: Brief, progress: Progress = _quiet, exclude: set[str] | None = None
    ) -> Draft:
        """`exclude`: template ids not to reuse (for 'write a new version')."""
        timings: dict[str, float] = {}
        progress(0.02, "Checking the details")
        with _Timer(timings, "input_safety"):
            result = self._call(lambda: safety.check_brief(brief, self.checker))
        if not result.ok:
            raise BookError("Some details need changing.", result.reasons)

        quality = QualityReport()
        quality.add("Request is a genuine description", "passed")

        reused = self._try_reuse(brief, exclude, quality, progress)
        if reused:
            reused.timings = {**timings, **reused.timings}
            return reused

        with _Timer(timings, "story"):
            story = self._plan_reviewed_story(brief, quality, progress)

        progress(0.6, "Drawing the hero")
        with _Timer(timings, "hero"):
            hero, variant = self._healthy_hero(brief, story, 0, quality)
        progress(1.0, "Hero ready")
        return Draft(brief, story, hero, variant, timings=timings, quality=quality)

    def _try_reuse(
        self, brief: Brief, exclude: set[str] | None, quality: QualityReport, progress: Progress
    ) -> Draft | None:
        if self.library is None:
            return None
        progress(0.15, "Looking for a matching story")
        try:
            match = self.library.find(brief, exclude)
            reused = self.library.reuse(match, brief) if match else None
        except ProviderError:
            log.warning("shared library unavailable; writing a new story")
            return None
        if not reused:
            return None
        story, report = reused
        for c in report.checks:
            quality.add(c.name, c.status, c.detail)
        tid = match.template["id"]
        if match.pictures:
            progress(0.6, "Using matching pictures")
            hero, pages = self.library.pictures(match.template)
            log.info("reused story and pictures from a shared template")
            return Draft(
                brief,
                story,
                hero,
                0,
                quality=quality,
                reuse="story+pictures",
                template_id=tid,
                shared_pages=pages,
            )
        progress(0.6, "Drawing the hero")
        hero, variant = self._healthy_hero(brief, story, 0, quality)
        log.info("reused story from a shared template")
        return Draft(brief, story, hero, variant, quality=quality, reuse="story", template_id=tid)

    def new_hero(self, draft: Draft) -> Draft:
        with _Timer(draft.timings, "hero"):
            hero, variant = self._healthy_hero(
                draft.brief, draft.story, draft.hero_variant + 1, draft.quality
            )
        # A new hero means new drawings too, so shared pictures no longer apply.
        reuse = "story" if draft.reuse != "none" else "none"
        return replace(draft, hero=hero, hero_variant=variant, shared_pages=None, reuse=reuse)

    def _healthy_hero(
        self, brief: Brief, story: Story, variant: int, quality: QualityReport
    ) -> tuple[bytes, int]:
        """Draw the hero; if the image comes back broken, try one more variant."""
        for v in (variant, variant + 1):
            hero = self._call(lambda v=v: self.illustrator.hero(brief, story, v))
            problem = reviewer.image_problem(hero)
            if problem is None:
                quality.add("Hero picture is a real picture", "passed" if v == variant else "fixed")
                return hero, v
            log.warning("hero image broken (%s); redrawing", problem)
        raise BookError("The hero picture didn't come out right. Please try again.")

    def _plan_reviewed_story(
        self, brief: Brief, quality: QualityReport, progress: Progress = _quiet
    ) -> Story:
        """Write, safety-check and quality-review the story; rewrite once if needed."""
        last_reason = ""
        for attempt in range(2):
            progress(0.15 + 0.15 * attempt, "Writing the story")
            try:
                story = self._call(lambda v=attempt: planner.plan_story(brief, self.llm, variant=v))
            except planner.StoryPlanningError as e:
                raise BookError(
                    "We couldn't write a good story this time. Please try again."
                ) from e
            verdict = self._call(lambda s=story: safety.check_story(s, self.checker))
            if not verdict.ok:
                log.warning("story failed output safety check (attempt %d)", attempt + 1)
                last_reason = "safety"
                continue
            progress(0.4 + 0.1 * attempt, "Reviewing the story")
            review = self._call(lambda s=story: reviewer.review_story(s, brief, self.checker))
            for check in review.report.checks:
                quality.add(check.name, check.status, check.detail)
            if review.decision == "show":
                quality.add("Story passed the safety check", "passed")
                return review.story
            log.warning("story review: %s (%s)", review.decision, review.reason)
            last_reason = review.reason
        if last_reason == "safety":
            raise BookError(
                "We couldn't write a story that passed our safety checks. Please try again."
            )
        raise BookError(f"Our quality check stopped this story ({last_reason}). Please try again.")

    # ------------------------------------------------------------------ phase 2

    def finish(self, draft: Draft, progress: Progress = _quiet) -> Book:
        brief, story, timings = draft.brief, draft.story, dict(draft.timings)
        warnings = list(draft.warnings)
        quality = copy.deepcopy(draft.quality)
        n = len(story.pages)

        # Narration runs in the background while pages are drawn.
        with ThreadPoolExecutor(max_workers=1) as bg:
            started = time.perf_counter()
            audio_job = bg.submit(narrator.narrate, brief, story, self.tts)

            images: list[bytes] = list(draft.shared_pages or [])
            with _Timer(timings, "pages"):
                for i, page in enumerate(story.pages[len(images) :], start=len(images)):
                    progress(0.05 + 0.6 * i / n, f"Drawing page {i + 1} of {n}")
                    images.append(
                        self._call(
                            lambda p=page: self.illustrator.page(
                                brief, story, p, hero=draft.hero, variant=draft.hero_variant
                            )
                        )
                    )

            if draft.shared_pages:
                quality.add("Pictures reused from a checked book", "passed")
            else:
                progress(0.68, "Checking the pictures")
                with _Timer(timings, "image_safety"):
                    images, img_warnings = self._check_and_fix_images(draft, images, quality)
                warnings += img_warnings

            progress(0.78, "Recording the voice")
            try:
                audio = audio_job.result()
            except ProviderError as e:
                raise BookError("The narration service isn't responding. Please try again.") from e
            timings["narration"] = round(time.perf_counter() - started, 2)

        book = Book(
            brief,
            story,
            draft.hero,
            draft.hero_variant,
            images,
            audio,
            self.tts.ext,
            b"",
            None,
            warnings,
            timings,
            quality,
            draft.reuse,
            draft.template_id,
        )
        return self._assemble(book, progress)

    def _redraw(self, draft: Draft | Book, story: Story, index: int) -> bytes:
        return self._call(
            lambda: self.illustrator.page(
                draft.brief,
                story,
                story.pages[index],
                hero=draft.hero,
                variant=draft.hero_variant,
                retry=1,
            )
        )

    def _check_and_fix_images(
        self, draft: Draft, images: list[bytes], quality: QualityReport
    ) -> tuple[list[bytes], list[str]]:
        """Code check for broken files, then one vision check; redraw once, else fall back
        to the hero picture. Every outcome is recorded in the quality report."""
        images, warnings = list(images), []
        story = draft.story

        # 1. Broken files: can't open, tiny, blank, black, one flat colour.
        broken = [i for i, img in enumerate(images) if reviewer.image_problem(img)]
        for i in broken:
            img = self._redraw(draft, story, i)
            if reviewer.image_problem(img) is None:
                images[i] = img
            else:
                images[i] = draft.hero
                warnings.append(
                    f"Page {i + 1}'s picture didn't come out right, so the hero picture is "
                    "shown instead."
                )
        quality.add(
            "Pictures open and look like pictures",
            "fixed" if broken else "passed",
            f"redrew page {', '.join(str(i + 1) for i in broken)}" if broken else "",
        )

        # 2. Vision check: safe, no writing, no distortion, matches the page.
        descriptions = ["the hero's reference portrait"] + [p.scene for p in story.pages]
        checks = safety.check_images([draft.hero, *images], self.vision, descriptions)
        if checks is None:
            if self.settings.require_image_check:
                raise BookError(
                    "Our picture safety check is unavailable right now. Please try later."
                )
            quality.add("Pictures checked by AI", "skipped", "vision model unavailable")
            warnings.append(
                "The pictures couldn't be checked automatically this time. "
                "Please look through them before sharing."
            )
            return images, warnings
        if not checks[0].safe:
            raise BookError(
                "The hero picture didn't pass our safety check. Please try another hero."
            )

        first = checks[1:]
        bad = [i for i, c in enumerate(first) if not c.ok]
        if bad:
            log.info("redrawing %d pages after image check", len(bad))
            redrawn = {i: self._redraw(draft, story, i) for i in bad}
            second = safety.check_images(
                list(redrawn.values()), self.vision, [story.pages[i].scene for i in redrawn]
            )
            for n, (i, img) in enumerate(redrawn.items()):
                check = second[n] if second else None
                ok_to_use = (
                    check.safe and not check.malformed if check else first[i].safe
                ) and reviewer.image_problem(img) is None
                if ok_to_use:
                    images[i] = img
                    if check and check.has_text:
                        warnings.append(f"Page {i + 1}'s picture may contain some stray lettering.")
                else:
                    # Keep the words; show the hero picture instead.
                    images[i] = draft.hero
                    warnings.append(
                        f"Page {i + 1}'s picture was replaced because it didn't pass our "
                        "picture check."
                    )

        def record(name: str, failed: list[int]) -> None:
            pages = ", ".join(str(i + 1) for i in failed)
            quality.add(
                name, "fixed" if failed else "passed", f"redrew page {pages}" if failed else ""
            )

        record("Pictures are safe for children", [i for i, c in enumerate(first) if not c.safe])
        record("No writing in the pictures", [i for i, c in enumerate(first) if c.has_text])
        record("No distorted bodies or faces", [i for i, c in enumerate(first) if c.malformed])
        record("Pictures match the story", [i for i, c in enumerate(first) if not c.matches_scene])
        return images, warnings

    def _assemble(self, book: Book, progress: Progress) -> Book:
        progress(0.85, "Making the book")
        with _Timer(book.timings, "pdf"):
            pdf = assembler.build_pdf(
                assembler.render_html(book.brief, book.story, book.hero, book.pages)
            )
        video = None
        if self.make_video:
            progress(0.9, "Making the video")
            with _Timer(book.timings, "video"):
                frames = assembler.pdf_to_images(pdf)
                video = assembler.build_video(frames, book.audio, book.audio_ext)
        progress(1.0, "Done")
        return replace(book, pdf=pdf, video=video)

    # ------------------------------------------------------------------ redo

    def redo_page(self, book: Book, number: int, request: str, progress: Progress = _quiet) -> Book:
        if not 1 <= number <= len(book.story.pages):
            raise BookError("That page doesn't exist.")
        request = " ".join(request.split())[:200]
        progress(0.05, "Checking your request")
        if request:
            verdict = self._call(lambda: safety.check_instruction(request, self.checker))
            if not verdict.ok:
                raise BookError("That request can't be used.", verdict.reasons)

        progress(0.15, f"Rewriting page {number}")
        new_page = self._rewrite_page(book, number, request)
        pages = list(book.story.pages)
        pages[number - 1] = new_page
        story = book.story.model_copy(update={"pages": pages})
        verdict = self._call(lambda: safety.check_story(story, self.checker))
        if not verdict.ok:
            raise BookError(
                "The new page didn't pass our safety check. Please try another request."
            )
        progress(0.25, "Reviewing the new page")
        review = self._call(lambda: reviewer.review_story(story, book.brief, self.checker))
        if review.decision != "show":
            raise BookError(
                f"The new page didn't pass our quality check ({review.reason}). "
                "Please try another request."
            )
        story = review.story  # may carry grammar fixes
        new_page = story.pages[number - 1]
        quality = copy.deepcopy(book.quality)
        for check in review.report.checks:
            quality.add(check.name, check.status, check.detail)

        progress(0.35, f"Drawing page {number}")
        image = self._call(
            lambda: self.illustrator.page(
                book.brief, story, new_page, hero=book.hero, variant=book.hero_variant
            )
        )
        checks = safety.check_images([image], self.vision, [new_page.scene])
        if reviewer.image_problem(image) or (checks and not checks[0].ok):
            image = self._redraw(book, story, number - 1)
            if reviewer.image_problem(image) or (
                (again := safety.check_images([image], self.vision, [new_page.scene]))
                and not again[0].safe
            ):
                image = book.hero
        images = list(book.pages)
        images[number - 1] = image

        progress(0.6, "Recording the voice")
        audio = list(book.audio)
        audio[number] = self._call(lambda: self.tts.synthesize(new_page.text, book.brief.language))
        updated = replace(book, story=story, pages=images, audio=audio, quality=quality)
        return self._assemble(updated, progress)

    def _rewrite_page(self, book: Book, number: int, request: str) -> Page:
        brief = book.brief
        template = Template((PROMPTS / "redo_page.txt").read_text("utf-8"))
        context = {
            "title": book.story.title,
            "pages": [{"number": p.number, "text": p.text} for p in book.story.pages],
        }
        prompt = template.substitute(
            hero_name=book.story.hero_name,
            story_json=json.dumps(context, ensure_ascii=False, indent=1),
            number=number,
            request_json=json.dumps(
                {"request": request or "Write a fresh version of this page."}, ensure_ascii=False
            ).replace("<", "\\u003c"),
            language_rules=planner.LANGUAGE_RULES[brief.language],
            age=brief.age,
            age_rules=planner._age_rules_text(brief.age, brief.taste),
        )
        system = (PROMPTS / "planner_system.txt").read_text("utf-8")
        problems: list[str] = []
        for _ in range(2):
            raw = self._call(lambda p=prompt: self.llm.generate_json(p, Page, system=system))
            try:
                page = Page.model_validate({**raw, "number": number})
            except ValidationError:
                problems = ["The page JSON was malformed."]
                continue
            pages = list(book.story.pages)
            pages[number - 1] = page
            trial = book.story.model_copy(update={"pages": pages})
            problems = [
                p
                for p in planner.validate_story(trial, brief)
                if p.startswith(f"Page {number} ") or f"page {number} " in p
            ]
            if not problems:
                return planner._anonymise_scenes(trial, brief).pages[number - 1]
            prompt += "\n\nPROBLEMS WITH YOUR LAST ANSWER\n" + "\n".join(f"- {p}" for p in problems)
        raise BookError("We couldn't rewrite that page. Please try a different request.")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _call(fn):
        try:
            return fn()
        except ProviderError as e:
            log.warning("provider error: %s", e)
            raise BookError(
                "Our free AI services are busy or out of today's quota. "
                "Please try again later, or look at the sample books."
            ) from e


def main() -> None:
    """Make a full book from the command line.

    uv run python -m kahaani.pipeline.create_book --lang hi --age 5 --out out/
    uv run python -m kahaani.pipeline.create_book --brief eval/briefs.jsonl --id b07
    """
    import argparse

    p = argparse.ArgumentParser(description="Make a complete storybook (PDF + MP4).")
    p.add_argument("--lang", choices=["en", "hi"], default="en")
    p.add_argument("--age", type=int, default=5)
    p.add_argument("--pages", type=int, choices=[4, 8], default=4)
    p.add_argument("--style", choices=["watercolour", "cartoon", "folk"], default="watercolour")
    p.add_argument("--brief", type=Path, help="JSON or JSONL file with briefs")
    p.add_argument("--id", help="which brief id to use from a JSONL file")
    p.add_argument("--out", type=Path, default=Path("out"))
    p.add_argument("--no-video", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("weasyprint", "fontTools", "httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.brief:
        text = args.brief.read_text("utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        row = next((r for r in rows if r.get("id") == args.id), rows[0])
        row.pop("id", None)
        brief = Brief.model_validate(row)
    else:
        brief = Brief(
            child_name="Meera",
            age=args.age,
            appearance="curly black hair, brown skin, round red glasses",
            favourites="elephants, mangoes",
            lesson="sharing",
            language=args.lang,
            style=args.style,
            pages=args.pages,
        )

    maker = BookMaker.from_settings(make_video=not args.no_video)
    say = lambda f, m: print(f"[{f:4.0%}] {m}", flush=True)  # noqa: E731
    try:
        book = maker.finish(maker.start(brief, say), say)
    except BookError as e:
        print("Could not make the book:", e, *e.reasons, sep="\n- ")
        raise SystemExit(1) from e

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "book.pdf").write_bytes(book.pdf)
    if book.video:
        (args.out / "book.mp4").write_bytes(book.video)
    (args.out / "hero.png").write_bytes(book.hero)
    (args.out / "story.json").write_text(book.story.model_dump_json(indent=2), "utf-8")
    print(f"\nSaved to {args.out}/  timings: {book.timings}")
    for w in book.warnings:
        print("warning:", w)


if __name__ == "__main__":
    main()
