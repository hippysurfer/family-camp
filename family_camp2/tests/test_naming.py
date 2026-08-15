from datetime import datetime

from family_camp2.naming import run_folder_name, slugify


def test_slugify_lowercases_and_replaces_whitespace():
    assert slugify("Willesley 2026") == "willesley_2026"


def test_slugify_collapses_punctuation_runs():
    assert slugify("Willesley -- 2026!!") == "willesley_2026"


def test_slugify_strips_leading_and_trailing_punctuation():
    assert slugify("  Willesley 2026  ") == "willesley_2026"


def test_slugify_falls_back_to_camp_for_an_empty_or_punctuation_only_name():
    assert slugify("") == "camp"
    assert slugify("   ") == "camp"
    assert slugify("!!!") == "camp"


def test_run_folder_name_combines_slug_and_timestamp():
    when = datetime(2026, 8, 15, 13, 3, 0)
    assert run_folder_name("Willesley 2026", when) == "willesley_2026_20260815_130300"
