"""Pre-made sample books, shown when the free quotas run out.

Build them (uses real APIs; ~4 books):
    uv run python -m kahaani.samples b01 b07 b15 b30

Each sample is a folder in samples/: book.pdf, book.mp4, cover.jpg, meta.json.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@dataclass
class Sample:
    title: str
    blurb: str
    cover: Path
    pdf: Path
    video: Path | None


def load_samples(root: Path = SAMPLES) -> list[Sample]:
    out = []
    for d in sorted(p for p in root.glob("*") if p.is_dir()):
        try:
            meta = json.loads((d / "meta.json").read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if not (d / "book.pdf").exists():
            continue
        video = d / "book.mp4"
        out.append(
            Sample(
                title=meta["title"],
                blurb=meta.get("blurb", ""),
                cover=d / "cover.jpg",
                pdf=d / "book.pdf",
                video=video if video.exists() else None,
            )
        )
    return out


def main(ids: list[str]) -> None:
    import io
    import logging

    from PIL import Image

    from kahaani.pipeline.create_book import BookMaker
    from kahaani.schemas import Brief

    logging.basicConfig(level=logging.WARNING)
    rows = {}
    for line in (SAMPLES.parent / "eval" / "briefs.jsonl").read_text("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row.pop("id")] = row
    maker = BookMaker.from_settings()
    for bid in ids:
        brief = Brief.model_validate(rows[bid])
        print(f"making sample {bid} ...", flush=True)
        book = maker.finish(maker.start(brief))
        d = SAMPLES / bid
        d.mkdir(parents=True, exist_ok=True)
        (d / "book.pdf").write_bytes(book.pdf)
        if book.video:
            (d / "book.mp4").write_bytes(book.video)
        Image.open(io.BytesIO(book.hero)).convert("RGB").save(d / "cover.jpg", quality=88)
        lang = {"hi": "Hindi", "en": "English"}[brief.language]
        style = {"folk": "Indian folk art"}.get(brief.style, brief.style)
        meta = {
            "title": book.story.title,
            "blurb": f"{lang}, for a {brief.age}-year-old. About {brief.lesson_text}, in {style}.",
        }
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        print(f"  saved {d} ({', '.join(book.warnings) or 'no warnings'})")


if __name__ == "__main__":
    main(sys.argv[1:] or ["b01", "b07", "b15", "b30"])
