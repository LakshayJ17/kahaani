"""The web API end to end, with fake AI providers, SQLite and a temp folder (no network)."""

import time

import pytest
from fastapi.testclient import TestClient

from kahaani import api
from kahaani.blobs import LocalBlobs
from kahaani.config import get_settings
from kahaani.db import Store
from tests.fakes import SchemaFakeLLM, story_dict
from tests.test_pipeline import maker as fake_maker

FORM = {
    "child_name": "Meera",
    "age": 5,
    "hero": "girl",
    "appearance": "curly hair, red glasses",
    "favourites": "elephants, mangoes",
    "lesson": "sharing",
    "language": "en",
    "style": "cartoon",
    "pages": 4,
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAHAANI_DEV_AUTH", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    from dataclasses import replace

    settings = replace(
        get_settings(), books_per_ip_per_day=3, global_books_per_day=100, url_secret="test-secret"
    )
    store = Store(f"sqlite:///{tmp_path}/k.db")
    store.create_all()
    blobs = LocalBlobs(tmp_path / "blobs")
    llms = {}

    def factory():
        llm = SchemaFakeLLM()
        llms["llm"] = llm
        return fake_maker(llm)

    svc = api.Service(settings, store, blobs, factory)
    # wait() below polls 20 times a second, far faster than the website; the real per-minute
    # limits have their own tests in test_security.py.
    svc.requests = api.RateLimit(100_000, 60)
    with TestClient(api.create_app(svc)) as client:
        yield client, svc, llms


def as_user(name):
    return {"X-Dev-User": name}


def signup(client, name):
    client.post("/api/me/consent", headers=as_user(name))


def wait(client, job_id, user, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        view = client.get(f"/api/jobs/{job_id}", headers=as_user(user)).json()
        if not view["busy"]:
            return view
        time.sleep(0.05)
    raise AssertionError("job never finished")


def make_book(client, user, **changes):
    r = client.post("/api/books", json={**FORM, **changes}, headers=as_user(user))
    assert r.status_code == 200, r.json()
    if "existingBookId" in r.json():
        return r.json()
    jid = r.json()["id"]
    view = wait(client, jid, user)
    assert view["stage"] == "hero", view["error"]
    client.post(f"/api/jobs/{jid}/approve", headers=as_user(user))
    view = wait(client, jid, user)
    assert view["stage"] == "saved", view
    return client.get(f"/api/library/{view['bookId']}", headers=as_user(user)).json()


# ----------------------------------------------------------------------------- accounts


def test_must_sign_in(env):
    client, *_ = env
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/books", json=FORM).status_code == 401
    assert client.get("/api/library").status_code == 401


def test_must_consent_before_making_books(env):
    client, *_ = env
    assert client.get("/api/me", headers=as_user("ana")).json()["consent"] is False
    assert client.post("/api/books", json=FORM, headers=as_user("ana")).status_code == 403
    signup(client, "ana")
    assert client.get("/api/me", headers=as_user("ana")).json()["consent"] is True


def test_config_exposes_only_public_values(env):
    client, *_ = env
    cfg = client.get("/api/config").json()
    assert set(cfg) == {"supabaseUrl", "supabaseAnonKey", "devAuth"}


# ----------------------------------------------------------------------------- making and reading


def test_full_flow_saves_to_library(env):
    client, svc, _ = env
    signup(client, "ana")
    book = make_book(client, "ana")
    assert book["title"] and len(book["pages"]) == 4 and book["reused"] == "none"
    assert client.get(book["pages"][0]["imageUrl"]).headers["content-type"] == "image/jpeg"
    assert client.get(book["pdfUrl"]).content.startswith(b"%PDF")
    lib = client.get("/api/library", headers=as_user("ana")).json()
    assert lib["children"][0]["childName"] == "Meera"
    assert lib["children"][0]["books"][0]["id"] == book["id"]


def test_reading_progress_and_finishing(env):
    client, *_ = env
    signup(client, "ana")
    book = make_book(client, "ana")
    h = as_user("ana")
    client.post(f"/api/library/{book['id']}/progress", json={"page": 2}, headers=h)
    client.post(f"/api/library/{book['id']}/progress", json={"page": 1}, headers=h)  # going back
    b = client.get(f"/api/library/{book['id']}", headers=h).json()
    assert b["progressPage"] == 2 and b["readCount"] == 0
    client.post(
        f"/api/library/{book['id']}/progress", json={"page": 4, "finished": True}, headers=h
    )
    b = client.get(f"/api/library/{book['id']}", headers=h).json()
    assert b["progressPage"] == 4 and b["readCount"] == 1


def test_same_details_open_the_existing_book(env):
    client, _, llms = env
    signup(client, "ana")
    first = make_book(client, "ana")
    again = client.post(
        "/api/books", json={**FORM, "favourites": "Mangoes, elephants!"}, headers=as_user("ana")
    ).json()
    assert again["existingBookId"] == first["id"]
    fresh = client.post("/api/books", json={**FORM, "fresh": True}, headers=as_user("ana"))
    assert "id" in fresh.json() and "existingBookId" not in fresh.json()


# ----------------------------------------------------------------------------- sharing


def test_matching_idea_reuses_story_and_pictures(env):
    client, svc, llms = env
    signup(client, "ana")
    signup(client, "ben")
    a = make_book(client, "ana")
    stories_written = llms["llm"].calls.count("Story")
    b = make_book(client, "ben", child_name="Tara", favourites="mangoes and elephants")
    assert b["reused"] == "story+pictures"
    assert llms["llm"].calls.count("Story") == stories_written  # no new story written
    assert "Tara" in b["pages"][0]["text"] and "Meera" not in str(b["pages"])
    # The drawings are stored once and shared.
    ra, rb = svc.store.get_book("dev-ana", a["id"]), svc.store.get_book("dev-ben", b["id"])
    assert ra["assets"]["p1"] == rb["assets"]["p1"] and ra["assets"]["a1"] != rb["assets"]["a1"]


def test_different_looks_reuse_story_but_draw_new_pictures(env):
    client, svc, _ = env
    signup(client, "ana")
    signup(client, "ben")
    a = make_book(client, "ana")
    b = make_book(client, "ben", child_name="Tara", appearance="long straight hair, freckles")
    assert b["reused"] == "story"
    ra, rb = svc.store.get_book("dev-ana", a["id"]), svc.store.get_book("dev-ben", b["id"])
    assert ra["assets"]["p1"] != rb["assets"]["p1"]


@pytest.mark.parametrize(
    "change",
    [
        {"lesson": "custom", "custom_lesson": "saying thank you"},  # custom: never shared
        {"hero": "boy", "child_name": "Kabir"},  # Hindi grammar differs by gender
        {"age": 3},  # different reading level
        {"favourites": "rockets, dosa"},  # different idea
        {"language": "hi"},
    ],
)
def test_non_matching_requests_get_a_new_story(env, change):
    client, *_ = env
    signup(client, "ana")
    signup(client, "ben")
    make_book(
        client,
        "ana",
        **(
            {"lesson": "custom", "custom_lesson": "saying thank you"}
            if "custom_lesson" in change
            else {}
        ),
    )
    if change.get("language") == "hi":
        return  # covered in the Hindi test below (needs a Hindi story from the fake)
    b = make_book(client, "ben", **{"child_name": "Tara", **change})
    assert b["reused"] == "none"


def test_hindi_reuse_spells_the_name_in_devanagari(env):
    client, svc, llms = env
    signup(client, "ana")
    signup(client, "ben")
    svc.maker.llm.story = story_dict(lang="hi")  # the fake now writes Hindi stories
    make_book(client, "ana", language="hi")
    b = make_book(client, "ben", language="hi", child_name="Aarav")
    assert b["reused"].startswith("story")
    assert "आरव" in b["pages"][0]["text"] and "मीरा" not in str(b["pages"])
    assert svc.store.name_spelling("Aarav") == "आरव"


def test_report_pulls_template_from_sharing(env):
    client, *_ = env
    for u in ("ana", "ben", "cai"):
        signup(client, u)
    make_book(client, "ana")
    b = make_book(client, "ben", child_name="Tara")
    assert b["reused"] != "none"
    assert client.post(f"/api/library/{b['id']}/report", headers=as_user("ben")).json()["ok"]
    c = make_book(client, "cai", child_name="Zoya")
    assert c["reused"] == "none"


def test_editing_a_shared_book_makes_a_private_copy(env):
    client, svc, _ = env
    signup(client, "ana")
    signup(client, "ben")
    a = make_book(client, "ana")
    b = make_book(client, "ben", child_name="Tara")
    r = client.post(
        f"/api/library/{b['id']}/pages/2/redo",
        json={"request": "add the moon"},
        headers=as_user("ben"),
    )
    wait(client, r.json()["id"], "ben")
    ra, rb = svc.store.get_book("dev-ana", a["id"]), svc.store.get_book("dev-ben", b["id"])
    assert rb["assets"]["p2"].startswith(f"books/{b['id']}/")
    assert ra["assets"]["p2"].startswith("templates/")  # ana's book is untouched
    assert rb["story"]["pages"][1]["text"].startswith("Meera laughs at the moon")
    assert ra["story"]["pages"][1]["text"] != rb["story"]["pages"][1]["text"]


# ----------------------------------------------------------------------------- privacy


def test_families_cannot_see_each_others_books(env):
    client, *_ = env
    signup(client, "ana")
    signup(client, "ben")
    a = make_book(client, "ana")
    assert client.get(f"/api/library/{a['id']}", headers=as_user("ben")).status_code == 404
    assert client.delete(f"/api/library/{a['id']}", headers=as_user("ben")).status_code == 404
    assert client.get("/api/library", headers=as_user("ben")).json()["children"] == []


def test_signed_links_cannot_be_forged_or_reused_for_other_files(env):
    client, svc, _ = env
    signup(client, "ana")
    a = make_book(client, "ana")
    good = a["pages"][0]["imageUrl"]
    assert client.get(good).status_code == 200
    assert client.get(good.replace("/p1.jpg", "/p2.jpg")).status_code == 403
    assert client.get(good[:-3] + "AAA").status_code == 403
    token = good.split("t=")[1]
    assert client.get(f"/api/files/{a['id']}/book.pdf?t={token}").status_code == 403


def test_expired_links_are_refused(env, monkeypatch):
    client, *_ = env
    signup(client, "ana")
    a = make_book(client, "ana")
    monkeypatch.setattr(api, "LINK_TTL", -10)
    stale = client.get(f"/api/library/{a['id']}", headers=as_user("ana")).json()
    assert client.get(stale["pages"][0]["imageUrl"]).status_code == 403


def test_delete_book_and_account(env):
    client, svc, _ = env
    signup(client, "ana")
    signup(client, "ben")
    a = make_book(client, "ana")
    make_book(client, "ana", favourites="rockets")
    b = make_book(client, "ben", child_name="Tara")  # reuses ana's template
    assert client.delete(f"/api/library/{a['id']}", headers=as_user("ana")).json()["ok"]
    assert client.get(b["pages"][0]["imageUrl"]).status_code == 200  # shared drawings stay
    r = client.delete("/api/me", headers=as_user("ana")).json()
    assert r["booksDeleted"] == 1
    assert client.get("/api/library", headers=as_user("ana")).json()["children"] == []
    tpl = svc.store.candidate_templates(1, svc.store.get_book("dev-ben", b["id"])["template_id"])
    assert all(t["source_user_id"] != "dev-ana" for t in tpl)


# ----------------------------------------------------------------------------- limits


def test_daily_limit_per_account(env):
    client, *_ = env
    signup(client, "ana")
    for fav in ("cats", "dogs", "owls"):
        make_book(client, "ana", favourites=fav)
    r = client.post("/api/books", json={**FORM, "favourites": "frogs"}, headers=as_user("ana"))
    assert r.status_code == 429 and "daily limit" in r.json()["error"]["message"]
    signup(client, "ben")  # another family on the same network is unaffected
    assert client.post("/api/books", json=FORM, headers=as_user("ben")).status_code == 200


def test_global_daily_cap(env):
    from dataclasses import replace

    client, svc, _ = env
    svc.settings = replace(svc.settings, global_books_per_day=1)
    for u in ("ana", "ben"):
        signup(client, u)
    make_book(client, "ana")
    r = client.post("/api/books", json={**FORM, "child_name": "Tara"}, headers=as_user("ben"))
    assert r.status_code == 429 and "all the books it can" in r.json()["error"]["message"]


def test_saved_book_cap(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr(api, "MAX_BOOKS_PER_ACCOUNT", 1)
    signup(client, "ana")
    make_book(client, "ana")
    r = client.post("/api/books", json={**FORM, "favourites": "owls"}, headers=as_user("ana"))
    assert r.status_code == 409 and "Delete one" in r.json()["error"]["message"]


def test_form_errors_name_the_field(env):
    client, *_ = env
    signup(client, "ana")
    r = client.post(
        "/api/books", json={**FORM, "child_name": "M3era", "hero": None}, headers=as_user("ana")
    )
    assert r.status_code == 422
    assert set(r.json()["error"]["fields"]) == {"child_name", "hero"}


def test_samples_listed_and_served(env):
    client, *_ = env
    samples = client.get("/api/samples").json()
    assert samples and client.get(samples[0]["coverUrl"]).status_code == 200
    assert client.get("/api/samples/..%2F..%2Fetc/passwd").status_code == 404
