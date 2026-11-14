"""Collect every eval result that exists into eval/out/report.md (+ PNG charts).

    uv run --group eval python -m eval.report      # with charts (needs matplotlib)
    uv run python -m eval.report                   # tables only if matplotlib is missing

Missing result files are skipped, so this runs at any stage of the evaluation.
"""

import json
import statistics
import sys
from pathlib import Path

from eval.common import OUT, read_jsonl
from eval.story_judge import CRITERIA

SETUP_ORDER = ["baseline", "fixed", "reference", "ipadapter"]
BLUE, SURFACE, INK, INK2, GRID = "#2a78d6", "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 3) if xs else None


def _fmt(x) -> str:
    return "–" if x is None else str(x)


def _setup_key(s: str) -> tuple[int, str]:
    return (SETUP_ORDER.index(s) if s in SETUP_ORDER else len(SETUP_ORDER), s)


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows]
    return out + [""]


# ---------- sections: each returns (markdown lines, chart data or None) ----------


def consistency_section(out: Path) -> tuple[list[str], dict]:
    clip = read_jsonl(out / "consistency_clip.jsonl")
    judge = read_jsonl(out / "consistency_judge.jsonl")
    human = read_jsonl(out / "consistency_human.jsonl")
    if not (clip or judge or human):
        return [], {}
    setups = sorted({r["setup"] for r in clip + judge + human}, key=_setup_key)
    rows, charts = [], {"clip": {}, "judge": {}}
    for s in setups:
        c = [r for r in clip if r["setup"] == s]
        j = [r["score"] for r in judge if r["setup"] == s]
        h = [r["same"] for r in human if r["setup"] == s]
        ref = _mean([x for r in c for x in r["ref_sims"]])
        pair = _mean([r["pairwise_mean"] for r in c if r["pairwise_mean"] is not None])
        jm = _mean(j)
        rows.append(
            [
                s,
                len(c),
                ref,
                pair,
                len(j),
                jm,
                round(100 * sum(x >= 4 for x in j) / len(j), 1) if j else None,
                len(h),
                round(100 * sum(h) / len(h), 1) if h else None,
            ]
        )
        if ref is not None:
            charts["clip"][s] = ref
        if jm is not None:
            charts["judge"][s] = jm
    lines = ["## Character consistency", ""]
    lines += [
        "Reference for every setup = the shared hero image (images/hero/{id}.png). CLIP also "
        "reacts to backgrounds, so read it next to the judge and human columns.",
        "",
    ]
    lines += _table(
        [
            "Setup",
            "Stories (CLIP)",
            "CLIP page↔ref",
            "CLIP page↔page",
            "Pages judged",
            "Judge mean (1-5)",
            "Judge ≥4 %",
            "Human pairs",
            "Human 'same' %",
        ],
        rows,
    )
    return lines, charts


def story_judge_section(out: Path) -> tuple[list[str], dict]:
    judge = read_jsonl(out / "judge.jsonl")
    if not judge:
        return [], {}
    avgs = {c: _mean([r[c] for r in judge]) for c in CRITERIA}
    lines = ["## Story quality (LLM judge)", "", f"{len(judge)} stories judged.", ""]
    lines += _table(["Criterion", "Mean (1-5)"], [[c, v] for c, v in avgs.items()])
    agree_file = out / "judge_agreement.json"
    if agree_file.exists():
        agree = json.loads(agree_file.read_text("utf-8"))
        lines += ["Judge vs hand scores:", ""]
        lines += _table(
            ["Criterion", "n", "Exact %", "Within 1 %"],
            [[c, a["n"], a["exact"], a["within1"]] for c, a in agree.items()],
        )
    return lines, avgs


def safety_section(out: Path) -> tuple[list[str], dict]:
    f = out / "safety.json"
    if not f.exists():
        return [], {}
    s = json.loads(f.read_text("utf-8"))["summary"]
    layers = s["blocked_by_layer"]
    lines = ["## Safety suite", ""]
    lines += _table(
        ["Expected-block cases", "Schema", "Rules", "LLM", "Blocked", "Missed", "False positives"],
        [
            [
                s["expect_block"],
                layers.get("schema", 0),
                layers.get("rules", 0),
                layers.get("llm", 0) if s["llm_run"] else "not run",
                s["blocked"],
                len(s["missed"]),
                f"{len(s['false_positives'])}/{s['expect_allow']}",
            ]
        ],
    )
    if s["missed"]:
        lines += [f"Missed: {', '.join(s['missed'])}", ""]
    shown = ("schema", "rules", "llm") if s["llm_run"] else ("schema", "rules")
    chart = {k: layers.get(k, 0) for k in shown}
    chart["missed"] = len(s["missed"])
    return lines, chart


def story_runs_section(out: Path) -> list[str]:
    runs = [("run1", out / "run1" / "stories.jsonl"), ("run2", out / "run2" / "stories.jsonl")]
    runs.append(("latest", out / "stories.jsonl"))
    rows = []
    for name, path in runs:
        data = read_jsonl(path)
        if not data:
            continue
        ok = [r for r in data if r.get("status") == "ok"]
        secs = [r["secs"] for r in data if r.get("secs") is not None]
        rows.append(
            [
                name,
                f"{len(ok)}/{len(data)}",
                sum(r.get("attempts") == 1 for r in ok),
                round(statistics.median(secs), 1) if secs else None,
            ]
        )
    if not rows:
        return []
    return ["## Story generation runs", ""] + _table(
        ["Run", "Valid", "First try", "Median secs"], rows
    )


def timing_section(out: Path) -> list[str]:
    gen = read_jsonl(out / "consistency_gen.jsonl")
    stories = [r["secs"] for r in read_jsonl(out / "stories.jsonl") if r.get("secs") is not None]
    rows = []
    if stories:
        rows.append(["story (LLM)", len(stories), *_median_p90(stories)])
    for s in sorted({r["setup"] for r in gen}, key=_setup_key):
        secs = [r["secs"] for r in gen if r["setup"] == s]
        rows.append([f"image ({s})", len(secs), *_median_p90(secs)])
    if not rows:
        return []
    return ["## Timing", ""] + _table(["Step", "n", "Median secs", "p90 secs"], rows)


def _median_p90(xs: list[float]) -> list[float]:
    xs = sorted(xs)
    return [round(statistics.median(xs), 1), round(xs[min(len(xs) - 1, int(0.9 * len(xs)))], 1)]


# ---------- charts ----------


def bar_chart(data: dict[str, float], title: str, ylabel: str, path: Path, ymax=None) -> bool:
    """One series, so one colour and no legend; values labelled on the bars."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    labels, values = list(data), list(data.values())
    bars = ax.bar(labels, values, color=BLUE, width=0.55, zorder=2)
    ax.bar_label(bars, labels=[f"{v:g}" for v in values], padding=3, color=INK, fontsize=9)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    if ymax:
        ax.set_ylim(0, ymax)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    plt.setp(
        ax.get_xticklabels(),
        rotation=20 if len(labels) > 4 else 0,
        ha="right" if len(labels) > 4 else "center",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return True


# ---------- main ----------


def build_report(out: Path = OUT, charts: bool = True) -> str:
    lines = ["# Kahaani evaluation report", ""]
    chart_dir = out / "charts"
    made: list[str] = []

    cons_lines, cons = consistency_section(out)
    story_lines, story_avgs = story_judge_section(out)
    safety_lines, safety = safety_section(out)
    if charts:
        specs = [
            ("consistency_clip.png", cons.get("clip"), "CLIP similarity to hero", "cosine", None),
            ("consistency_judge.png", cons.get("judge"), "Vision judge: same child?", "1-5", 5),
            ("story_judge.png", story_avgs, "Story judge averages", "1-5", 5),
            ("safety.png", safety, "Expected-block cases by layer", "cases", None),
        ]
        for name, data, title, ylabel, ymax in specs:
            if data and bar_chart(data, title, ylabel, chart_dir / name, ymax):
                made.append(name)

    for section in (
        cons_lines,
        story_lines,
        safety_lines,
        story_runs_section(out),
        timing_section(out),
    ):
        lines += section
    if len(lines) == 2:
        lines += ["No results yet. See eval/README.md for how to produce them.", ""]
    if made:
        lines += ["## Charts", ""] + [f"![{m}](charts/{m})" for m in made] + [""]
    text = "\n".join(lines)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(text, "utf-8")
    return text


def main() -> int:
    build_report()
    print(f"wrote {OUT / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
