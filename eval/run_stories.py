"""Generate a story for every brief in eval/briefs.jsonl and save results.

    uv run python -m eval.run_stories            # all briefs
    uv run python -m eval.run_stories b03 b17    # just these

Writes eval/out/stories.jsonl (one row per brief) and eval/out/stories.md (for reading).
Responses are cached, so re-running only calls the API for new or changed prompts.
"""

import json
import logging
import sys
import time
from pathlib import Path

from kahaani.pipeline.planner import StoryPlanningError, plan_story_with_stats
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_chain import build_llm
from kahaani.schemas import Brief

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"


def load_briefs(only: set[str] | None = None) -> list[tuple[str, Brief]]:
    rows = []
    for line in (ROOT / "briefs.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            bid = data.pop("id")
            if not only or bid in only:
                rows.append((bid, Brief.model_validate(data)))
    return rows


def to_markdown(rows: list[dict]) -> str:
    out = ["# Eval stories\n"]
    for r in rows:
        b = r["brief"]
        head = f"## {r['id']}: age {b['age']}, {b['language']}, {b['lesson']}, {b['pages']}p"
        out.append(head)
        out.append(
            f"_{r['status']}, attempts: {r['attempts']}, {r['secs']}s, by {r.get('provider')}_\n"
        )
        if r["status"] != "ok":
            out.append("Problems: " + "; ".join(r["problems"]) + "\n")
            continue
        s = r["story"]
        out.append(
            f"**{s['title']}**  \nCharacter: {s['character']['description']}  \n"
            f"Outfit: {s['character']['outfit']}  \n"
            f"Companion: {s['character']['companion']}\n"
        )
        for p in s["pages"]:
            out.append(f"{p['number']}. ({p['mood']}) {p['text']}  \n   _scene: {p['scene']}_")
        out.append("")
    return "\n".join(out)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    only = set(sys.argv[1:]) or None
    llm = build_llm()
    OUT.mkdir(exist_ok=True)
    rows = []
    for bid, brief in load_briefs(only):
        start = time.perf_counter()
        row = {"id": bid, "brief": brief.model_dump()}
        try:
            story, history = plan_story_with_stats(brief, llm)
            row |= {"status": "ok", "story": story.model_dump(), "problems": []}
        except StoryPlanningError as e:
            history = e.history
            row |= {"status": "invalid", "problems": e.problems}
        except ProviderError as e:
            history = []
            row |= {"status": "error", "problems": [str(e)]}
        row |= {
            "provider": getattr(llm, "last_used", None),
            "attempts": len(history),
            "first_try_problems": history[0] if history else [],
            "secs": round(time.perf_counter() - start, 1),
        }
        rows.append(row)
        print(
            f"{bid} {row['status']:8} attempts={row['attempts']} {row['secs']}s {row['provider']}",
            flush=True,
        )

    with open(OUT / "stories.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "stories.md").write_text(to_markdown(rows), "utf-8")

    ok = sum(r["status"] == "ok" for r in rows)
    first = sum(r["status"] == "ok" and r["attempts"] == 1 for r in rows)
    print(f"\n{ok}/{len(rows)} valid, {first} on first try. See eval/out/stories.md")


if __name__ == "__main__":
    main()
