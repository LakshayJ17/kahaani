import pytest

from kahaani.cache import DiskCache, cache_key
from kahaani.config import Settings
from kahaani.providers.errors import ProviderError, TransientError
from kahaani.providers.llm_base import parse_json_object
from kahaani.providers.llm_chain import FallbackLLM, build_llm
from kahaani.providers.retry import with_retries
from kahaani.schemas import Story
from tests.fakes import FakeLLM, story_dict


def test_cache_key_is_stable_and_order_sensitive():
    assert cache_key("a", {"x": 1, "y": 2}) == cache_key("a", {"y": 2, "x": 1})
    assert cache_key("ab", "c") != cache_key("a", "bc")


def test_disk_cache_roundtrip(tmp_path):
    c = DiskCache(tmp_path)
    assert c.get("k" * 64) is None
    c.set("k" * 64, {"नाम": "मीरा"})
    assert c.get("k" * 64) == {"नाम": "मीरा"}


def test_llm_uses_cache(tmp_path):
    llm = FakeLLM([story_dict()], cache=DiskCache(tmp_path))
    first = llm.generate_json("p", Story)
    second = llm.generate_json("p", Story)  # would fail if it called the fake again
    assert first == second and len(llm.prompts) == 1


def test_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr("kahaani.providers.retry.time.sleep", lambda s: None)
    llm = FakeLLM([TransientError("429"), TransientError("503"), story_dict()])
    assert llm.generate_json("p", Story)["hero_name"] == "Meera"


def test_retry_gives_up():
    calls = []

    def fail():
        calls.append(1)
        raise TransientError("429")

    with pytest.raises(TransientError):
        with_retries(fail, attempts=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_non_transient_not_retried():
    llm = FakeLLM([ProviderError("400"), story_dict()])
    with pytest.raises(ProviderError):
        llm.generate_json("p", Story)
    assert len(llm.prompts) == 1


def test_fallback_moves_to_next_provider():
    broken = FakeLLM([ProviderError("down")])
    backup = FakeLLM([story_dict()])
    out = FallbackLLM([broken, backup]).generate_json("p", Story)
    assert out["hero_name"] == "Meera"


def test_fallback_all_fail():
    with pytest.raises(ProviderError, match="all LLM providers failed"):
        FallbackLLM([FakeLLM([ProviderError("a")]), FakeLLM([ProviderError("b")])]).generate_json(
            "p", Story
        )


def test_build_llm_skips_providers_without_keys(tmp_path):
    s = Settings(
        gemini_api_key=None,
        gemini_models=("g",),
        groq_api_key="k",
        groq_model="m",
        llm_order=("gemini", "groq"),
        cache_dir=tmp_path,
        cache_enabled=False,
    )
    assert [p.name for p in build_llm(s).providers] == ["groq"]


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', '  ```\n{"a":1}```'])
def test_parse_json_object(text):
    assert parse_json_object(text) == {"a": 1}


@pytest.mark.parametrize("text", ["not json", "[1, 2]"])
def test_parse_json_object_rejects(text):
    with pytest.raises(ProviderError):
        parse_json_object(text)


def test_long_retry_after_gives_up_at_once():
    from kahaani.providers.errors import QuotaExhausted

    slept = []

    def fail():
        raise TransientError("429", retry_after=75000)

    with pytest.raises(QuotaExhausted):
        with_retries(fail, sleep=slept.append)
    assert slept == []


def test_short_retry_after_is_honoured():
    calls, slept = [], []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise TransientError("429", retry_after=30)
        return "ok"

    assert with_retries(flaky, sleep=slept.append) == "ok"
    assert slept[0] >= 30


def test_quota_exhausted_falls_back():
    a = FakeLLM([TransientError("429", retry_after=75000)])
    b = FakeLLM([story_dict()])
    assert FallbackLLM([a, b]).generate_json("p", Story)["hero_name"] == "Meera"


def test_gemini_retry_delay_parsing():
    from kahaani.providers.llm_gemini import _retry_delay

    body = {"error": {"details": [{"violations": []}, {"retryDelay": "75545s"}]}}
    assert _retry_delay(body) == 75545
    assert _retry_delay({"error": {}}) is None
    assert _retry_delay(None) is None


def test_build_llm_chains_gemini_models(tmp_path):
    s = Settings(
        gemini_api_key="k",
        gemini_models=("a", "b"),
        groq_api_key="k",
        groq_model="m",
        llm_order=("gemini", "groq"),
        cache_dir=tmp_path,
        cache_enabled=False,
    )
    chain = build_llm(s)
    assert [(p.name, p.model) for p in chain.providers] == [
        ("gemini", "a"),
        ("gemini", "b"),
        ("groq", "m"),
    ]


def test_failed_provider_is_skipped_then_retried_after_cooldown():
    now = [0.0]
    broken = FakeLLM([ProviderError("503"), story_dict()])
    backup = FakeLLM([story_dict(), story_dict()])
    chain = FallbackLLM([broken, backup], clock=lambda: now[0])

    chain.generate_json("p1", Story)
    assert chain.last_used == "fake/fake-model" and len(broken.prompts) == 1

    chain.generate_json("p2", Story)  # broken is cooling down: not called
    assert len(broken.prompts) == 1 and len(backup.prompts) == 2

    now[0] = 10_000
    chain.generate_json("p3", Story)  # cooldown over: broken is tried again
    assert len(broken.prompts) == 2


def test_all_cooling_down_still_tries():
    now = [0.0]
    a = FakeLLM([ProviderError("x"), story_dict()])
    chain = FallbackLLM([a], clock=lambda: now[0])
    with pytest.raises(ProviderError):
        chain.generate_json("p1", Story)
    assert chain.generate_json("p2", Story)["hero_name"] == "Meera"
