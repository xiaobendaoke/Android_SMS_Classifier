"""Tests for metrics module."""
import math

from src.metrics import wilson_interval, per_class_prf, macro_f1


def test_wilson_interval_bounds():
    low, high = wilson_interval(8, 10)
    assert 0.0 <= low <= high <= 1.0
    assert low < 0.9 < high


def test_wilson_zero_total():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_macro_f1_perfect():
    labels = ["TRANSACTION", "AD", "HARASS", "FRAUD"]
    assert macro_f1(labels, labels) == 1.0
