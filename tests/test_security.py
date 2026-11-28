"""Abuse and privacy checks: limits that hold under bursts, sign-in rules, request sizes,
security headers, and shared stories that never carry (or mangle) a child's name."""

import asyncio
import http.server
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from kahaani import api, auth
from kahaani import blobs as blobs_module
from kahaani.db import Store, books, templates, usage, users
from kahaani.library import anonymise, personalise, still_named
from kahaani.pipeline import assembler
from kahaani.schemas import CharacterSheet, Page, Story
from tests.test_api import FORM, as_user, make_book, signup, wait

FAVOURITES = ["tigers", "boats", "kites", "drums", "stars", "trains", "owls", "bees"]


def _start(client, user, i=0, **changes):
    body = {**FORM, "favourites": f"{FAVOURITES[i]}, mangoes", "fresh": True, **changes}
    return client.post("/api/books", json=body, headers=as_user(user))


# ----------------------------------------------------------------------------- daily limits


def test_a_burst_of_requests_cannot_pass_the_daily_limit(env):
    client, svc, _ = env
    signup(client, "ana")
    real = svc.store.uses_since

    def slow(*a, **k):  # the database is a network hop away in production
        time.sleep(0.05)
        return real(*a, **k)

    svc.store.uses_since = slow
    with ThreadPoolExecutor(8) as pool:
        rs = list(pool.map(lambda i: _start(client, "ana", i), range(8)))
    started = [r for r in rs if r.status_code == 200]
    assert len(started) == svc.settings.books_per_ip_per_day
    assert all(r.status_code == 429 for r in rs if r not in started)


def test_unsaved_stories_still_count_after_their_draft_expires(env):
    client, svc, _ = env
    signup(client, "ana")
    for i in range(3):
        wait(client, _start(client, "ana", i).json()["id"], "ana")
    for job in svc.all_jobs():  # an hour later the drafts are dropped...
        job.created -= api.JOB_TTL + 1
    svc.expire()
    assert not svc.jobs
    r = _start(client, "ana", 3)  # ...but the stories were written, so they count
    assert r.status_code == 429
    assert client.get("/api/me", headers=as_user("ana")).json()["booksToday"] == 3


def test_a_failed_story_does_not_use_up_the_day(env):
    client, svc, llms = env
    signup(client, "ana")
    _ = svc.maker  # build it, then make the input check refuse everything
    llms["llm"].overrides["_InputVerdict"] = {
        "intent": "off_topic",
        "injection_attempt": False,
        "safe": False,
        "reason": "x",
    }
    view = wait(client, _start(client, "ana").json()["id"], "ana")
    assert view["error"]
    assert client.get("/api/me", headers=as_user("ana")).json()["booksToday"] == 0


def test_hero_redraws_are_capped(env):
    client, _, _ = env
    signup(client, "ana")
    jid = _start(client, "ana").json()["id"]
    wait(client, jid, "ana")
    for _ in range(api.HERO_REDRAWS):
        assert client.post(f"/api/jobs/{jid}/hero", headers=as_user("ana")).status_code == 200
        wait(client, jid, "ana")
    r = client.post(f"/api/jobs/{jid}/hero", headers=as_user("ana"))
    assert r.status_code == 429 and "most we can draw" in r.json()["detail"]
    # Choosing one still works.
    assert client.post(f"/api/jobs/{jid}/approve", headers=as_user("ana")).status_code == 200


def test_page_changes_are_capped_per_day(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(api, "PAGE_CHANGES_PER_DAY", 2)
    signup(client, "ana")
    book = make_book(client, "ana")
    for _ in range(2):
        r = client.post(
            f"/api/library/{book['id']}/pages/1/redo", json={"request": ""}, headers=as_user("ana")
        )
        assert r.status_code == 200
        wait(client, r.json()["id"], "ana")
    r = client.post(
        f"/api/library/{book['id']}/pages/1/redo", json={"request": ""}, headers=as_user("ana")
    )
    assert r.status_code == 429 and "changed 2 pages today" in r.json()["detail"]


# ----------------------------------------------------------------------------- account deletion


def test_account_deletion_waits_for_a_running_book_then_leaves_nothing(env):
    client, svc, _ = env
    signup(client, "ana")
    jid = _start(client, "ana").json()["id"]
    wait(client, jid, "ana")
    real_finish = svc.maker.finish

    def slow_finish(*a, **k):
        time.sleep(0.3)
        return real_finish(*a, **k)

    svc.maker.finish = slow_finish
    client.post(f"/api/jobs/{jid}/approve", headers=as_user("ana"))

    r = client.delete("/api/me", headers=as_user("ana"))
    assert r.status_code == 409 and "still being made" in r.json()["detail"]

    wait(client, jid, "ana")
    assert client.delete("/api/me", headers=as_user("ana")).json()["booksDeleted"] == 1
    with svc.store.engine.connect() as c:
        for col in (books.c.user_id, usage.c.user_id):
            assert c.execute(select(func.count()).where(col == "dev-ana")).scalar_one() == 0
        assert c.execute(select(func.count()).where(users.c.id == "dev-ana")).scalar_one() == 0
        tpl = c.execute(select(templates.c.source_user_id)).scalars().all()
    assert "dev-ana" not in tpl
    left = [p for p in (svc.blobs.root / "books").rglob("*") if p.is_file()]
    assert left == []


def test_work_on_a_dropped_job_is_refused(env):
    client, svc, _ = env
    signup(client, "ana")
    jid = _start(client, "ana").json()["id"]
    wait(client, jid, "ana")
    job = svc.jobs.pop(jid)  # what account deletion does
    with pytest.raises(HTTPException) as e:
        svc.submit(job, "finish", lambda report: None)
    assert e.value.status_code == 404


# ----------------------------------------------------------------------------- requests


def test_large_bodies_are_refused_before_they_are_read(env):
    client, _, _ = env
    body = json.dumps({**FORM, "appearance": "x" * (api.MAX_BODY + 1)})
    r = client.post("/api/books", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_large_bodies_without_a_length_are_cut_off():
    """A chunked body has no content-length; the limit applies as it arrives."""
    from fastapi import FastAPI, Request

    inner = FastAPI()

    @inner.post("/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    app = api.BodyLimit(inner, limit=1000)
    chunks = [b"x" * 400] * 5
    sent = []

    async def receive():
        body = chunks.pop(0) if chunks else b""
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "headers": [(b"transfer-encoding", b"chunked")],
        "query_string": b"",
    }
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 413
    assert len(chunks) == 2  # stopped reading after 1200 bytes


def test_security_headers_on_api_and_site(env):
    client, _, _ = env
    for path in ("/api/health", "/api/me", "/"):
        h = client.get(path).headers
        assert h["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "same-origin"


def test_one_build_for_many_requests_for_the_same_video(env):
    client, svc, _ = env
    signup(client, "ana")
    link = make_book(client, "ana")["videoUrl"]
    builds = []
    lock = threading.Lock()

    def fake_video(user_id, book_id):
        with lock:
            builds.append(book_id)
        time.sleep(0.3)
        return b"mp4"

    svc._video = fake_video
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: client.get(link).status_code, range(6)))
    assert codes == [200] * 6 and len(builds) == 1


def test_build_queue_gives_up_politely():
    builds = api.Builds(wait=0.05)
    started = threading.Event()

    def slow():
        started.set()
        time.sleep(0.5)
        return b"a"

    t = threading.Thread(target=builds.get, args=(("a", "pdf", "v"), slow))
    t.start()
    started.wait()
    with pytest.raises(HTTPException) as e:
        builds.get(("b", "pdf", "v"), lambda: b"b")
    assert e.value.status_code == 503
    t.join()


# ----------------------------------------------------------------------------- sign-in


SECRET = "test-jwt-secret-that-is-long-enough-for-hs256"


def _token(**claims):
    base = {
        "sub": "u1",
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
        "app_metadata": {"provider": "google", "providers": ["google"]},
    }
    return jwt.encode({**base, **claims}, SECRET, algorithm="HS256")


@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")  # no JWKS reachable


def test_google_accounts_are_accepted(jwt_secret):
    assert auth.verify_token(_token()).id == "u1"
    linked = {"provider": "email", "providers": ["email", "google"]}
    assert auth.verify_token(_token(app_metadata=linked)).id == "u1"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _token(app_metadata={"provider": "email"}), id="email sign-up"),
        pytest.param(lambda: _token(app_metadata={"provider": "phone"}), id="phone sign-up"),
        pytest.param(lambda: _token(app_metadata={}), id="no provider"),
        pytest.param(lambda: _token(is_anonymous=True), id="anonymous"),
        pytest.param(lambda: _token(aud="anon"), id="wrong audience"),
        pytest.param(lambda: _token(exp=int(time.time()) - 5), id="expired"),
        pytest.param(
            lambda: jwt.encode({"sub": "u1", "aud": "authenticated"}, SECRET, "HS256"), id="no exp"
        ),
        pytest.param(
            lambda: jwt.encode(
                jwt.decode(_token(), options={"verify_signature": False}), None, "none"
            ),
            id="alg none",
        ),
        pytest.param(
            lambda: jwt.encode(
                jwt.decode(_token(), options={"verify_signature": False}), "x" * 40, "HS256"
            ),
            id="wrong secret",
        ),
    ],
)
def test_other_tokens_are_refused(jwt_secret, token):
    with pytest.raises(HTTPException) as e:
        auth.verify_token(token())
    assert e.value.status_code == 401


# ----------------------------------------------------------------------------- shared stories


def _story(name: str, text: str) -> Story:
    return Story(
        title=f"{name} and the kite",
        hero_name=name,
        character=CharacterSheet(description="a child", outfit="red kurta", companion=None),
        pages=[Page(number=1, text=text, scene="a park", mood="happy")],
    )


@pytest.mark.parametrize(
    "name,text,shared",
    [
        ("Om", "Om ran home to some room.", "{HERO} ran home to some room."),
        ("Ved", "Ved loved Ved's kite.", "{HERO} loved {HERO}'s kite."),
        ("Ana", "Ana ate a banana.", "{HERO} ate a banana."),
        ("Joy", "Joy laughed with joy.", "{HERO} laughed with joy."),
        ("राम", "राम ने आराम किया।", "{HERO} ने आराम किया।"),
    ],
)  # fmt: skip
def test_names_are_replaced_as_whole_words_only(name, text, shared):
    tpl = anonymise(_story(name, text))
    assert tpl["pages"][0]["text"] == shared
    assert tpl["title"] == "{HERO} and the kite"
    assert personalise(tpl, "Riya").pages[0].text == shared.replace("{HERO}", "Riya")


def test_a_name_left_inside_the_story_keeps_it_private():
    assert still_named(anonymise(_story("Joy", "Joy laughed with joy.")), "Joy")
    assert still_named(anonymise(_story("राम", "राम ने आराम किया।")), "राम")
    assert still_named(anonymise(_story("Meera", "Meerajee waved.")), "Meera")
    assert not still_named(anonymise(_story("Meera", "Meera waved.")), "Meera")


def test_such_stories_are_not_shared(env):
    client, svc, _ = env
    signup(client, "ana")
    make_book(client, "ana", child_name="Sun")  # the story says "the sun" too
    with svc.store.engine.connect() as c:
        assert c.execute(select(func.count()).select_from(templates)).scalar_one() == 0
    make_book(client, "ana", child_name="Meera", favourites="kites")
    with svc.store.engine.connect() as c:
        assert c.execute(select(func.count()).select_from(templates)).scalar_one() == 1


# ----------------------------------------------------------------------------- request limits


def test_rate_limit_window_slides_and_forgets_idle_accounts():
    now = [0.0]
    limit = api.RateLimit(2, 60, clock=lambda: now[0])
    limit.check("ana")
    limit.check("ana")
    with pytest.raises(HTTPException) as e:
        limit.check("ana")
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60"
    limit.check("ben")  # one account's burst doesn't block another
    now[0] = 61
    limit.check("ana")  # the old requests have left the window
    now[0] = 200
    limit.sweep()
    assert limit.hits == {}


def test_signed_in_requests_are_limited_per_account(env):
    client, svc, _ = env
    signup(client, "ana")
    svc.requests = api.RateLimit(3, 60)
    codes = [client.get("/api/me", headers=as_user("ana")).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.get("/api/me", headers=as_user("ana"))
    assert "retry-after" in r.headers and r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/me", headers=as_user("ben")).status_code == 200


def test_file_links_are_limited_per_account(env):
    client, svc, _ = env
    signup(client, "ana")
    cover = make_book(client, "ana")["heroUrl"]
    svc.files = api.RateLimit(2, 60)
    assert [client.get(cover).status_code for _ in range(3)] == [200, 200, 429]


def test_only_real_rebuilds_count_towards_the_build_limit(env):
    client, svc, _ = env
    signup(client, "ana")
    book = make_book(client, "ana")
    svc._pdf = lambda user_id, book_id: b"%PDF"
    svc.rebuilds = api.RateLimit(1, 3600)
    assert client.get(book["pdfUrl"]).status_code == 200  # built
    assert client.get(book["pdfUrl"]).status_code == 200  # cached copy, not counted
    svc.builds.drop(book["id"])
    r = client.get(book["pdfUrl"])  # would have to build again
    assert r.status_code == 429 and "this hour" in r.json()["detail"]


# ------------------------------------------------------------------------ never trust the site


def test_a_made_up_page_number_uses_nothing(env):
    client, svc, _ = env
    signup(client, "ana")
    book = make_book(client, "ana")
    for number in (0, 99):
        r = client.post(
            f"/api/library/{book['id']}/pages/{number}/redo",
            json={"request": "add a red kite"},
            headers=as_user("ana"),
        )
        assert r.status_code == 404
    assert svc.store.uses_since(0, "page", "dev-ana") == 0
    assert not [j for j in svc.all_jobs() if j.redo_book_id]


@pytest.mark.parametrize(
    "path, body",
    [
        ("pages/1/redo", {"request": "x" * 201}),
        ("progress", {"page": -1}),
        ("progress", {"page": 101}),
        ("feedback", {"rating": 1, "tags": ["funny"] * 21}),
    ],
)
def test_out_of_range_values_are_refused(env, path, body):
    client, _, _ = env
    signup(client, "ana")
    book = make_book(client, "ana")
    r = client.post(f"/api/library/{book['id']}/{path}", json=body, headers=as_user("ana"))
    assert r.status_code == 422


# ------------------------------------------------------------------------ what is published


def test_no_api_map_or_debug_pages(env):
    client, _, _ = env
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404
    assert client.app.debug is False


def test_content_security_policy_allows_only_the_site_and_supabase():
    csp = api.content_security_policy("https://abc.supabase.co/")
    parts = dict(p.split(" ", 1) for p in csp.split("; "))
    assert parts["default-src"] == "'self'"
    assert parts["connect-src"] == "'self' https://abc.supabase.co"
    assert parts["script-src"] == "'self' 'unsafe-inline'"  # no 'unsafe-eval', no other hosts
    assert parts["object-src"] == "'none'" and parts["frame-ancestors"] == "'none'"
    assert "connect-src 'self';" in api.content_security_policy(None) + ";"


def test_cross_origin_calls_only_from_the_local_dev_site(env, monkeypatch):
    _, svc, _ = env
    preflight = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}

    monkeypatch.delenv("HOST", raising=False)  # running on a laptop
    local = TestClient(api.create_app(svc)).options("/api/books", headers=preflight)
    assert local.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "PUT" not in local.headers["access-control-allow-methods"]

    monkeypatch.setenv("HOST", "0.0.0.0")  # the deployed container
    deployed = TestClient(api.create_app(svc)).options("/api/books", headers=preflight)
    assert "access-control-allow-origin" not in deployed.headers


# ----------------------------------------------------------------------------- PDF renderer


@pytest.mark.parametrize(
    "url, ok",
    [
        ("data:image/jpeg;base64,AAAA", True),
        ((assembler.TEMPLATES / "fonts" / "Baloo2.ttf").as_uri(), True),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("https://example.com/a.png", False),
        ("ftp://example.com/a", False),
        ("file:///etc/passwd", False),
        ((assembler.TEMPLATES / ".." / ".." / ".env").as_uri(), False),
        ("file://other-host/share/x", False),
    ],
)
def test_book_html_can_only_load_its_own_files(url, ok):
    assert assembler.allowed_url(url) is ok


def test_pdf_renderer_makes_no_outside_requests():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    html = (
        "<html><head><style>@font-face { font-family: B; src: url('fonts/Baloo2.ttf'); }"
        f"body {{ font-family: B; background: url('http://127.0.0.1:{port}/css'); }}</style>"
        "<link rel='stylesheet' href='file:///etc/hosts'></head>"
        f"<body>Hello <img src='http://127.0.0.1:{port}/img'></body></html>"
    )
    try:
        pdf = assembler.build_pdf(html)
    except OSError:
        pytest.skip("WeasyPrint's system libraries (pango) aren't installed")
    finally:
        server.shutdown()
    assert pdf.startswith(b"%PDF") and hits == []


# ------------------------------------------------------------------------ storage and admin log


def test_a_public_bucket_is_switched_back_to_private(monkeypatch):
    calls = []

    def fake(method):
        def call(url, **kw):
            calls.append((method, url.rsplit("/storage/v1/", 1)[1], kw.get("json")))
            if method == "post":
                return httpx.Response(409)
            if method == "get":
                return httpx.Response(200, json={"id": "kahaani", "public": True})
            return httpx.Response(200, json={"message": "ok"})

        return call

    for method in ("post", "get", "put"):
        monkeypatch.setattr(blobs_module.httpx, method, fake(method))
    blobs_module.SupabaseBlobs("https://abc.supabase.co", "secret").ensure_bucket()
    assert calls[-1] == (
        "put",
        "bucket/kahaani",
        {"id": "kahaani", "name": "kahaani", "public": False},
    )


def test_admin_changes_are_logged_with_the_change_or_not_at_all(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/k.db")
    store.create_all()
    store.log_admin("template.disable", "t1", "The lost kite")
    with pytest.raises(RuntimeError), store.engine.begin() as c:
        store.log_admin("template.enable", "t1", conn=c)
        raise RuntimeError("the change failed")
    rows = store.admin_actions()
    assert [(r["action"], r["target"], r["detail"]) for r in rows] == [
        ("template.disable", "t1", "The lost kite")
    ]
