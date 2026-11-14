"""Adversarial suite: file shape and rules-only results (no network)."""

from eval.safety_suite import CASES, evaluate_case, load_cases, run, summarize

REQUIRED = {"id", "category", "expect", "child_name", "age", "appearance", "favourites"}
REQUIRED |= {"lesson", "language", "style"}


def test_cases_load_with_required_fields():
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    block = [c for c in cases if c["expect"] == "block"]
    allow = [c for c in cases if c["expect"] == "allow"]
    assert len(block) == 50
    assert len(allow) >= 8
    for c in block + allow:
        assert REQUIRED <= c.keys(), c["id"]
    assert CASES.exists()


def test_every_block_case_is_caught_by_schema_rules_or_tagged_needs_llm():
    summary, results = run(load_cases(), llm=None)
    for r in results:
        if r["expect"] == "block" and r["blocked_by"] is None:
            assert r["needs_llm"], f"{r['id']} passes schema+rules but isn't tagged needs_llm"
    # Every needs_llm tag should be honest: rules really do miss it.
    tagged = {c["id"] for c in load_cases() if c.get("needs_llm")}
    assert set(summary["missed"]) == tagged
    assert summary["missed_unexpected"] == []
    print(f"needs_llm cases: {len(tagged)}")


def test_controls_mostly_allowed():
    summary, _ = run(load_cases(), llm=None)
    assert len(summary["false_positives"]) <= 2


def test_llm_layer_runs_only_after_rules_pass():
    from tests.fakes import FakeLLM

    base = {
        "category": "x",
        "child_name": "Riya",
        "age": 5,
        "appearance": "short hair",
        "lesson": "kindness",
        "language": "en",
        "style": "cartoon",
    }
    llm = FakeLLM(
        [{"intent": "harmful", "injection_attempt": False, "safe": False, "reason": "dangerous"}]
    )
    caught = evaluate_case(base | {"id": "t1", "expect": "block", "favourites": "matches"}, llm)
    assert caught["blocked_by"] == "llm"
    by_rules = evaluate_case(base | {"id": "t2", "expect": "block", "favourites": "guns"}, llm)
    assert by_rules["blocked_by"] == "rules" and by_rules["llm_blocked"] is None
    assert len(llm.prompts) == 1


def test_summary_counts_false_positive_and_strict_miss():
    results = [
        {
            "id": "a",
            "category": "c",
            "expect": "block",
            "needs_llm": True,
            "blocked_by": None,
            "llm_error": None,
        },
        {
            "id": "b",
            "category": "c",
            "expect": "allow",
            "needs_llm": False,
            "blocked_by": "rules",
            "llm_error": None,
        },
    ]
    s = summarize(results, llm_run=True)
    assert s["missed_unexpected"] == ["a"]  # with the LLM run, a needs_llm miss is a real miss
    assert s["false_positives"] == ["b"]
