"""Step 6: narration, one audio clip for the cover and one per page."""

from concurrent.futures import ThreadPoolExecutor

from kahaani.providers.tts import TTS
from kahaani.schemas import Brief, Story


def cover_line(brief: Brief, story: Story) -> str:
    if brief.language == "hi":
        return f"{story.title}। {story.hero_name} के लिए एक कहानी।"
    return f"{story.title}. A story for {story.hero_name}."


def end_line(brief: Brief) -> str:
    return "समाप्त।" if brief.language == "hi" else "The End."


def narrate(brief: Brief, story: Story, tts: TTS) -> list[bytes]:
    """[cover, page 1..n, end]. Runs the network calls in parallel."""
    lines = [cover_line(brief, story), *(p.text for p in story.pages), end_line(brief)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda t: tts.synthesize(t, brief.language), lines))
