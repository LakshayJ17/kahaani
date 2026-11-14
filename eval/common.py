"""Small helpers shared by the eval scripts (paths, JSONL in/out, loading stories)."""

import json
from collections.abc import Iterable
from pathlib import Path

from kahaani.schemas import Brief, Story

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
PROMPTS = ROOT / "prompts"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_stories(path: Path | None = None) -> list[tuple[str, Brief, Story]]:
    """(id, brief, story) for every row of stories.jsonl with status 'ok'."""
    rows = read_jsonl(path or OUT / "stories.jsonl")
    return [
        (r["id"], Brief.model_validate(r["brief"]), Story.model_validate(r["story"]))
        for r in rows
        if r.get("status") == "ok"
    ]
