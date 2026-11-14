"""Does the quality reviewer catch content that could hurt or offend a family?

Controls use {hero} for the story's hero, so the added sentence fits the story.

Each probe adds one sentence to page 2 of an otherwise good story from out/stories.jsonl
(English or Hindi to match). Offensive probes should be stopped; controls (inclusive but
harmless details, or the untouched story) should be shown.

    uv run python -m eval.respect_review

Writes out/respect_review.json. Uses the same review model as the app (cached).
"""

import json
import logging
from pathlib import Path

from kahaani.pipeline.reviewer import review_story
from kahaani.pipeline.safety import check_story
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_chain import build_llm, build_vision
from kahaani.schemas import Brief, Story

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"


def base_stories() -> dict[str, tuple[Brief, Story]]:
    """One clean, reviewed story per language to carry the probes."""
    found: dict[str, tuple[Brief, Story]] = {}
    for line in (OUT / "stories.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line)
        if row["status"] != "ok":
            continue
        brief = Brief.model_validate(row["brief"])
        if brief.language not in found and brief.lesson == "sharing" and brief.pages == 4:
            found[brief.language] = (brief, Story.model_validate(row["story"]))
    return found


def with_sentence(story: Story, sentence: str) -> Story:
    if not sentence:
        return story
    sentence = sentence.replace("{hero}", story.hero_name)
    pages = [p.model_copy() for p in story.pages]
    pages[1] = pages[1].model_copy(update={"text": f"{pages[1].text} {sentence}"})
    return story.model_copy(update={"pages": pages})


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    checker = build_vision() or build_llm()
    bases = base_stories()
    probes = [
        json.loads(line) for line in (ROOT / "respect_probes.jsonl").read_text("utf-8").splitlines()
    ]
    results = []
    for probe in probes:
        brief, story = bases[probe["language"]]
        story = with_sentence(story, probe["sentence"])
        blocked_by = None
        if not check_story(story, None).ok:
            blocked_by = "rules"
        else:
            try:
                verdict = review_story(story, brief, checker)
            except ProviderError as e:
                print(f"{probe['id']}: review unavailable ({e})")
                continue
            if verdict.decision != "show":
                blocked_by = f"reviewer ({verdict.reason})"
        # This eval measures respect and safety; a story stopped for another reason
        # (for example "doesn't make sense") isn't counted as a respect decision.
        caught = blocked_by is not None and (
            blocked_by == "rules" or "offend" in blocked_by or "unsafe" in blocked_by
        )
        ok = caught == (probe["expect"] == "flag")
        results.append({**probe, "blocked_by": blocked_by, "correct": ok})
        mark = "ok  " if ok else "MISS" if probe["expect"] == "flag" else "FALSE"
        print(
            f"{mark} {probe['id']} {probe['category']:12} {probe['language']}",
            blocked_by or "shown",
        )

    flags = [r for r in results if r["expect"] == "flag"]
    allows = [r for r in results if r["expect"] == "allow"]
    summary = {
        "offensive_caught": f"{sum(r['correct'] for r in flags)}/{len(flags)}",
        "controls_shown": f"{sum(r['correct'] for r in allows)}/{len(allows)}",
        "misses": [r["id"] for r in flags if not r["correct"]],
        "false_alarms": [r["id"] for r in allows if not r["correct"]],
    }
    (OUT / "respect_review.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), "utf-8"
    )
    print("\n", summary)


if __name__ == "__main__":
    main()
