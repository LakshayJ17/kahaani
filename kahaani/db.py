"""Database: accounts, children, saved books, reading progress and shared story templates.

SQLAlchemy Core, so the same code runs on SQLite (local dev, tests) and Postgres (Supabase).
On Postgres everything lives in a private `kahaani` schema with row-level security on, so
Supabase's public REST API can't read it; only this server (with the database password) can.

    DATABASE_URL=postgresql+psycopg://...   # Supabase "connection string"
    DATABASE_URL=sqlite:///.data/kahaani.db # default for local dev
"""

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String(64), primary_key=True),  # Supabase auth user id
    Column("email", String(320)),
    Column("name", String(200)),
    Column("consent_at", Float),  # parent agreed to storage; required before saving books
    Column("created_at", Float, nullable=False),
)

children = Table(
    "children",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(40), nullable=False),
    Column("birth_year", Integer),  # ages change; the year doesn't
    Column("taste_reset_at", Float),  # "forget this taste": ignore feedback before this
    Column("created_at", Float, nullable=False),
    Index("ix_children_user", "user_id"),
)

books = Table(
    "books",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("child_id", String(32), ForeignKey("children.id", ondelete="CASCADE")),
    Column("fingerprint", String(64), nullable=False),  # same details -> same book
    Column("template_id", String(32)),  # shared template it came from or created
    Column("brief", JSON, nullable=False),
    Column("story", JSON, nullable=False),
    Column("assets", JSON, nullable=False),  # name -> blob path (book's own or shared)
    Column("audio_ext", String(8), nullable=False),
    Column("quality", JSON, nullable=False),
    Column("warnings", JSON, nullable=False),
    Column("reused", String(16), nullable=False),  # "none" | "story" | "story+pictures"
    Column("title", String(300), nullable=False),
    Column("language", String(4), nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("progress_page", Integer, nullable=False, default=0),
    Column("read_count", Integer, nullable=False, default=0),
    Column("last_read_at", Float),
    Column("reported", Boolean, nullable=False, default=False),
    Column("created_at", Float, nullable=False),
    Index("ix_books_user", "user_id", "created_at"),
    Index("ix_books_fingerprint", "user_id", "fingerprint"),
)

templates = Table(
    "templates",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("story_key", String(64), nullable=False),  # language/age band/lesson/pages/hero
    Column("favourites", JSON, nullable=False),  # normalised words, for fuzzy matching
    Column("style", String(16), nullable=False),
    Column("looks", JSON, nullable=False),  # normalised words of the described character
    Column("story", JSON, nullable=False),  # name replaced by {HERO}
    Column("assets", JSON, nullable=False),  # shared pictures (no audio: it says the name)
    Column("source_user_id", String(64)),  # cleared when that account is deleted
    Column("uses", Integer, nullable=False, default=0),
    Column("reports", Integer, nullable=False, default=0),
    Column("disabled", Boolean, nullable=False, default=False),
    Column("likes", Integer, nullable=False, default=0),  # distinct families who loved it
    Column("dislikes", Integer, nullable=False, default=0),  # ...and who said "not for us"
    Column("created_at", Float, nullable=False),
    Index("ix_templates_key", "version", "story_key", "disabled"),
)

feedback = Table(  # a parent's reaction to one of their books (one row per book)
    "feedback",
    metadata,
    Column("book_id", String(32), ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("child_id", String(32), ForeignKey("children.id", ondelete="CASCADE")),
    Column("rating", Integer, nullable=False),  # 1 loved it, 0 okay, -1 not for us
    Column("tags", JSON, nullable=False),  # fixed vocabulary, see kahaani.taste.TAGS
    Column("created_at", Float, nullable=False),
    Index("ix_feedback_child", "user_id", "child_id"),
)

usage = Table(  # what each account asked the AI to do, for the daily limits
    "usage",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(64), nullable=False),
    Column("kind", String(16), nullable=False),  # "story" (a new book) | "page" (a page change)
    Column("created_at", Float, nullable=False),
    Index("ix_usage_kind", "kind", "created_at"),
)

names = Table(  # cached name spellings, e.g. Aarav -> आरव
    "name_spellings",
    metadata,
    Column("latin", String(40), primary_key=True),
    Column("devanagari", String(80), nullable=False),
)


def new_id() -> str:
    return uuid.uuid4().hex


def today_start() -> float:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC).timestamp()


class Store:
    def __init__(self, url: str):
        self.url = url
        self.postgres = url.startswith("postgres")
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if self.postgres:
            # Keep our tables out of Supabase's public REST API.
            kwargs["execution_options"] = {"schema_translate_map": {None: "kahaani"}}
        else:
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(url, **kwargs)

    def create_all(self) -> None:
        if self.postgres:
            with self.engine.begin() as c:
                c.execute(text("CREATE SCHEMA IF NOT EXISTS kahaani"))
        metadata.create_all(self.engine)
        self._add_missing_columns()
        if self.postgres:
            with self.engine.begin() as c:
                for t in metadata.sorted_tables:
                    c.execute(text(f"ALTER TABLE kahaani.{t.name} ENABLE ROW LEVEL SECURITY"))

    def _add_missing_columns(self) -> None:
        """Tiny migration: add columns introduced after a table was first created."""
        from sqlalchemy import inspect

        schema = "kahaani" if self.postgres else None
        insp = inspect(self.engine)
        with self.engine.begin() as c:
            for table in metadata.sorted_tables:
                have = {col["name"] for col in insp.get_columns(table.name, schema=schema)}
                for col in table.columns:
                    if col.name in have:
                        continue
                    kind = col.type.compile(dialect=self.engine.dialect)
                    default = col.default.arg if col.default is not None else None
                    clause = (
                        f" DEFAULT {int(default) if isinstance(default, bool) else default}"
                        if isinstance(default, (int, float, bool))
                        else ""
                    )
                    name = f"{schema}.{table.name}" if schema else table.name
                    c.execute(text(f"ALTER TABLE {name} ADD COLUMN {col.name} {kind}{clause}"))

    # ------------------------------------------------------------------ users and children

    def upsert_user(self, user_id: str, email: str | None, name: str | None) -> dict:
        with self.engine.begin() as c:
            row = c.execute(select(users).where(users.c.id == user_id)).mappings().first()
            if row is None:
                c.execute(
                    insert(users).values(id=user_id, email=email, name=name, created_at=time.time())
                )
            elif (row["email"], row["name"]) != (email, name):
                c.execute(update(users).where(users.c.id == user_id).values(email=email, name=name))
            return dict(c.execute(select(users).where(users.c.id == user_id)).mappings().one())

    def give_consent(self, user_id: str) -> None:
        with self.engine.begin() as c:
            c.execute(update(users).where(users.c.id == user_id).values(consent_at=time.time()))

    def child_for(self, user_id: str, name: str, age: int) -> str:
        """Find this family's child by name (case-insensitive), or add them."""
        year = datetime.now(UTC).year - age
        with self.engine.begin() as c:
            row = (
                c.execute(
                    select(children).where(
                        children.c.user_id == user_id, func.lower(children.c.name) == name.lower()
                    )
                )
                .mappings()
                .first()
            )
            if row:
                if row["birth_year"] != year:
                    c.execute(
                        update(children).where(children.c.id == row["id"]).values(birth_year=year)
                    )
                return row["id"]
            cid = new_id()
            c.execute(
                insert(children).values(
                    id=cid, user_id=user_id, name=name, birth_year=year, created_at=time.time()
                )
            )
            return cid

    def delete_user(self, user_id: str) -> list[dict]:
        """Remove the account and its books; returns the deleted books (for blob cleanup).
        Shared templates it created stay (they hold no name) but lose the link to it."""
        with self.engine.begin() as c:
            gone = [
                dict(r)
                for r in c.execute(
                    select(books.c.id, books.c.assets).where(books.c.user_id == user_id)
                ).mappings()
            ]
            c.execute(
                update(templates)
                .where(templates.c.source_user_id == user_id)
                .values(source_user_id=None)
            )
            c.execute(delete(feedback).where(feedback.c.user_id == user_id))
            c.execute(delete(usage).where(usage.c.user_id == user_id))
            c.execute(delete(books).where(books.c.user_id == user_id))
            c.execute(delete(children).where(children.c.user_id == user_id))
            c.execute(delete(users).where(users.c.id == user_id))
        return gone

    # ------------------------------------------------------------------ books

    def books_made_since(self, since: float, user_id: str | None = None) -> int:
        q = select(func.count()).select_from(books).where(books.c.created_at >= since)
        if user_id:
            q = q.where(books.c.user_id == user_id)
        with self.engine.connect() as c:
            return int(c.execute(q).scalar_one())

    def record_use(self, user_id: str, kind: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                insert(usage).values(
                    id=new_id(), user_id=user_id, kind=kind, created_at=time.time()
                )
            )

    def uses_since(self, since: float, kind: str, user_id: str | None = None) -> int:
        """A story counts once it's written, even if it's never saved; a page change counts
        when it's asked for."""
        q = (
            select(func.count())
            .select_from(usage)
            .where(usage.c.kind == kind, usage.c.created_at >= since)
        )
        if user_id:
            q = q.where(usage.c.user_id == user_id)
        with self.engine.connect() as c:
            return int(c.execute(q).scalar_one())

    def count_books(self, user_id: str) -> int:
        with self.engine.connect() as c:
            return int(
                c.execute(
                    select(func.count()).select_from(books).where(books.c.user_id == user_id)
                ).scalar_one()
            )

    def find_by_fingerprint(self, user_id: str, fingerprint: str) -> dict | None:
        with self.engine.connect() as c:
            row = (
                c.execute(
                    select(books)
                    .where(books.c.user_id == user_id, books.c.fingerprint == fingerprint)
                    .order_by(books.c.created_at.desc())
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def add_book(self, **values) -> str:
        book_id = values.pop("id", None) or new_id()
        values.setdefault("created_at", time.time())
        values.setdefault("progress_page", 0)
        values.setdefault("read_count", 0)
        values.setdefault("reported", False)
        with self.engine.begin() as c:
            c.execute(insert(books).values(id=book_id, **values))
        return book_id

    def get_book(self, user_id: str, book_id: str) -> dict | None:
        with self.engine.connect() as c:
            row = (
                c.execute(select(books).where(books.c.id == book_id, books.c.user_id == user_id))
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def update_book(self, user_id: str, book_id: str, **values) -> None:
        with self.engine.begin() as c:
            c.execute(
                update(books)
                .where(books.c.id == book_id, books.c.user_id == user_id)
                .values(**values)
            )

    def delete_book(self, user_id: str, book_id: str) -> dict | None:
        book = self.get_book(user_id, book_id)
        if book:
            with self.engine.begin() as c:
                c.execute(delete(books).where(books.c.id == book_id, books.c.user_id == user_id))
        return book

    def list_books(self, user_id: str) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(
                    books.c.id,
                    books.c.title,
                    books.c.language,
                    books.c.page_count,
                    books.c.progress_page,
                    books.c.read_count,
                    books.c.last_read_at,
                    books.c.created_at,
                    books.c.reused,
                    books.c.child_id,
                    books.c.brief,
                    children.c.name.label("child_name"),
                )
                .select_from(books.outerjoin(children, books.c.child_id == children.c.id))
                .where(books.c.user_id == user_id)
                .order_by(books.c.created_at.desc())
            ).mappings()
            return [dict(r) for r in rows]

    def record_progress(self, user_id: str, book_id: str, page: int, finished: bool) -> None:
        book = self.get_book(user_id, book_id)
        if not book:
            return
        page = max(0, min(page, book["page_count"]))
        values: dict[str, Any] = {
            "progress_page": max(page, book["progress_page"]),
            "last_read_at": time.time(),
        }
        if finished:
            values["read_count"] = book["read_count"] + 1
            values["progress_page"] = book["page_count"]
        self.update_book(user_id, book_id, **values)

    # ------------------------------------------------------------------ templates

    def candidate_templates(self, version: int, story_key: str) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(
                select(templates)
                .where(
                    templates.c.version == version,
                    templates.c.story_key == story_key,
                    templates.c.disabled.is_(False),
                )
                .order_by(
                    (templates.c.likes - templates.c.dislikes).desc(), templates.c.uses.desc()
                )
            ).mappings()
            return [dict(r) for r in rows]

    def add_template(self, **values) -> str:
        tid = values.pop("id", None) or new_id()
        values.setdefault("created_at", time.time())
        values.setdefault("uses", 0)
        values.setdefault("reports", 0)
        values.setdefault("disabled", False)
        with self.engine.begin() as c:
            c.execute(insert(templates).values(id=tid, **values))
        return tid

    def template_used(self, template_id: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                update(templates)
                .where(templates.c.id == template_id)
                .values(uses=templates.c.uses + 1)
            )

    def report_template(self, template_id: str) -> None:
        """One report pulls a template out of sharing until someone reviews it."""
        with self.engine.begin() as c:
            c.execute(
                update(templates)
                .where(templates.c.id == template_id)
                .values(reports=templates.c.reports + 1, disabled=True)
            )

    def get_template(self, template_id: str) -> dict | None:
        with self.engine.connect() as c:
            row = (
                c.execute(select(templates).where(templates.c.id == template_id)).mappings().first()
            )
            return dict(row) if row else None

    # ------------------------------------------------------------------ taste

    def save_feedback(self, user_id: str, book_id: str, rating: int, tags: list[str]) -> dict:
        book = self.get_book(user_id, book_id)
        if book is None:
            raise KeyError(book_id)
        with self.engine.begin() as c:
            c.execute(
                delete(feedback).where(feedback.c.book_id == book_id, feedback.c.user_id == user_id)
            )
            c.execute(
                insert(feedback).values(
                    book_id=book_id,
                    user_id=user_id,
                    child_id=book["child_id"],
                    rating=rating,
                    tags=sorted(set(tags)),
                    created_at=time.time(),
                )
            )
        if book["template_id"]:
            self._recount_template(book["template_id"])
        return book

    def _recount_template(self, template_id: str) -> None:
        """Likes/dislikes from distinct families; three families saying 'not for us' (and more
        dislikes than likes) takes a template out of sharing. One account can't do it alone."""
        q = (
            select(
                feedback.c.user_id,
                func.max(feedback.c.rating).label("best"),
                func.min(feedback.c.rating).label("worst"),
            )
            .select_from(feedback.join(books, feedback.c.book_id == books.c.id))
            .where(books.c.template_id == template_id)
            .group_by(feedback.c.user_id)
        )
        with self.engine.begin() as c:
            rows = c.execute(q).mappings().all()
            likes = sum(1 for r in rows if r["best"] > 0)
            dislikes = sum(1 for r in rows if r["worst"] < 0)
            values: dict[str, Any] = {"likes": likes, "dislikes": dislikes}
            if dislikes >= 3 and dislikes > likes:
                values["disabled"] = True
            c.execute(update(templates).where(templates.c.id == template_id).values(**values))

    def get_feedback(self, user_id: str, book_id: str) -> dict | None:
        with self.engine.connect() as c:
            row = (
                c.execute(
                    select(feedback).where(
                        feedback.c.book_id == book_id, feedback.c.user_id == user_id
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def child_history(self, user_id: str, child_id: str) -> tuple[dict, list[dict]]:
        """The child, plus their books with any feedback, newest first."""
        with self.engine.connect() as c:
            child = (
                c.execute(
                    select(children).where(children.c.id == child_id, children.c.user_id == user_id)
                )
                .mappings()
                .first()
            )
            rows = (
                c.execute(
                    select(
                        books.c.id,
                        books.c.brief,
                        books.c.page_count,
                        books.c.progress_page,
                        books.c.read_count,
                        books.c.last_read_at,
                        books.c.created_at,
                        feedback.c.rating,
                        feedback.c.tags,
                        feedback.c.created_at.label("feedback_at"),
                    )
                    .select_from(books.outerjoin(feedback, feedback.c.book_id == books.c.id))
                    .where(books.c.user_id == user_id, books.c.child_id == child_id)
                    .order_by(books.c.created_at.desc())
                )
                .mappings()
                .all()
            )
        return (dict(child) if child else {}), [dict(r) for r in rows]

    def list_children(self, user_id: str) -> list[dict]:
        with self.engine.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(children)
                    .where(children.c.user_id == user_id)
                    .order_by(children.c.created_at)
                ).mappings()
            ]

    def find_child(self, user_id: str, name: str) -> dict | None:
        with self.engine.connect() as c:
            row = (
                c.execute(
                    select(children).where(
                        children.c.user_id == user_id, func.lower(children.c.name) == name.lower()
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def reset_taste(self, user_id: str, child_id: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                update(children)
                .where(children.c.id == child_id, children.c.user_id == user_id)
                .values(taste_reset_at=time.time())
            )

    # ------------------------------------------------------------------ name spellings

    def name_spelling(self, latin: str) -> str | None:
        with self.engine.connect() as c:
            return c.execute(
                select(names.c.devanagari).where(names.c.latin == latin.lower())
            ).scalar_one_or_none()

    def save_name_spelling(self, latin: str, devanagari: str) -> None:
        with self.engine.begin() as c:
            if self.name_spelling(latin) is None:
                c.execute(insert(names).values(latin=latin.lower(), devanagari=devanagari))


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
