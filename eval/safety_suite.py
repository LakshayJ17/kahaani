"""Run the adversarial briefs in eval/adversarial.jsonl through the safety layers.

    uv run python -m eval.safety_suite            # schema + rules only (free, instant)
    uv run python -m eval.safety_suite --llm      # also the LLM check (uses Gemini quota)
    uv run python -m eval.safety_suite --strict   # without --llm, still fail on needs_llm misses

Layers, in the same order as the app:
  1. schema: `Brief` validation (lengths, letters-only name, custom lesson rules)
  2. rules:  `check_text_rules` (blocklists, injection, contact info, public figures)
  3. llm:    `check_brief` with an LLM, only for cases that passed 1 and 2 (saves quota)

Writes eval/out/safety.json and prints markdown tables. Exits 1 if an expected-block case
passes every layer that was run. Cases tagged `needs_llm: true` are ones only an LLM can
catch; without --llm they are reported but don't fail the run (unless --strict).
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from eval.common import OUT, ROOT, read_jsonl
from kahaani.pipeline.safety import _free_text, check_brief, check_text_rules
from kahaani.providers.errors import ProviderError
from kahaani.providers.llm_base import LLM
from kahaani.schemas import Brief

CASES = ROOT / "adversarial.jsonl"
META_KEYS = {"id", "category", "expect", "needs_llm", "note"}


def load_cases(path: Path = CASES) -> list[dict]:
    return read_jsonl(path)


def brief_fields(case: dict) -> dict:
    return {k: v for k, v in case.items() if k not in META_KEYS}


def evaluate_case(case: dict, llm: LLM | None = None) -> dict:
    """Which layer (if any) blocks this case. `llm` None = LLM layer not run."""
    res = {
        "id": case["id"],
        "category": case["category"],
        "expect": case["expect"],
        "needs_llm": bool(case.get("needs_llm")),
        "schema_blocked": False,
        "rules_blocked": False,
        "llm_blocked": None,  # None = not run
        "llm_error": None,
        "blocked_by": None,
    }
    try:
        brief = Brief.model_validate(brief_fields(case))
    except ValidationError:
        res["schema_blocked"] = True
        res["blocked_by"] = "schema"
        return res
    if check_text_rules(_free_text(brief)):
        res["rules_blocked"] = True
        res["blocked_by"] = "rules"
        return res
    if llm is not None:
        try:
            verdict = check_brief(brief, llm)
            res["llm_blocked"] = not verdict.ok
            if not verdict.ok:
                res["blocked_by"] = "llm"
        except (ProviderError, ValueError) as e:
            res["llm_error"] = type(e).__name__
    return res


def summarize(results: list[dict], llm_run: bool) -> dict:
    block = [r for r in results if r["expect"] == "block"]
    allow = [r for r in results if r["expect"] == "allow"]
    misses = [r for r in block if r["blocked_by"] is None]
    return {
        "llm_run": llm_run,
        "cases": len(results),
        "expect_block": len(block),
        "expect_allow": len(allow),
        "blocked_by_layer": dict(Counter(r["blocked_by"] for r in block if r["blocked_by"])),
        "blocked": len(block) - len(misses),
        "missed": [r["id"] for r in misses],
        "missed_needs_llm": [r["id"] for r in misses if r["needs_llm"]],
        "missed_unexpected": [r["id"] for r in misses if not r["needs_llm"] or llm_run],
        "false_positives": [r["id"] for r in allow if r["blocked_by"]],
        "needs_llm_total": sum(r["needs_llm"] for r in block),
        "llm_errors": [r["id"] for r in results if r["llm_error"]],
    }


def by_category(results: list[dict]) -> dict[str, dict]:
    cats: dict[str, dict] = {}
    for r in results:
        c = cats.setdefault(
            r["category"],
            {"expect": r["expect"], "n": 0, "schema": 0, "rules": 0, "llm": 0, "passed": 0},
        )
        c["n"] += 1
        c[r["blocked_by"] or "passed"] += 1
    return cats


def markdown(summary: dict, results: list[dict]) -> str:
    s = summary
    layers = s["blocked_by_layer"]
    llm_cell = str(layers.get("llm", 0)) if s["llm_run"] else "not run"
    lines = [
        "| Layer | Expected-block cases blocked |",
        "|---|---|",
        f"| schema | {layers.get('schema', 0)} |",
        f"| rules | {layers.get('rules', 0)} |",
        f"| llm | {llm_cell} |",
        f"| **total** | **{s['blocked']}/{s['expect_block']}** |",
        "",
        f"Missed: {len(s['missed'])} ({len(s['missed_needs_llm'])} tagged needs_llm). "
        f"False positives: {len(s['false_positives'])}/{s['expect_allow']} safe controls.",
        "",
        "| Category | Expect | n | schema | rules | llm | passed |",
        "|---|---|---|---|---|---|---|",
    ]
    for cat, c in by_category(results).items():
        lines.append(
            f"| {cat} | {c['expect']} | {c['n']} | {c['schema']} | {c['rules']} | "
            f"{c['llm']} | {c['passed']} |"
        )
    if s["missed"]:
        lines += ["", "Missed ids: " + ", ".join(s["missed"])]
    if s["false_positives"]:
        lines += ["False-positive ids: " + ", ".join(s["false_positives"])]
    return "\n".join(lines)


def run(cases: list[dict], llm: LLM | None) -> tuple[dict, list[dict]]:
    results = [evaluate_case(c, llm) for c in cases]
    return summarize(results, llm is not None), results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--llm", action="store_true", help="also run the LLM layer (uses quota)")
    ap.add_argument("--strict", action="store_true", help="fail on needs_llm misses too")
    ap.add_argument("--cases", type=Path, default=CASES)
    args = ap.parse_args(argv)

    llm = None
    if args.llm:
        from kahaani.providers.llm_chain import build_llm, build_vision

        llm = build_vision() or build_llm()

    summary, results = run(load_cases(args.cases), llm)
    OUT.mkdir(exist_ok=True)
    (OUT / "safety.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), "utf-8"
    )
    print(markdown(summary, results))
    failing = summary["missed"] if args.strict else summary["missed_unexpected"]
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
