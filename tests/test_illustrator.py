from kahaani.pipeline.illustrator import Illustrator, book_seed, hero_prompt, page_prompt
from kahaani.providers.image_placeholder import PlaceholderImageGen
from kahaani.schemas import Brief, Story
from tests.fakes import story_dict

BRIEF = Brief(
    child_name="Meera",
    age=5,
    appearance="curls",
    favourites="cats",
    lesson="sharing",
    language="en",
    style="folk",
)


def story() -> Story:
    return Story.model_validate(story_dict())


def test_every_page_prompt_has_identical_character_and_style():
    s = story()
    prompts = [page_prompt(BRIEF, s, p) for p in s.pages]
    char = "a 5-year-old Indian girl, curly black hair, round red glasses, wearing yellow kurta"
    assert all(char in p for p in prompts)
    assert all(p.startswith("Indian folk art") for p in prompts)
    assert all("no text" in p for p in prompts)
    assert all("Meera" not in p for p in prompts)


def test_hero_prompt_is_reference_style():
    p = hero_prompt(BRIEF, story())
    assert "Full body" in p and "plain light background" in p and "small grey baby elephant" in p


def test_seed_fixed_per_book_and_changes_with_variant():
    s = story()
    assert book_seed(s) == book_seed(story())
    assert book_seed(s, 1) != book_seed(s)


class RecordingGen(PlaceholderImageGen):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _generate(self, prompt, seed, ref, size):
        self.calls.append((prompt, seed, ref))
        return super()._generate(prompt, seed, ref, size)


def test_pages_share_seed_and_no_reference_for_flux_like_models():
    gen = RecordingGen()
    ill, s = Illustrator(gen), story()
    hero = ill.hero(BRIEF, s)
    for p in s.pages:
        ill.page(BRIEF, s, p, hero=hero)
    seeds = {seed for _, seed, _ in gen.calls}
    assert len(seeds) == 1
    assert all(ref is None for _, _, ref in gen.calls)


def test_retry_changes_seed_and_adds_no_writing_hint():
    gen = RecordingGen()
    ill, s = Illustrator(gen), story()
    ill.page(BRIEF, s, s.pages[0], hero=None)
    ill.page(BRIEF, s, s.pages[0], hero=None, retry=1)
    (p1, s1, _), (p2, s2, _) = gen.calls
    assert s1 != s2 and "Absolutely no writing" in p2
