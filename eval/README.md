# Kahaani evaluation

Everything writes to `eval/out/` (git-ignored). Free-tier quotas are tiny (~20 Gemini
requests/day per model), so every script that calls an API is resumable and cached:
just re-run it the next day.

Optional heavy deps (torch, open_clip, matplotlib, pandas, nbformat) live in the `eval`
group: `uv sync --group eval`, or prefix commands with `uv run --group eval`.

| Script | What it does | API cost |
|---|---|---|
| `run_stories.py` | 30 briefs → `out/stories.jsonl` | 1-2 LLM calls per story |
| `safety_suite.py` | 61 adversarial / control briefs through schema → rules → (LLM) | 0 (rules), ≤29 with `--llm` |
| `story_judge.py` | LLM-as-judge rubric over the stories | 1 LLM call per story |
| `consistency.py` | character-consistency experiment (4 setups) | images + 1 vision call per page |
| `quality_review.py` | runs the quality reviewer over the stories → `out/quality_review.jsonl` | 1 LLM call per story |
| `report.py` | `out/report.md` + `out/charts/*.png` from whatever exists | 0 |
| `results.ipynb` | runs `report.py` and shows tables and charts | 0 |

## Safety suite

```bash
uv run python -m eval.safety_suite          # schema + rules, instant
uv run python -m eval.safety_suite --llm    # + LLM check on cases that got past the rules
```

`adversarial.jsonl`: 50 cases that must be blocked (violence, horror, adult, prompt injection
incl. Hinglish/Hindi/obfuscated, real people and brand characters, contact info and school
names, bullying, dangerous imitable behaviour, over-long fields, name abuse) and 11 safe
controls (wheelchair, hearing aid, headscarf, patka, "Kumar", "skills", fire trucks, dark
skin, ...) that measure false positives. Cases tagged `needs_llm: true` get past the
schema and rules by design and need the LLM layer; without `--llm` they're reported but
don't fail the run (`--strict` makes them fail). Exit code 1 = an expected-block case got
through every layer that was run. Output: `out/safety.json`.

## Story judge

```bash
uv run python -m eval.story_judge --limit 10        # judge 10 more stories
uv run python -m eval.story_judge --make-hand-sheet # out/hand_scores.csv, 20 blank rows
# ...fill in 1-5 per criterion while reading out/stories.md...
uv run python -m eval.story_judge --agreement       # exact and within-1 agreement per criterion
```

Rubric (1-5): `age_appropriate_language`, `lesson_clear_not_preachy`, `child_is_hero`,
`no_scary_content`, `coherent`. The prompt is `prompts/story_judge.txt`; the story goes in as
escaped JSON data. Output: `out/judge.jsonl`, `out/judge_agreement.json`.

## Character consistency

Four setups over the same stories, each scored against the same hero picture
(`out/images/hero/{id}.png`, made once per story by `Illustrator.hero()`):

| Setup | How pages are drawn |
|---|---|
| `baseline` | "a 5-year-old child, \<appearance\>" + scene, new seed per page, no reference |
| `fixed` | fixed character sentence + one seed per book, text only (`hero=None`) |
| `reference` | the live app: FLUX.2 [klein] with the hero as `input_image_0` |
| `ipadapter` | SDXL + IP-Adapter (scale 0.6) on Kaggle, conditioned on the hero |

```bash
uv run python -m eval.consistency generate --setup fixed --limit 2      # also makes heroes
uv run python -m eval.consistency generate --setup baseline --limit 2
uv run python -m eval.consistency generate --setup reference --limit 2
# ipadapter: run notebooks/ip_adapter_kaggle.ipynb, unzip into eval/out/images/
uv run --group eval python -m eval.consistency score-clip
uv run python -m eval.consistency score-judge --limit 20
uv run python -m eval.consistency make-human-pairs   # out/human_pairs/ → send to raters
uv run python -m eval.consistency score-human out/human_pairs/answers_*.csv
```

- `generate` defaults to 2 stories × 4 pages (Cloudflare's free quota is limited) and skips
  existing files.
- **CLIP** (ViT-B-32, laion2b): cosine of each page vs. the hero, plus mean page-to-page
  similarity. CLIP sees the whole picture, so backgrounds and palette move it too.
- **Vision judge**: Gemini compares hero + page on hair, skin, outfit, glasses and accessories,
  then gives 1-5. Resumable; `--limit` caps calls per run.
- **Humans**: `human_pairs/index.html` opens locally (no server), shows 20 shuffled pairs
  blind to setup, and downloads `answers_<initials>.csv`. The key mapping pairs to setups is
  kept out of the folder, in `out/human_pairs_key.csv`.

Outputs: `out/consistency_{clip,judge,human,gen}.jsonl`.

## Report

```bash
uv run --group eval python -m eval.report    # → out/report.md, out/charts/*.png
```
