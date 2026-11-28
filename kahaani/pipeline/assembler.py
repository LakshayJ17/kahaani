"""Step 7: HTML -> PDF (WeasyPrint), PDF -> page images -> narrated MP4 (moviepy).

WeasyPrint shapes text with HarfBuzz, so Devanagari conjuncts (क्ष, त्र, श्र) render
correctly. ReportLab does not.
"""

import base64
import io
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kahaani.schemas import Brief, Story

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
VIDEO_WIDTH = 1280  # the 288x180mm page becomes 1280x800
PAUSE_AFTER_PAGE = 0.8


def _ensure_native_libs() -> None:
    """On macOS, Python from uv/pyenv doesn't search Homebrew's lib folder."""
    if sys.platform == "darwin":
        brew = "/opt/homebrew/lib" if Path("/opt/homebrew/lib").exists() else "/usr/local/lib"
        current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if brew not in current.split(":"):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(p for p in (current, brew) if p)


def _data_uri(img: bytes) -> str:
    mime = "image/png" if img[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(img).decode()}"


def _age_class(age: int) -> str:
    return "age-small" if age <= 4 else "age-mid" if age <= 6 else "age-big"


TEXTS = {
    "en": {
        "for": "A story for {name}",
        "end": "The End",
        "note": "Made with Kahaani. This story and its pictures were made by AI. "
        "Please read it before sharing it with your child.",
    },
    "hi": {
        "for": "{name} के लिए एक कहानी",
        "end": "समाप्त",
        "note": "कहानी ऐप से बनी। यह कहानी और चित्र AI से बनाए गए हैं। "
        "बच्चे को सुनाने से पहले एक बार ज़रूर पढ़ लें।",
    },
}


def render_html(brief: Brief, story: Story, hero: bytes, pages: list[bytes]) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    t = TEXTS[brief.language]
    return env.get_template("book.html").render(
        lang=brief.language,
        title=story.title,
        for_line=t["for"].format(name=story.hero_name),
        end_text=t["end"],
        note=t["note"],
        age_class=_age_class(brief.age),
        hero_src=_data_uri(hero),
        pages=[
            {"number": p.number, "text": p.text, "mood": p.mood, "src": _data_uri(img)}
            for p, img in zip(story.pages, pages, strict=True)
        ],
    )


def allowed_url(url: str) -> bool:
    """The book only needs the pictures we embed as data: URIs and its own bundled fonts.
    Anything else (a web address, another file on the server) is refused, so no text in a
    story could ever make the PDF renderer fetch or read something."""
    if url.startswith("data:"):
        return True
    parts = urlparse(url)
    if parts.scheme != "file" or parts.netloc not in ("", "localhost"):
        return False
    return Path(unquote(parts.path)).resolve().is_relative_to(TEMPLATES)


def _url_fetcher():
    from weasyprint.urls import URLFetcher

    class TemplateOnly(URLFetcher):
        def fetch(self, url, headers=None):
            if not allowed_url(url):
                raise ValueError(f"blocked URL in book HTML: {url[:60]}")
            return super().fetch(url, headers)

    return TemplateOnly(allowed_protocols=("data", "file"), allow_redirects=False)


def build_pdf(html: str) -> bytes:
    _ensure_native_libs()
    from weasyprint import HTML

    start = time.perf_counter()
    pdf = HTML(string=html, base_url=str(TEMPLATES), url_fetcher=_url_fetcher()).write_pdf()
    log.info("pdf built secs=%.1f", time.perf_counter() - start)
    return pdf


def pdf_to_images(pdf: bytes, width: int = VIDEO_WIDTH) -> list[bytes]:
    from pdf2image import convert_from_bytes

    out = []
    for page in convert_from_bytes(pdf, size=(width, None)):
        page = page.convert("RGB")
        # H.264 needs even dimensions.
        w, h = page.size
        if w % 2 or h % 2:
            page = page.resize((w - w % 2, h - h % 2))
        buf = io.BytesIO()
        page.save(buf, "PNG")
        out.append(buf.getvalue())
    return out


def build_video(frames: list[bytes], audio: list[bytes], audio_ext: str, fps: int = 12) -> bytes:
    """One clip per page, each as long as its narration plus a short pause."""
    if len(frames) != len(audio):
        raise ValueError(f"{len(frames)} frames but {len(audio)} audio clips")
    import numpy as np
    from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
    from PIL import Image

    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="kahaani-") as tmp:
        clips, audio_clips = [], []
        for i, (frame, sound) in enumerate(zip(frames, audio, strict=True)):
            apath = Path(tmp) / f"a{i}.{audio_ext}"
            apath.write_bytes(sound)
            aclip = AudioFileClip(str(apath))
            audio_clips.append(aclip)
            img = np.array(Image.open(io.BytesIO(frame)).convert("RGB"))
            pause = PAUSE_AFTER_PAGE * (2 if i == len(frames) - 1 else 1)
            clips.append(ImageClip(img).with_duration(aclip.duration + pause).with_audio(aclip))
        out = Path(tmp) / "book.mp4"
        video = concatenate_videoclips(clips, method="compose")
        video.write_videofile(
            str(out),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=None,
        )
        for c in audio_clips:
            c.close()
        video.close()
        data = out.read_bytes()
    log.info("video built secs=%.1f pages=%d", time.perf_counter() - start, len(frames))
    return data
