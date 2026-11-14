"""Offensive and manipulative *requests*: form details and "change this page" wishes.

Each case goes through the same checks as the app (rules, then the AI classifier). Offensive
or manipulative requests should be blocked; ordinary ones (festivals, a hijab, "make it
funnier") should be allowed.

    uv run python -m eval.request_probes

Writes out/request_probes.json.
"""

import json
import logging
from pathlib import Path

from kahaani.pipeline.safety import check_brief, check_instruction
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_chain import build_llm, build_vision
from kahaani.schemas import Brief

ROOT = Path(__file__).resolve().parent
BASE = dict(
    child_name="Meera",
    age=5,
    hero="girl",
    appearance="curly hair",
    favourites="elephants",
    lesson="sharing",
    language="en",
    style="cartoon",
)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    checker = build_vision() or build_llm()
    cases = [
        json.loads(line) for line in (ROOT / "request_probes.jsonl").read_text("utf-8").splitlines()
    ]
    results = []
    for case in cases:
        try:
            if case["kind"] == "form":
                verdict = check_brief(Brief(**{**BASE, **case["change"]}), checker)
            else:
                verdict = check_instruction(case["request"], checker)
        except ProviderError as e:
            print(f"{case['id']}: check unavailable ({e})")
            continue
        blocked = not verdict.ok
        correct = blocked == (case["expect"] == "block")
        results.append({**case, "blocked": blocked, "correct": correct})
        text = case.get("request") or list(case["change"].values())[-1]
        print(
            f"{'ok  ' if correct else 'WRONG'} {case['id']} {case['kind']:4} "
            f"{'blocked' if blocked else 'allowed'} | {text}"
        )
    blocks = [r for r in results if r["expect"] == "block"]
    allows = [r for r in results if r["expect"] == "allow"]
    summary = {
        "offensive_blocked": f"{sum(r['correct'] for r in blocks)}/{len(blocks)}",
        "ordinary_allowed": f"{sum(r['correct'] for r in allows)}/{len(allows)}",
        "wrong": [r["id"] for r in results if not r["correct"]],
    }
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    (out / "request_probes.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), "utf-8"
    )
    print("\n", summary)


if __name__ == "__main__":
    main()
