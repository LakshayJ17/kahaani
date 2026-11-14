"""LLM-as-judge for the generated stories in eval/out/stories.jsonl.

    uv run python -m eval.story_judge --limit 5          # judge up to 5 new stories
    uv run python -m eval.story_judge --make-hand-sheet  # blank CSV for a human to score
    uv run python -m eval.story_judge --agreement        # compare hand scores vs judge

Results go to eval/out/judge.jsonl. Already-judged ids are skipped, and LLM responses
are cached on disk, so re-running after a quota error just continues where it stopped.
The hand sheet (eval/out/hand_scores.csv) lists 20 stories; read them in
eval/out/stories.md and fill in 1-5 for each criterion.
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from string import Template

from pydantic import BaseModel, Field, ValidationError

from eval.common import OUT, PROMPTS, append_jsonl, read_jsonl
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_base import LLM

log = logging.getLogger(__name__)

CRITERIA = [
    "age_appropriate_language",
    "lesson_clear_not_preachy",
    "child_is_hero",
    "no_scary_content",
    "coherent",
]
JUDGE_FILE = OUT / "judge.jsonl"
HAND_FILE = OUT / "hand_scores.csv"
HAND_SHEET_SIZE = 20


class StoryVerdict(BaseModel):
    age_appropriate_language: int = Field(ge=1, le=5)
    lesson_clear_not_preachy: int = Field(ge=1, le=5)
    child_is_hero: int = Field(ge=1, le=5)
    no_scary_content: int = Field(ge=1, le=5)
    coherent: int = Field(ge=1, le=5)
    comment: str


def judge_prompt(row: dict) -> str:
    brief, story = row["brief"], row["story"]
    data = {
        "title": story["title"],
        "hero_name": story["hero_name"],
        "pages": [p["text"] for p in story["pages"]],
    }
    # Escape "<" so the story text can't close the <story> block.
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    lesson = brief.get("custom_lesson") or brief["lesson"]
    template = Template((PROMPTS / "story_judge.txt").read_text("utf-8"))
    return template.substitute(
        age=brief["age"], language=brief["language"], lesson=lesson, story_json=payload
    )


def judge_story(llm: LLM, row: dict) -> dict:
    raw = llm.generate_json(judge_prompt(row), StoryVerdict, temperature=0.0)
    verdict = StoryVerdict.model_validate(raw)
    return {"id": row["id"], "model": getattr(llm, "last_used", None) or llm.model} | (
        verdict.model_dump()
    )


def judge_all(llm: LLM, rows: list[dict], out: Path = JUDGE_FILE, limit: int | None = None):
    """Judge stories not yet in `out`, appending as we go. Returns the number judged."""
    done = {r["id"] for r in read_jsonl(out)}
    todo = [r for r in rows if r.get("status") == "ok" and r["id"] not in done]
    if limit is not None:
        todo = todo[:limit]
    n = 0
    for row in todo:
        try:
            result = judge_story(llm, row)
        except ProviderError as e:
            log.warning("judge stopped at %s: %s", row["id"], type(e).__name__)
            break
        except ValidationError:
            log.warning("judge returned an invalid verdict for %s, skipping", row["id"])
            continue
        append_jsonl(out, result)
        n += 1
        print(f"{row['id']} judged", flush=True)
    return n


def make_hand_sheet(rows: list[dict], path: Path = HAND_FILE, n: int = HAND_SHEET_SIZE) -> int:
    ok = [r for r in rows if r.get("status") == "ok"][:n]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "language", "age", "lesson", *CRITERIA, "notes"])
        for r in ok:
            b = r["brief"]
            lesson = b.get("custom_lesson") or b["lesson"]
            w.writerow(
                [r["id"], r["story"]["title"], b["language"], b["age"], lesson]
                + [""] * (len(CRITERIA) + 1)
            )
    return len(ok)


def read_hand_scores(path: Path = HAND_FILE) -> dict[str, dict[str, int]]:
    """id -> {criterion: score} for filled-in cells only."""
    out: dict[str, dict[str, int]] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scores = {c: int(row[c]) for c in CRITERIA if (row.get(c) or "").strip().isdigit()}
            if scores:
                out[row["id"]] = scores
    return out


def agreement(hand: dict[str, dict[str, int]], judge: list[dict]) -> dict:
    """Per criterion: number of pairs, exact agreement %, within-1 agreement %."""
    by_id = {r["id"]: r for r in judge}
    result = {}
    all_diffs: list[int] = []
    for c in CRITERIA:
        diffs = [
            abs(scores[c] - by_id[i][c])
            for i, scores in hand.items()
            if c in scores and i in by_id and c in by_id[i]
        ]
        all_diffs += diffs
        result[c] = _agree(diffs)
    result["overall"] = _agree(all_diffs)
    return result


def _agree(diffs: list[int]) -> dict:
    n = len(diffs)
    if not n:
        return {"n": 0, "exact": None, "within1": None}
    return {
        "n": n,
        "exact": round(100 * sum(d == 0 for d in diffs) / n, 1),
        "within1": round(100 * sum(d <= 1 for d in diffs) / n, 1),
    }


def averages(judge: list[dict]) -> dict[str, float]:
    return {c: round(sum(r[c] for r in judge) / len(judge), 2) for c in CRITERIA if judge}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="judge at most N new stories")
    ap.add_argument("--make-hand-sheet", action="store_true")
    ap.add_argument("--agreement", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite an existing hand sheet")
    args = ap.parse_args(argv)
    rows = read_jsonl(OUT / "stories.jsonl")

    if args.make_hand_sheet:
        if HAND_FILE.exists() and not args.force:
            print(f"{HAND_FILE} exists; use --force to overwrite")
            return 1
        print(f"wrote {make_hand_sheet(rows)} rows to {HAND_FILE}")
        return 0
    if args.agreement:
        result = agreement(read_hand_scores(), read_jsonl(JUDGE_FILE))
        (OUT / "judge_agreement.json").write_text(json.dumps(result, indent=2), "utf-8")
        print("| Criterion | n | Exact % | Within 1 % |\n|---|---|---|---|")
        for c, a in result.items():
            print(f"| {c} | {a['n']} | {a['exact']} | {a['within1']} |")
        return 0

    from kahaani.providers.llm_chain import build_llm

    n = judge_all(build_llm(), rows, limit=args.limit)
    print(f"judged {n} new stories; averages: {averages(read_jsonl(JUDGE_FILE))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
