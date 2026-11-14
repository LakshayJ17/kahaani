"""Run the quality reviewer over the eval stories and summarise what it flags.

    uv run python -m eval.quality_review            # all stories in out/stories.jsonl
    uv run python -m eval.quality_review --limit 5

Writes out/quality_review.jsonl. Uses the same checker models as the app (cached).
"""

import argparse
import collections
import json
import logging
from pathlib import Path

from kahaani.pipeline.reviewer import review_story
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_chain import build_llm, build_vision
from kahaani.schemas import Brief, Story

OUT = Path(__file__).resolve().parent / "out"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)

    checker = build_vision() or build_llm()
    rows = [json.loads(line) for line in (OUT / "stories.jsonl").read_text("utf-8").splitlines()]
    rows = [r for r in rows if r["status"] == "ok"][: args.limit or None]
    results, decisions, flags = [], collections.Counter(), collections.Counter()
    for r in rows:
        brief, story = Brief.model_validate(r["brief"]), Story.model_validate(r["story"])
        try:
            v = review_story(story, brief, checker)
        except ProviderError as e:
            print(f"{r['id']}: review unavailable ({e})")
            continue
        decisions[v.decision] += 1
        for c in v.report.checks:
            if c.status in ("fixed", "flagged"):
                flags[f"{c.name}: {c.status}"] += 1
        changed = [
            {"page": a.number, "before": a.text, "after": b.text}
            for a, b in zip(story.pages, v.story.pages, strict=True)
            if a.text != b.text
        ]
        results.append(
            {
                "id": r["id"],
                "language": brief.language,
                "decision": v.decision,
                "reason": v.reason,
                "checks": v.report.as_list(),
                "fixes": changed,
            }
        )
        print(
            f"{r['id']} ({brief.language}): {v.decision}{' - ' + v.reason if v.reason else ''}"
            f"{f', fixed {len(changed)} page(s)' if changed else ''}",
            flush=True,
        )

    with open(OUT / "quality_review.jsonl", "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("\nDecisions:", dict(decisions))
    for name, n in flags.most_common():
        print(f"  {n:2d}  {name}")


if __name__ == "__main__":
    main()
