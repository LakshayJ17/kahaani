"""Consistency experiment plumbing with fake image models and embeddings (no torch)."""

import csv
import io

from PIL import Image

from eval import consistency as c
from kahaani.providers.image_base import ImageGen
from kahaani.schemas import Brief, Story
from tests.fakes import FakeLLM, story_dict


class FakeGen(ImageGen):
    name = "fakegen"

    def __init__(self, uses_reference=False):
        super().__init__("fake")
        self.uses_reference = uses_reference
        self.calls = []

    def _generate(self, prompt, seed, ref, size):
        self.calls.append({"prompt": prompt, "seed": seed, "ref": ref})
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (seed or 0) % 255).save(buf, "PNG")
        return buf.getvalue()


def _stories():
    brief = Brief(
        child_name="Meera",
        age=5,
        appearance="curly hair",
        favourites="mangoes",
        lesson="sharing",
        language="en",
        style="cartoon",
    )
    return [("b01", brief, Story.model_validate(story_dict()))]


def test_generate_setups_share_one_hero(tmp_path):
    stories = _stories()
    fixed, base, ref = FakeGen(), FakeGen(), FakeGen(uses_reference=True)
    c.GEN_FILE = tmp_path / "gen.jsonl"
    assert c.generate("fixed", fixed, stories, root=tmp_path, max_pages=2) == 3  # hero + 2
    assert c.generate("baseline", base, stories, root=tmp_path, max_pages=2) == 2
    assert c.generate("reference", ref, stories, root=tmp_path, max_pages=2) == 2
    assert c.generate("fixed", fixed, stories, root=tmp_path, max_pages=2) == 0  # skips existing
    assert (tmp_path / "hero" / "b01.png").exists()
    assert {x["seed"] for x in fixed.calls[1:]} == {fixed.calls[1]["seed"]}  # one seed per book
    assert len({x["seed"] for x in base.calls}) == 2  # new seed per page
    assert all(x["ref"] is None for x in fixed.calls + base.calls)
    assert all(x["ref"] == (tmp_path / "hero" / "b01.png").read_bytes() for x in ref.calls)
    assert "outfit" not in base.calls[0]["prompt"].lower()
    assert c.setups_present(tmp_path) == ["baseline", "fixed", "reference"]


def _png(path, colour):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), colour).save(path)


def _fake_images(root):
    _png(root / "hero" / "b01.png", "red")
    for setup in ("baseline", "fixed", "reference", "ipadapter"):
        for n in (1, 2, 10):
            _png(root / setup / "b01" / f"p{n}.png", "red" if setup != "baseline" else "blue")


def fake_embed(paths):
    return [[1.0, 0.0] if Image.open(p).getpixel((0, 0))[0] > 128 else [0.6, 0.8] for p in paths]


def test_clip_scores_with_fake_embedder(tmp_path):
    _fake_images(tmp_path)
    rows = {r["setup"]: r for r in c.clip_scores(fake_embed, tmp_path)}
    assert set(rows) == {"baseline", "fixed", "reference", "ipadapter"}
    assert rows["fixed"]["ref_sim_mean"] == 1.0
    assert rows["baseline"]["ref_sim_mean"] == 0.6
    assert rows["baseline"]["pairwise_mean"] == 1.0
    assert c.page_files(tmp_path / "fixed" / "b01")[-1].name == "p10.png"


def test_judge_pages_resumes(tmp_path):
    _fake_images(tmp_path)
    out = tmp_path / "judge.jsonl"
    verdict = {
        "hair": "same",
        "skin": "same",
        "outfit": "different",
        "glasses": "not_visible",
        "accessories": "same",
        "score": 4,
        "reason": "outfit colour differs",
    }
    llm = FakeLLM([verdict] * 5)
    assert c.judge_pages(llm, tmp_path, out, limit=5) == 5
    assert len(llm.images) == 2  # reference + page
    llm2 = FakeLLM([verdict] * 20)
    assert c.judge_pages(llm2, tmp_path, out, limit=50) == 7  # 12 pages total


def test_human_pairs_roundtrip(tmp_path):
    _fake_images(tmp_path)
    pairs_dir, key = tmp_path / "pairs", tmp_path / "key.csv"
    assert c.make_human_pairs(tmp_path, pairs_dir, key, n=5) == 5
    html = (pairs_dir / "index.html").read_text()
    assert "Download answers CSV" in html and "pair01" in html
    assert "baseline" not in html  # raters stay blind to the setup
    with open(pairs_dir / "pairs.csv", newline="") as f:
        pairs = list(csv.DictReader(f))
    assert all(p["answer"] == "" for p in pairs)
    answers = tmp_path / "answers_x.csv"
    answers.write_text("pair,answer,rater\npair01,yes,x\npair02,no,x\npair03,unsure,x\n")
    rows = c.score_human([answers], key)
    assert len(rows) == 2
    summary = c.human_summary(rows)
    assert sum(s["n"] for s in summary.values()) == 2
