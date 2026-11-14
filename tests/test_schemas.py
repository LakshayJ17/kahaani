import pytest
from pydantic import ValidationError

from kahaani.schemas import Brief

BASE = dict(
    child_name="Meera",
    age=5,
    appearance="curly hair",
    favourites="elephants",
    lesson="sharing",
    language="en",
    style="cartoon",
)


def test_valid_brief_defaults_to_four_pages():
    assert Brief(**BASE).pages == 4


@pytest.mark.parametrize("age", [2, 9])
def test_age_out_of_range(age):
    with pytest.raises(ValidationError):
        Brief(**{**BASE, "age": age})


@pytest.mark.parametrize("name", ["Meera2", "Robert'); DROP", "", "   ", "a" * 21])
def test_bad_names_rejected(name):
    with pytest.raises(ValidationError):
        Brief(**{**BASE, "child_name": name})


@pytest.mark.parametrize("name", ["Meera Rao", "श्रेया", "  Aarav  "])
def test_good_names_accepted(name):
    assert Brief(**{**BASE, "child_name": name}).child_name == name.strip()


def test_custom_lesson_required():
    with pytest.raises(ValidationError):
        Brief(**{**BASE, "lesson": "custom"})
    b = Brief(**{**BASE, "lesson": "custom", "custom_lesson": "saying thank you"})
    assert b.lesson_text == "saying thank you"


def test_custom_lesson_dropped_for_fixed_lessons():
    assert Brief(**{**BASE, "custom_lesson": "ignored"}).custom_lesson is None


def test_pages_must_be_4_or_8():
    with pytest.raises(ValidationError):
        Brief(**{**BASE, "pages": 6})


def test_long_fields_rejected():
    with pytest.raises(ValidationError):
        Brief(**{**BASE, "favourites": "x" * 101})
