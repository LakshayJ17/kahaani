"""HTTP API for the website.

Parents sign in with Google (Supabase Auth). Making a book runs as an in-memory job on one
background worker (one book at a time on the free server); finished books are saved to the
family's library, together with an anonymous template other families can reuse.

Pictures, PDFs and videos are served through short-lived signed links, because <img> and
<video> tags can't send the sign-in token.

    uv run python -m kahaani.api            # http://127.0.0.1:8000
"""

import base64
import hashlib
import hmac
import io
import logging
import os
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from kahaani.auth import User, current_user, dev_auth_enabled
from kahaani.blobs import Blobs, LocalBlobs, SupabaseBlobs
from kahaani.config import Settings, get_settings
from kahaani.db import Store, today_start
from kahaani.library import MAX_BOOKS_PER_ACCOUNT, Library, fingerprint
from kahaani.pipeline import assembler
from kahaani.pipeline.create_book import BookError, BookMaker, Draft
from kahaani.samples import SAMPLES, load_samples
from kahaani.schemas import Brief
from kahaani.taste import TAGS, Taste
from kahaani.taste import compute as compute_taste

log = logging.getLogger("kahaani.api")
ROOT = Path(__file__).resolve().parent.parent
WEB_OUT = ROOT / "web" / "out"
JOB_TTL = 3600  # unfinished jobs (drafts) are dropped after an hour
LINK_TTL = 3600  # signed file links last an hour

FIELD_HELP = {
    "child_name": "Use letters and spaces only, up to 20.",
    "age": "Choose an age from 3 to 8.",
    "appearance": "Keep this under 150 characters.",
    "favourites": "Keep this under 100 characters.",
    "custom_lesson": "Describe the lesson in under 80 characters.",
    "lesson": "Choose a lesson.",
    "language": "Choose English or Hindi.",
    "style": "Choose an art style.",
    "pages": "Choose 4 or 8 pages.",
    "hero": "Choose girl or boy.",
}


class BookRequest(BaseModel):
    child_name: str = ""
    age: int = 5
    hero: str | None = None
    appearance: str = ""
    favourites: str = ""
    lesson: str = "sharing"
    custom_lesson: str | None = None
    language: str = "en"
    style: str = "watercolour"
    pages: int = 4
    fresh: bool = False  # "write a new version" even if this family has one already
    use_taste: bool = True  # follow what we've learned about this child


class RedoRequest(BaseModel):
    request: str = ""


class FeedbackRequest(BaseModel):
    rating: Literal[-1, 0, 1]
    tags: list[str] = []


class ProgressRequest(BaseModel):
    page: int
    finished: bool = False


Action = Literal["start", "hero", "finish", "redo"]


@dataclass
class Job:
    id: str
    user_id: str
    brief: Brief
    fingerprint: str
    created: float = field(default_factory=time.time)
    exclude: set[str] = field(default_factory=set)
    draft: Draft | None = None
    saved_book_id: str | None = None
    redo_book_id: str | None = None  # set when this job edits a saved book
    busy: bool = False
    action: Action | None = None
    progress: float = 0.0
    step: str = ""
    error: dict | None = None
    revision: int = 0


def error(message: str, status: int, **extra) -> JSONResponse:
    return JSONResponse({"error": {"message": message, **extra}}, status_code=status)


class Signer:
    """HMAC-signed, expiring links: /api/files/{book}/{name}?t=..."""

    def __init__(self, secret: str | None):
        self.key = (secret or secrets.token_hex(32)).encode()

    def sign(self, user_id: str, book_id: str, name: str) -> str:
        exp = int(time.time() + LINK_TTL)
        sig = self._sig(user_id, book_id, name, exp)
        token = base64.urlsafe_b64encode(f"{user_id}|{exp}|{sig}".encode()).decode()
        return f"/api/files/{book_id}/{name}?t={token}"

    def _sig(self, user_id: str, book_id: str, name: str, exp: int | str) -> str:
        msg = f"{user_id}|{book_id}|{name}|{exp}".encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()[:32]

    def check(self, token: str, book_id: str, name: str) -> str:
        try:
            user_id, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
            expires = int(exp)
        except Exception as e:  # malformed token
            raise HTTPException(403, "This link isn't valid.") from e
        if not hmac.compare_digest(sig, self._sig(user_id, book_id, name, exp)):
            raise HTTPException(403, "This link isn't valid.")
        if expires < time.time():
            raise HTTPException(403, "This link has expired. Please reload the page.")
        return user_id


class Builds:
    """Small in-memory cache for rebuilt PDFs and videos."""

    def __init__(self, size: int = 12):
        self.size, self.items, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, key, make):
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        value = make()
        with self.lock:
            self.items[key] = value
            while len(self.items) > self.size:
                self.items.popitem(last=False)
        return value

    def drop(self, book_id: str) -> None:
        with self.lock:
            for k in [k for k in self.items if k[0] == book_id]:
                del self.items[k]


def for_line(language: str, hero_name: str) -> str:
    return f"{hero_name} के लिए एक कहानी" if language == "hi" else f"A story for {hero_name}"


def jpeg(data: bytes, max_side: int = 1024) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


class Service:
    def __init__(self, settings: Settings, store: Store, blobs: Blobs, maker_factory):
        self.settings = settings
        self.store = store
        self.blobs = blobs
        self.library = Library(store, blobs)
        self._maker_factory = maker_factory
        self._maker: BookMaker | None = None
        self.jobs: dict[str, Job] = {}
        self.queue: list[str] = []
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="book")
        self.signer = Signer(settings.url_secret)
        self.builds = Builds()

    @property
    def maker(self) -> BookMaker:
        if self._maker is None:
            self._maker = self._maker_factory()
            self._maker.library = self.library
            self.library.llm = self._maker.checker
        return self._maker

    # ------------------------------------------------------------------ jobs

    def expire(self) -> None:
        cutoff = time.time() - JOB_TTL
        with self.lock:
            for jid in [j for j, job in self.jobs.items() if job.created < cutoff and not job.busy]:
                del self.jobs[jid]

    def job(self, job_id: str, user: User) -> Job:
        job = self.jobs.get(job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(404, "This book has expired. Please start a new one.")
        return job

    def active_starts(self, user_id: str | None = None) -> int:
        """New books in progress (not yet saved), so limits count them too."""
        return sum(
            1
            for j in self.jobs.values()
            if j.saved_book_id is None
            and j.redo_book_id is None
            and (user_id is None or j.user_id == user_id)
            and (j.busy or j.draft is not None)
        )

    def submit(self, job: Job, action: Action, work) -> None:
        if job.busy:
            raise HTTPException(409, "This book is still being worked on.")
        job.busy, job.action, job.error = True, action, None
        job.progress, job.step = 0.0, "Waiting for a free spot"
        with self.lock:
            self.queue.append(job.id)

        def run():
            with self.lock:
                self.queue.remove(job.id)

            def report(frac: float, msg: str) -> None:
                job.progress, job.step = frac, msg

            try:
                work(report)
            except BookError as e:
                job.error = {"message": str(e), "reasons": e.reasons}
            except Exception:
                log.exception("unexpected error during %s", action)
                job.error = {"message": "Something went wrong. Please try again.", "reasons": []}
            finally:
                job.busy, job.action = False, None
                job.revision += 1

        self.pool.submit(run)

    def queue_position(self, job_id: str) -> int:
        with self.lock:
            return self.queue.index(job_id) if job_id in self.queue else 0

    def job_view(self, job: Job) -> dict:
        view: dict = {
            "id": job.id,
            "busy": job.busy,
            "action": job.action,
            "progress": round(job.progress, 3),
            "step": job.step,
            "queuePosition": self.queue_position(job.id) if job.busy else 0,
            "error": job.error,
            "stage": "saved" if job.saved_book_id else "hero" if job.draft else "new",
            "bookId": job.saved_book_id or job.redo_book_id,
        }
        if job.draft:
            story = job.draft.story
            view |= {
                "title": story.title,
                "language": job.brief.language,
                "forLine": for_line(job.brief.language, story.hero_name),
                "heroUrl": f"/api/jobs/{job.id}/hero.jpg?v={job.revision}",
                "reused": job.draft.reuse,
            }
        return view

    # ------------------------------------------------------------------ taste

    def taste(self, user_id: str, child: dict | None, age: int | None = None) -> Taste:
        if not child:
            return Taste()
        child, history = self.store.child_history(user_id, child["id"])
        if age is None:
            age = max(3, min(8, time.gmtime().tm_year - (child.get("birth_year") or 0)))
        return compute_taste(child, history, age)

    # ------------------------------------------------------------------ saved books

    def book_view(self, user: User, row: dict) -> dict:
        def sign(name: str) -> str:
            return self.signer.sign(user.id, row["id"], name)

        brief, story = row["brief"], row["story"]
        return {
            "id": row["id"],
            "title": row["title"],
            "language": row["language"],
            "forLine": for_line(row["language"], story["hero_name"]),
            "childName": brief["child_name"],
            "heroUrl": sign("hero.jpg"),
            "pages": [
                {
                    "number": p["number"],
                    "text": p["text"],
                    "mood": p["mood"],
                    "imageUrl": sign(f"p{p['number']}.jpg"),
                }
                for p in story["pages"]
            ],
            "pdfUrl": sign("book.pdf"),
            "videoUrl": sign("book.mp4"),
            "quality": row["quality"],
            "warnings": row["warnings"],
            "progressPage": row["progress_page"],
            "readCount": row["read_count"],
            "reused": row["reused"],
            "reported": row["reported"],
            "createdAt": row["created_at"],
            "feedback": self._feedback(user.id, row["id"]),
        }

    def _feedback(self, user_id: str, book_id: str) -> dict | None:
        fb = self.store.get_feedback(user_id, book_id)
        return {"rating": fb["rating"], "tags": fb["tags"]} if fb else None

    def file(self, user_id: str, book_id: str, name: str) -> tuple[bytes, str]:
        row = self.store.get_book(user_id, book_id)
        if row is None:
            raise HTTPException(404, "This book isn't in your library.")
        assets = row["assets"]
        if name == "hero.jpg":
            return self.blobs.get(assets["hero"]), "image/jpeg"
        key = name.removesuffix(".jpg")
        if name.endswith(".jpg") and key.startswith("p") and key in assets:
            return self.blobs.get(assets[key]), "image/jpeg"
        version = hashlib.sha256(repr((assets, row["story"])).encode()).hexdigest()[:12]
        if name == "book.pdf":
            pdf = self.builds.get((book_id, "pdf", version), lambda: self._pdf(user_id, book_id))
            return pdf, "application/pdf"
        if name == "book.mp4":
            mp4 = self.builds.get((book_id, "mp4", version), lambda: self._video(user_id, book_id))
            return mp4, "video/mp4"
        raise HTTPException(404, "No such file.")

    def _pdf(self, user_id: str, book_id: str) -> bytes:
        book = self.library.load(user_id, book_id)
        return assembler.build_pdf(
            assembler.render_html(book.brief, book.story, book.hero, book.pages)
        )

    def _video(self, user_id: str, book_id: str) -> bytes:
        book = self.library.load(user_id, book_id)
        frames = assembler.pdf_to_images(self._pdf(user_id, book_id))
        return assembler.build_video(frames, book.audio, book.audio_ext)


def default_service(settings: Settings, maker_factory=None) -> Service:
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    store = Store(settings.database_url)
    store.create_all()
    if settings.supabase_url and settings.supabase_service_key:
        blobs: Blobs = SupabaseBlobs(settings.supabase_url, settings.supabase_service_key)
        blobs.ensure_bucket()
    else:
        blobs = LocalBlobs(settings.blob_dir)
    return Service(
        settings, store, blobs, maker_factory or (lambda: BookMaker.from_settings(settings))
    )


def create_app(service: Service | None = None) -> FastAPI:
    svc = service or default_service(get_settings())
    app = FastAPI(title="Kahaani", docs_url=None, redoc_url=None)
    app.state.service = svc
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def drop_old_jobs(request: Request, call_next):
        svc.expire()
        return await call_next(request)

    def signed_in(request: Request) -> User:
        user = current_user(request)
        svc.store.upsert_user(user.id, user.email, user.name)
        return user

    def consented(user: User = Depends(signed_in)) -> User:
        row = svc.store.upsert_user(user.id, user.email, user.name)
        if not row["consent_at"]:
            raise HTTPException(403, "Please agree to how we store your books first.")
        return user

    # ------------------------------------------------------------------ public

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/config")
    def config():
        return {
            "supabaseUrl": svc.settings.supabase_url,
            "supabaseAnonKey": svc.settings.supabase_anon_key,
            "devAuth": dev_auth_enabled(),
        }

    @app.get("/api/samples")
    def samples():
        return [
            {
                "id": s.pdf.parent.name,
                "title": s.title,
                "blurb": s.blurb,
                "coverUrl": f"/api/samples/{s.pdf.parent.name}/cover.jpg",
                "pdfUrl": f"/api/samples/{s.pdf.parent.name}/book.pdf",
                "videoUrl": f"/api/samples/{s.pdf.parent.name}/book.mp4" if s.video else None,
            }
            for s in load_samples()
        ]

    @app.get("/api/samples/{sample_id}/{name}")
    def sample_file(sample_id: str, name: str):
        if name not in ("cover.jpg", "book.pdf", "book.mp4") or not sample_id.isalnum():
            raise HTTPException(404)
        path = SAMPLES / sample_id / name
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    # ------------------------------------------------------------------ account

    @app.get("/api/me")
    def me(user: User = Depends(signed_in)):
        row = svc.store.upsert_user(user.id, user.email, user.name)
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "consent": bool(row["consent_at"]),
            "booksToday": svc.store.books_made_since(today_start(), user.id),
            "booksPerDay": svc.settings.books_per_ip_per_day,
            "saved": svc.store.count_books(user.id),
            "maxSaved": MAX_BOOKS_PER_ACCOUNT,
        }

    @app.post("/api/me/consent")
    def consent(user: User = Depends(signed_in)):
        svc.store.give_consent(user.id)
        return {"ok": True}

    @app.delete("/api/me")
    def delete_account(user: User = Depends(signed_in)):
        removed = svc.library.delete_account(user.id)
        for jid in [j for j, job in svc.jobs.items() if job.user_id == user.id]:
            svc.jobs.pop(jid, None)
        if (
            svc.settings.supabase_url
            and svc.settings.supabase_service_key
            and not user.id.startswith("dev-")
        ):
            r = httpx.delete(
                f"{svc.settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user.id}",
                headers={
                    "Authorization": f"Bearer {svc.settings.supabase_service_key}",
                    "apikey": svc.settings.supabase_service_key,
                },
                timeout=30,
            )
            if r.status_code >= 400:
                log.warning("supabase user delete HTTP %s", r.status_code)
        return {"ok": True, "booksDeleted": removed}

    # ------------------------------------------------------------------ making a book

    @app.post("/api/books")
    def create_book(body: BookRequest, user: User = Depends(consented)):
        fields: dict[str, str] = {}
        if body.hero not in ("girl", "boy"):
            fields["hero"] = FIELD_HELP["hero"]
        try:
            brief = Brief(
                child_name=body.child_name,
                age=body.age,
                hero=body.hero,
                appearance=body.appearance,
                favourites=body.favourites,
                lesson=body.lesson,
                custom_lesson=(body.custom_lesson or None) if body.lesson == "custom" else None,
                language=body.language,
                style=body.style,
                pages=body.pages,
            )
        except ValidationError as e:
            for err in e.errors():
                key = str(err["loc"][0]) if err["loc"] else "custom_lesson"
                fields[key] = FIELD_HELP.get(key, "Please check this.")
        if fields:
            return error("Please check the highlighted details.", 422, fields=fields)

        if body.use_taste:
            child = svc.store.find_child(user.id, brief.child_name)
            tokens = svc.taste(user.id, child, brief.age).tokens
            brief = brief.model_copy(update={"taste": tokens})

        fp = fingerprint(brief)
        existing = svc.store.find_by_fingerprint(user.id, fp)
        if existing and not body.fresh:
            return {"existingBookId": existing["id"], "title": existing["title"]}

        if svc.store.count_books(user.id) >= MAX_BOOKS_PER_ACCOUNT:
            return error(
                f"You have {MAX_BOOKS_PER_ACCOUNT} saved books, the most we can keep on our "
                "free plan. Delete one to make room.",
                409,
            )
        made = svc.store.books_made_since(today_start(), user.id) + svc.active_starts(user.id)
        if made >= svc.settings.books_per_ip_per_day:
            return error(
                f"You've made {svc.settings.books_per_ip_per_day} books today, the daily limit on "
                "our free servers. Please come back tomorrow.",
                429,
            )
        everyone = svc.store.books_made_since(today_start()) + svc.active_starts()
        if everyone >= svc.settings.global_books_per_day:
            return error(
                "Kahaani has made all the books it can for today on its free servers. "
                "Please come back tomorrow.",
                429,
            )

        # A new version shouldn't reuse the template behind the book they already have.
        exclude = {existing["template_id"]} if existing and existing["template_id"] else set()
        job = Job(
            id=uuid.uuid4().hex, user_id=user.id, brief=brief, fingerprint=fp, exclude=exclude
        )
        svc.jobs[job.id] = job

        def work(report):
            job.draft = svc.maker.start(brief, report, exclude=job.exclude)

        svc.submit(job, "start", work)
        return svc.job_view(job)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, user: User = Depends(signed_in)):
        return svc.job_view(svc.job(job_id, user))

    @app.post("/api/jobs/{job_id}/hero")
    def new_hero(job_id: str, user: User = Depends(signed_in)):
        job = svc.job(job_id, user)
        if not job.draft or job.saved_book_id:
            raise HTTPException(409, "There's no hero picture to replace.")

        def work(report):
            report(0.3, "Drawing another hero")
            job.draft = svc.maker.new_hero(job.draft)

        svc.submit(job, "hero", work)
        return svc.job_view(job)

    @app.post("/api/jobs/{job_id}/approve")
    def approve(job_id: str, user: User = Depends(signed_in)):
        job = svc.job(job_id, user)
        if not job.draft or job.saved_book_id:
            raise HTTPException(409, "Create a story first.")

        def work(report):
            book = svc.maker.finish(job.draft, report)
            report(0.97, "Saving to your library")
            job.saved_book_id = svc.library.save(user.id, book, job.fingerprint)
            job.draft = None  # the saved copy is the one that matters now

        svc.submit(job, "finish", work)
        return svc.job_view(job)

    @app.get("/api/jobs/{job_id}/hero.jpg")
    def job_hero(job_id: str):
        # <img> can't send the sign-in token; the job id itself is an unguessable secret.
        job = svc.jobs.get(job_id)
        if job is None or job.draft is None:
            raise HTTPException(404)
        return Response(jpeg(job.draft.hero), media_type="image/jpeg")

    # ------------------------------------------------------------------ library

    @app.get("/api/library")
    def library(user: User = Depends(signed_in)):
        groups: dict[str, dict] = {}
        kids = {c["id"]: c for c in svc.store.list_children(user.id)}
        for b in svc.store.list_books(user.id):
            name = b["child_name"] or b["brief"]["child_name"]
            if name.lower() not in groups:
                child = kids.get(b["child_id"])
                groups[name.lower()] = {
                    "childName": name,
                    "childId": b["child_id"],
                    "taste": svc.taste(user.id, child).as_dict(),
                    "books": [],
                }
            group = groups[name.lower()]
            group["books"].append(
                {
                    "id": b["id"],
                    "title": b["title"],
                    "language": b["language"],
                    "pageCount": b["page_count"],
                    "progressPage": b["progress_page"],
                    "readCount": b["read_count"],
                    "lastReadAt": b["last_read_at"],
                    "createdAt": b["created_at"],
                    "reused": b["reused"],
                    "coverUrl": svc.signer.sign(user.id, b["id"], "hero.jpg"),
                }
            )
        return {"children": list(groups.values())}

    @app.get("/api/library/{book_id}")
    def get_saved(book_id: str, user: User = Depends(signed_in)):
        row = svc.store.get_book(user.id, book_id)
        if row is None:
            raise HTTPException(404, "This book isn't in your library.")
        view = svc.book_view(user, row)
        editing = next(
            (
                j
                for j in svc.jobs.values()
                if j.redo_book_id == book_id and j.user_id == user.id and (j.busy or j.error)
            ),
            None,
        )
        view["job"] = svc.job_view(editing) if editing else None
        return view

    @app.get("/api/files/{book_id}/{name}")
    def file(book_id: str, name: str, t: str, request: Request):
        user_id = svc.signer.check(t, book_id, name)
        data, media = svc.file(user_id, book_id, name)
        headers = {"Cache-Control": "private, max-age=3600"}
        if name.endswith((".pdf", ".mp4")) and request.query_params.get("download"):
            row = svc.store.get_book(user_id, book_id)
            ext = name.rsplit(".", 1)[1]
            headers["Content-Disposition"] = (
                f"attachment; filename*=UTF-8''{quote(row['title'])}.{ext}"
            )
        if name.endswith(".jpg"):
            data = jpeg(data)
        return Response(data, media_type=media, headers=headers)

    @app.post("/api/library/{book_id}/progress")
    def progress(book_id: str, body: ProgressRequest, user: User = Depends(signed_in)):
        svc.store.record_progress(user.id, book_id, body.page, body.finished)
        return {"ok": True}

    @app.post("/api/library/{book_id}/report")
    def report(book_id: str, user: User = Depends(signed_in)):
        if not svc.library.report(user.id, book_id):
            raise HTTPException(404, "This book isn't in your library.")
        return {"ok": True}

    @app.delete("/api/library/{book_id}")
    def delete_book(book_id: str, user: User = Depends(signed_in)):
        if not svc.library.delete(user.id, book_id):
            raise HTTPException(404, "This book isn't in your library.")
        svc.builds.drop(book_id)
        return {"ok": True}

    @app.post("/api/library/{book_id}/feedback")
    def feedback(book_id: str, body: FeedbackRequest, user: User = Depends(signed_in)):
        unknown = set(body.tags) - set(TAGS)
        if unknown or len(body.tags) > len(TAGS):
            raise HTTPException(422, "Unknown feedback option.")
        try:
            book = svc.store.save_feedback(user.id, book_id, body.rating, body.tags)
        except KeyError as e:
            raise HTTPException(404, "This book isn't in your library.") from e
        child = next(
            (c for c in svc.store.list_children(user.id) if c["id"] == book["child_id"]), None
        )
        return {"ok": True, "taste": svc.taste(user.id, child).as_dict()}

    @app.get("/api/children")
    def children(user: User = Depends(signed_in)):
        out = []
        latest: dict[str, dict] = {}
        for b in svc.store.list_books(user.id):  # newest first
            latest.setdefault(b["child_id"], b["brief"])
        for c in svc.store.list_children(user.id):
            last = latest.get(c["id"])
            age = max(3, min(8, time.gmtime().tm_year - (c["birth_year"] or 0)))
            out.append(
                {
                    "id": c["id"],
                    "name": c["name"],
                    "age": age,
                    "last": {
                        k: last[k]
                        for k in ("hero", "appearance", "favourites", "language", "style", "pages")
                    }
                    if last
                    else None,
                    "taste": svc.taste(user.id, c, age).as_dict(),
                }
            )
        return out

    @app.delete("/api/children/{child_id}/taste")
    def forget_taste(child_id: str, user: User = Depends(signed_in)):
        if not any(c["id"] == child_id for c in svc.store.list_children(user.id)):
            raise HTTPException(404, "No such child in your library.")
        svc.store.reset_taste(user.id, child_id)
        return {"ok": True}

    @app.post("/api/library/{book_id}/pages/{number}/redo")
    def redo(book_id: str, number: int, body: RedoRequest, user: User = Depends(signed_in)):
        row = svc.store.get_book(user.id, book_id)
        if row is None:
            raise HTTPException(404, "This book isn't in your library.")
        if any(j.redo_book_id == book_id and j.busy for j in svc.jobs.values()):
            raise HTTPException(409, "This book is already being changed.")
        job = Job(
            id=uuid.uuid4().hex,
            user_id=user.id,
            brief=Brief.model_validate(row["brief"]),
            fingerprint=row["fingerprint"],
            redo_book_id=book_id,
        )
        svc.jobs[job.id] = job

        def work(report):
            book = svc.library.load(user.id, book_id)
            book = svc.maker.redo_page(book, number, body.request, report)
            svc.library.update_page(user.id, book_id, book, number)
            svc.builds.drop(book_id)

        svc.submit(job, "redo", work)
        return svc.job_view(job)

    # The built Next.js site (web/out), if present. Mounted last so /api wins.
    if WEB_OUT.exists():
        app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="web")

    return app


def app_factory() -> FastAPI:
    return create_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("weasyprint", "fontTools", "httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    port = int(os.environ.get("PORT", "8000"))
    # Containers (Render, Spaces) set HOST=0.0.0.0; locally stay on this machine only.
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1")
    uvicorn.run("kahaani.api:app_factory", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
