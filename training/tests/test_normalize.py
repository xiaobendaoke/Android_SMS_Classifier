"""Tests for normalize module."""
from src.normalize import normalize_text


def test_nfkc_fullwidth_digits():
    assert normalize_text("１２３") == "123"


def test_zero_width_removed():
    assert normalize_text("a\u200bb") == "ab"


def test_whitespace_collapsed():
    assert normalize_text("hello   world") == "hello world"


def test_confusables_mapping():
    confusables = {"а": "a"}  # Cyrillic a -> Latin a
    assert normalize_text("а", confusables=confusables) == "a"
