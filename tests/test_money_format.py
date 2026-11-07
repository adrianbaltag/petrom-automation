"""Tests for format_lei: whole bani (int) -> Romanian display text."""

import pytest

from petrom_dashboard.money import format_lei


@pytest.mark.parametrize(
    ("bani", "text"),
    [
        (0, "0,00 lei"),
        (5, "0,05 lei"),
        (62000, "620,00 lei"),
        (100000, "1.000,00 lei"),
        (123456, "1.234,56 lei"),
        (123456789, "1.234.567,89 lei"),
    ],
)
def test_formats_bani_as_romanian_lei(bani, text):
    assert format_lei(bani) == text


def test_without_the_lei_suffix():
    assert format_lei(123456, suffix=False) == "1.234,56"
