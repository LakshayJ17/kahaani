"""Character-consistency experiment: does the hero look the same on every page?

Four setups, same briefs and stories (eval/out/stories.jsonl):

  baseline   per page, a free-form description ("a 5-year-old child, <appearance>") with
             no fixed outfit or companion, a different seed on every page, no reference.
  fixed      fixed character sentence + one seed per book, text only: `Illustrator.page`
             with hero=None (forces the text-only `page_prompt` path even on FLUX.2).
  reference  the live app: `Illustrator.page` with hero=<hero image> on FLUX.2 [klein]
             (Cloudflare `input_image_0`, `reference_page_prompt`).
  ipadapter  SDXL + IP-Adapter conditioned on the same hero image; made on a free GPU by
             notebooks/ip_adapter_kaggle.ipynb and copied into eval/out/images/ipadapter/.

The hero image is made ONCE per story with `Illustrator.hero()` and saved to
eval/out/images/hero/{id}.png. It is the REFERENCE for scoring every setup (and the
conditioning image for `reference` and `ipadapter`), so all scores answer the same
question: "how close are this setup's pages to this one picture of the child?". Baseline
and fixed never see it while drawing, which is exactly what the comparison measures.

Pages live in eval/out/images/{setup}/{id}/p1.png, p2.png, ... Any other folder there
(e.g. the notebook's ipadapter_s0.4 sweep) is scored as an extra setup.

    uv run python -m eval.consistency generate --setup fixed --limit 2
    uv run python -m eval.consistency generate --setup baseline --limit 2
    uv run python -m eval.consistency generate --setup reference --limit 2
    uv run --group eval python -m eval.consistency score-clip
    uv run python -m eval.consistency score-judge --limit 20
    uv run python -m eval.consistency make-human-pairs
    uv run python -m eval.consistency score-human [answers.csv ...]

Metrics:
  score-clip   open_clip ViT-B-32 (laion2b) cosine similarity of each page to the hero
               reference, plus the mean pairwise page-to-page similarity. CLIP embeds the
               whole picture, so it also reacts to backgrounds, palette and composition,
               not just the child; treat it as a rough signal next to the judge and humans.
  score-judge  Gemini vision sees reference + page and scores "same character?" 1-5 on
               hair / skin / outfit / glasses / accessories. Resumable; ~1 request per page.
  human        20 shuffled (reference, page) pairs, blind to setup, answered yes/no in a
               local HTML form.

Writes eval/out/consistency_clip.jsonl, consistency_judge.jsonl, consistency_human.jsonl
and consistency_gen.jsonl (generation timings). torch/open_clip are imported lazily, so
this module works without the eval dependency group except for score-clip.
"""

import argparse
import csv
import hashlib
import io
import json
import logging
import math
import random
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from itertools import combinations
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from eval.common import OUT, PROMPTS, append_jsonl, load_stories, read_jsonl, write_jsonl
from kahaani.pipeline.illustrator import NO_TEXT, STYLE_PREFIXES, Illustrator
from kahaani.providers.errors import ProviderError
from kahaani.providers.image_base import ImageGen
from kahaani.providers.llm_base import LLM
from kahaani.schemas import Brief, Page, Story

log = logging.getLogger(__name__)

IMAGES = OUT / "images"
MAIN_SETUPS = ("baseline", "fixed", "reference", "ipadapter")
GEN_SETUPS = ("baseline", "fixed", "reference")
HERO_DIR = "hero"
CLIP_FILE = OUT / "consistency_clip.jsonl"
JUDGE_FILE = OUT / "consistency_judge.jsonl"
HUMAN_FILE = OUT / "consistency_human.jsonl"
GEN_FILE = OUT / "consistency_gen.jsonl"
PAIRS_DIR = OUT / "human_pairs"
PAIRS_KEY = OUT / "human_pairs_key.csv"  # kept outside the folder sent to raters


# ---------- paths ----------


def reference_path(story_id: str, root: Path = IMAGES) -> Path:
    """The shared hero image: scoring reference for every setup."""
    return root / HERO_DIR / f"{story_id}.png"


def page_files(folder: Path) -> list[Path]:
    """p1.png, p2.png, ... sorted by page number."""
    return sorted(
        folder.glob("p*.png"), key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0
    )


def setups_present(root: Path = IMAGES) -> list[str]:
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != HERO_DIR)


def scored_items(root: Path = IMAGES) -> list[tuple[str, str, Path, list[Path]]]:
    """(setup, id, reference, pages) for every story folder that has a reference."""
    items = []
    for setup in setups_present(root):
        for folder in sorted(p for p in (root / setup).iterdir() if p.is_dir()):
            ref = reference_path(folder.name, root)
            pages = page_files(folder)
            if ref.exists() and pages:
                items.append((setup, folder.name, ref, pages))
    return items


# ---------- generation ----------


def baseline_prompt(brief: Brief, page: Page) -> str:
    """No fixed character sheet: just age + the parent's free-text appearance."""
    parts = [
        STYLE_PREFIXES[brief.style],
        f"A {brief.age}-year-old child, {brief.appearance.rstrip('. ')}",
        f"Scene: {page.scene.rstrip('. ')}",
        f"Mood: {page.mood}",
        f"Children's book illustration, soft lighting, {NO_TEXT}",
    ]
    return ". ".join(parts) + "."


def baseline_seed(story_id: str, page_number: int) -> int:
    """A different (but reproducible, so cacheable) seed for every page."""
    h = hashlib.sha256(f"baseline|{story_id}|{page_number}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 2_147_483_647


def to_png(data: bytes) -> bytes:
    from PIL import Image

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data
    buf = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def _save(path: Path, make: Callable[[], bytes], setup: str, story_id: str) -> bytes:
    start = time.perf_counter()
    data = to_png(make())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    secs = round(time.perf_counter() - start, 2)
    append_jsonl(GEN_FILE, {"setup": setup, "id": story_id, "file": path.name, "secs": secs})
    return data


def page_maker(
    setup: str,
    illustrator: Illustrator,
    story_id: str,
    brief: Brief,
    story: Story,
    page: Page,
    hero: bytes,
) -> Callable[[], bytes]:
    """A no-argument function that draws one page the way `setup` does."""
    if setup == "baseline":
        return lambda: illustrator.gen.generate(
            baseline_prompt(brief, page), seed=baseline_seed(story_id, page.number)
        )
    if setup == "fixed":
        return lambda: illustrator.page(brief, story, page, hero=None)
    if setup == "reference":
        if not illustrator.gen.uses_reference:
            raise ValueError("the 'reference' setup needs an image model that takes a reference")
        return lambda: illustrator.page(brief, story, page, hero=hero)
    raise ValueError(f"cannot generate setup {setup!r}")


def generate(
    setup: str,
    gen: ImageGen,
    stories: Sequence[tuple[str, Brief, Story]],
    root: Path = IMAGES,
    max_pages: int | None = None,
) -> int:
    """Write missing images (hero first, then pages) for `stories`. Returns images made."""
    made = 0
    illustrator = Illustrator(gen)
    for story_id, brief, story in stories:
        hero_file = reference_path(story_id, root)
        if hero_file.exists():
            hero = hero_file.read_bytes()
        else:
            hero = _save(
                hero_file, lambda b=brief, s=story: illustrator.hero(b, s), HERO_DIR, story_id
            )
            made += 1
        pages = story.pages[:max_pages] if max_pages else story.pages
        for page in pages:
            out = root / setup / story_id / f"p{page.number}.png"
            if not out.exists():
                make = page_maker(setup, illustrator, story_id, brief, story, page, hero)
                _save(out, make, setup, story_id)
                made += 1
        print(f"{setup} {story_id}: done", flush=True)
    return made


# ---------- CLIP ----------

Embedder = Callable[[list[Path]], list[list[float]]]


def make_clip_embedder() -> Embedder:
    import open_clip
    import torch
    from PIL import Image

    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k"
    )
    model.eval()

    def embed(paths: list[Path]) -> list[list[float]]:
        batch = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in paths])
        with torch.no_grad():
            feats = model.encode_image(batch)
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.tolist()

    return embed


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def clip_scores(embed: Embedder, root: Path = IMAGES) -> list[dict]:
    rows = []
    ref_cache: dict[Path, list[float]] = {}
    for setup, story_id, ref, pages in scored_items(root):
        if ref not in ref_cache:
            ref_cache[ref] = embed([ref])[0]
        vecs = embed(pages)
        ref_sims = [round(cosine(ref_cache[ref], v), 4) for v in vecs]
        pair_sims = [cosine(a, b) for a, b in combinations(vecs, 2)]
        rows.append(
            {
                "setup": setup,
                "id": story_id,
                "n_pages": len(pages),
                "ref_sims": ref_sims,
                "ref_sim_mean": round(sum(ref_sims) / len(ref_sims), 4),
                "pairwise_mean": round(sum(pair_sims) / len(pair_sims), 4) if pair_sims else None,
            }
        )
    return rows


# ---------- vision judge ----------

Match = Literal["same", "different", "not_visible"]


class SameCharacter(BaseModel):
    hair: Match
    skin: Match
    outfit: Match
    glasses: Match
    accessories: Match
    score: int = Field(ge=1, le=5)
    reason: str


def _small_jpeg(path: Path, size: int = 512) -> bytes:
    """Downscale before sending: fewer image tokens, same verdict."""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def judge_pages(vision: LLM, root: Path = IMAGES, out: Path = JUDGE_FILE, limit: int = 20) -> int:
    """Score pages not yet in `out`; stops after `limit` new verdicts or a quota error."""
    done = {(r["setup"], r["id"], r["page"]) for r in read_jsonl(out)}
    prompt = (PROMPTS / "consistency_judge.txt").read_text("utf-8")
    n = 0
    for setup, story_id, ref, pages in scored_items(root):
        for page in pages:
            if n >= limit:
                return n
            if (setup, story_id, page.stem) in done:
                continue
            try:
                raw = vision.generate_json(
                    prompt,
                    SameCharacter,
                    temperature=0.0,
                    images=[_small_jpeg(ref), _small_jpeg(page)],
                )
                verdict = SameCharacter.model_validate(raw)
            except ProviderError as e:
                log.warning("judge stopped: %s", type(e).__name__)
                return n
            except ValidationError:
                log.warning("invalid verdict for %s/%s/%s", setup, story_id, page.stem)
                continue
            row = {"setup": setup, "id": story_id, "page": page.stem} | verdict.model_dump()
            append_jsonl(out, row)
            n += 1
            print(f"{setup} {story_id} {page.stem}: {verdict.score}", flush=True)
    return n


# ---------- human pairs ----------

HTML = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Same Child?</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 16px;
  background: #fcfcfb; color: #0b0b0b; }
.pair { border-top: 1px solid #ddd; padding: 16px 0; }
.imgs { display: flex; gap: 12px; flex-wrap: wrap; }
.imgs figure { margin: 0; flex: 1 1 260px; }
.imgs img { width: 100%; height: auto; border-radius: 6px; }
figcaption { font-size: 14px; color: #52514e; }
label { margin-right: 16px; font-size: 18px; }
button { font-size: 18px; padding: 10px 18px; margin: 16px 0; }
</style></head><body>
<h1>Is it the same child?</h1>
<p>For each pair, look at the main child only (ignore background, other characters and
small style changes). Is the child on the right the same child as on the left?</p>
<p><label>Your initials: <input id="rater" size="6"></label></p>
<div id="pairs"></div>
<button onclick="download()">Download answers CSV</button>
<p id="status"></p>
<script>
const PAIRS = $pairs_json;
const box = document.getElementById("pairs");
for (const p of PAIRS) {
  const div = document.createElement("div");
  div.className = "pair";
  div.innerHTML = `<h3>Pair $${p.pair}</h3>
    <div class="imgs">
      <figure><img src="$${p.ref_image}" alt="reference"><figcaption>Reference</figcaption></figure>
      <figure><img src="$${p.page_image}" alt="page"><figcaption>Page</figcaption></figure>
    </div>
    <p><label><input type="radio" name="$${p.pair}" value="yes"> Yes, same child</label>
       <label><input type="radio" name="$${p.pair}" value="no"> No</label>
       <label><input type="radio" name="$${p.pair}" value="unsure"> Can't tell</label></p>`;
  box.appendChild(div);
}
function download() {
  const rater = (document.getElementById("rater").value || "anon").replace(/[^\\w-]/g, "");
  const lines = ["pair,answer,rater"];
  let missing = 0;
  for (const p of PAIRS) {
    const sel = document.querySelector(`input[name="$${p.pair}"]:checked`);
    if (!sel) missing++;
    lines.push(`$${p.pair},$${sel ? sel.value : ""},$${rater}`);
  }
  const blob = new Blob([lines.join("\\n") + "\\n"], {type: "text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `answers_$${rater}.csv`;
  a.click();
  document.getElementById("status").textContent =
    missing ? `Saved. $${missing} pairs left unanswered.` : "Saved. Thank you!";
}
</script></body></html>
""")


def make_human_pairs(
    root: Path = IMAGES,
    out_dir: Path = PAIRS_DIR,
    key_file: Path = PAIRS_KEY,
    n: int = 20,
    seed: int = 7,
) -> int:
    """Copy n shuffled (reference, page) pairs, blind to setup, plus a CSV and an HTML form."""
    candidates = [
        (setup, story_id, ref, page)
        for setup, story_id, ref, pages in scored_items(root)
        if setup in MAIN_SETUPS
        for page in pages
    ]
    rng = random.Random(seed)
    picked = rng.sample(candidates, min(n, len(candidates)))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "images").mkdir(parents=True)
    pairs, key = [], []
    for i, (setup, story_id, ref, page) in enumerate(picked, 1):
        name = f"pair{i:02d}"
        ref_rel, page_rel = f"images/{name}_ref.png", f"images/{name}_page.png"
        shutil.copy(ref, out_dir / ref_rel)
        shutil.copy(page, out_dir / page_rel)
        pairs.append({"pair": name, "ref_image": ref_rel, "page_image": page_rel, "answer": ""})
        key.append({"pair": name, "setup": setup, "id": story_id, "page": page.stem})
    _write_csv(out_dir / "pairs.csv", pairs, ["pair", "ref_image", "page_image", "answer"])
    _write_csv(key_file, key, ["pair", "setup", "id", "page"])
    html = HTML.substitute(pairs_json=json.dumps(pairs))
    (out_dir / "index.html").write_text(html, "utf-8")
    return len(pairs)


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def score_human(answer_files: list[Path], key_file: Path = PAIRS_KEY) -> list[dict]:
    """Join raters' answers with the hidden key. 'unsure' and blank answers are dropped."""
    with open(key_file, newline="", encoding="utf-8") as f:
        key = {r["pair"]: r for r in csv.DictReader(f)}
    rows = []
    for path in answer_files:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                answer = (r.get("answer") or "").strip().lower()
                if answer not in ("yes", "no") or r["pair"] not in key:
                    continue
                k = key[r["pair"]]
                rater = (r.get("rater") or path.stem).strip()
                rows.append(
                    {
                        "rater": rater,
                        "pair": r["pair"],
                        "setup": k["setup"],
                        "id": k["id"],
                        "page": k["page"],
                        "same": answer == "yes",
                    }
                )
    return rows


def human_summary(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r["setup"], {"n": 0, "yes": 0})
        s["n"] += 1
        s["yes"] += r["same"]
    for s in out.values():
        s["yes_pct"] = round(100 * s["yes"] / s["n"], 1)
    return out


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Character-consistency experiment")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--setup", choices=GEN_SETUPS, required=True)
    g.add_argument("--limit", type=int, default=2, help="number of stories (default 2)")
    g.add_argument("--max-pages", type=int, default=4)
    sub.add_parser("score-clip")
    j = sub.add_parser("score-judge")
    j.add_argument("--limit", type=int, default=20, help="max new vision calls (default 20)")
    h = sub.add_parser("make-human-pairs")
    h.add_argument("-n", type=int, default=20)
    sh = sub.add_parser("score-human")
    sh.add_argument("answers", nargs="*", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "generate":
        from kahaani.providers.image_factory import build_image_gen

        stories = load_stories()[: args.limit]
        made = generate(args.setup, build_image_gen(), stories, max_pages=args.max_pages)
        print(f"made {made} images under {IMAGES / args.setup}")
    elif args.cmd == "score-clip":
        rows = clip_scores(make_clip_embedder())
        write_jsonl(CLIP_FILE, rows)
        print(f"scored {len(rows)} story folders -> {CLIP_FILE}")
    elif args.cmd == "score-judge":
        from kahaani.providers.llm_chain import build_vision

        vision = build_vision()
        if vision is None:
            print("no vision model configured (needs GEMINI_API_KEY)")
            return 1
        print(f"judged {judge_pages(vision, limit=args.limit)} new pages -> {JUDGE_FILE}")
    elif args.cmd == "make-human-pairs":
        n = make_human_pairs(n=args.n)
        print(f"wrote {n} pairs; send {PAIRS_DIR} to raters (open index.html)")
    elif args.cmd == "score-human":
        files = args.answers or sorted(PAIRS_DIR.glob("answers*.csv"))
        rows = score_human(files)
        write_jsonl(HUMAN_FILE, rows)
        for setup, s in human_summary(rows).items():
            print(f"{setup}: {s['yes']}/{s['n']} judged same ({s['yes_pct']}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
