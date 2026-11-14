"""A child's taste, learned from how their family reacts to books.

Signals:
- explicit: "Loved it / It was okay / Not for us" plus optional tags (fixed list below);
- implicit: re-reading a book (strong like), finishing it (mild like), abandoning it halfway
  for days (mild dislike).

Newer signals count more (half-life ~two months). Length and word-difficulty preferences only
count feedback from the child's current age band, since what was "too hard" at 4 may be right
at 6. "Forget this" ignores everything before the reset.

The result becomes a few FIXED instructions for the story writer. Nothing the parent types
reaches the prompt this way, so feedback can't be used for prompt injection.
"""

import math
import time
from dataclasses import dataclass, field

from kahaani.schemas import TasteToken as Token

TAGS: dict[str, str] = {
    "funny": "Funny",
    "calm": "Calm, good for bedtime",
    "adventure": "More adventure please",
    "too_long": "Too long",
    "too_short": "Too short",
    "too_easy": "Too easy",
    "too_hard": "Too hard",
    "preachy": "The lesson felt preachy",
    "loved_pictures": "Loved the pictures",
    "pictures_off": "Pictures weren't quite right",
}

# What each taste token tells the story writer. Fixed wording only.
PROMPT_LINES: dict[str, str] = {
    "tone:funny": "This family loves funny stories: add gentle jokes, a silly moment or two, "
    "and a fun sound the child can repeat.",
    "tone:calm": "This family wants calm stories: keep the mood soft and soothing, with a slow, "
    "cosy ending that's good for bedtime.",
    "length:shorter": "This family prefers short pages: keep to the sentence count above.",
    "length:longer": "This family enjoys fuller pages: keep to the sentence count above.",
    "words:simpler": "Use only the simplest everyday words.",
    "words:richer": "Include one or two new, interesting words, made clear by the story.",
    "plot:adventure": "Add a small, safe adventure: a search, a little journey, or a surprise.",
    "lesson:subtle": "Never state the lesson outright, even for younger children; show it "
    "through what the hero does.",
}

SUMMARY: dict[str, str] = {
    "tone:funny": "funny stories",
    "tone:calm": "calm, bedtime-friendly stories",
    "length:shorter": "shorter pages",
    "length:longer": "longer pages",
    "words:simpler": "simpler words",
    "words:richer": "a few new words",
    "plot:adventure": "a bit of adventure",
    "lesson:subtle": "lessons shown, not told",
}


def age_band(age: int) -> str:
    return "3-4" if age <= 4 else "5-6" if age <= 6 else "7-8"


HALF_LIFE_DAYS = 60
THRESHOLD = 0.9  # roughly one recent tag, or a few weaker signals that agree


@dataclass
class Taste:
    tokens: list[Token] = field(default_factory=list)  # prompt-affecting, sorted
    style: str | None = None  # art style they've enjoyed most
    evidence: int = 0  # books with any signal
    liked_books: int = 0

    @property
    def summary(self) -> list[str]:
        return [SUMMARY[t] for t in self.tokens]

    def as_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "summary": self.summary,
            "style": self.style,
            "evidence": self.evidence,
            "likedBooks": self.liked_books,
        }


def _weight(ts: float | None, now: float) -> float:
    if not ts:
        return 1.0
    days = max(0.0, (now - ts) / 86400)
    return math.pow(0.5, days / HALF_LIFE_DAYS)


def compute(child: dict, history: list[dict], current_age: int, now: float | None = None) -> Taste:
    """`history`: the child's books with optional feedback (see Store.child_history)."""
    now = now or time.time()
    reset = child.get("taste_reset_at") or 0
    band = age_band(current_age)
    score: dict[str, float] = {k: 0.0 for k in ("tone", "length", "words", "adventure", "subtle")}
    calm = funny = 0.0
    styles: dict[str, float] = {}
    evidence = liked = 0

    for b in history:
        stamp = b.get("feedback_at") or b.get("last_read_at") or b["created_at"]
        if stamp < reset:
            continue
        w = _weight(stamp, now)
        same_band = age_band(b["brief"]["age"]) == band
        rating = b.get("rating")
        tags = set(b.get("tags") or [])

        # Implicit signals.
        implicit = 0.0
        if b["read_count"] >= 2:
            implicit = 1.0  # read again and again
        elif b["read_count"] == 1:
            implicit = 0.3
        elif (
            b["progress_page"]
            and b["progress_page"] < b["page_count"]
            and b.get("last_read_at")
            and now - b["last_read_at"] > 3 * 86400
        ):
            implicit = -0.5  # stopped partway and never came back
        overall = (rating if rating is not None else 0) + implicit
        if rating is None and implicit == 0:
            continue
        evidence += 1
        if overall > 0.5:
            liked += 1

        funny += w * (("funny" in tags) * 1.0)
        calm += w * (("calm" in tags) * 1.0)
        score["adventure"] += w * (("adventure" in tags) * 1.0)
        score["subtle"] += w * (("preachy" in tags) * 1.0)
        if same_band:
            score["length"] += w * (("too_short" in tags) - ("too_long" in tags))
            score["words"] += w * (("too_easy" in tags) - ("too_hard" in tags))

        style = b["brief"]["style"]
        pic = ("loved_pictures" in tags) - ("pictures_off" in tags)
        styles[style] = styles.get(style, 0.0) + w * (overall * 0.5 + pic)

    tokens = []
    if funny >= THRESHOLD and funny > calm:
        tokens.append("tone:funny")
    elif calm >= THRESHOLD and calm > funny:
        tokens.append("tone:calm")
    if score["length"] <= -THRESHOLD:
        tokens.append("length:shorter")
    elif score["length"] >= THRESHOLD:
        tokens.append("length:longer")
    if score["words"] <= -THRESHOLD:
        tokens.append("words:simpler")
    elif score["words"] >= THRESHOLD:
        tokens.append("words:richer")
    if score["adventure"] >= THRESHOLD:
        tokens.append("plot:adventure")
    if score["subtle"] >= THRESHOLD:
        tokens.append("lesson:subtle")

    best_style = max(styles.items(), key=lambda kv: kv[1], default=(None, 0.0))
    return Taste(
        tokens=sorted(tokens),
        style=best_style[0] if best_style[1] >= THRESHOLD else None,
        evidence=evidence,
        liked_books=liked,
    )


def prompt_section(tokens: list[str]) -> str:
    lines = [PROMPT_LINES[t] for t in tokens if t in PROMPT_LINES]
    if not lines:
        return ""
    return (
        "\n\nTHIS FAMILY'S TASTE (learned from their feedback; follow it within the rules "
        "above)\n" + "\n".join(f"- {line}" for line in lines)
    )
