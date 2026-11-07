"""Tests for parse_amount: invoice amount text -> whole bani (int)."""

import pytest

from petrom_dashboard.money import AmountError, parse_amount


@pytest.mark.parametrize(
    ("text", "bani"),
    [
        # No separator: whole lei.
        ("100", 10000),
        ("100 lei", 10000),
        ("100 LEI", 10000),
        ("0", 0),
        # 1-2 digits after the last separator: decimals.
        ("199.89", 19989),
        ("199,89", 19989),
        ("199.8", 19980),
        ("199,8", 19980),
        ("0.05", 5),
        ("1234.56", 123456),
        # 3 digits after the last separator: thousands (money never has 3 decimals).
        ("1.234", 123400),
        ("1,234", 123400),
        # Thousands, then decimals.
        ("1,234.56", 123456),
        ("1.234,56", 123456),
        ("1.234,5", 123450),
        # Higher amounts.
        ("1234567.89", 123456789),
        ("1.234.567,89", 123456789),
        ("1,234,567.89", 123456789),
        ("1 234 567,89", 123456789),
        ("1 234 567,89", 123456789),  # non-breaking spaces
        ("1.234.567", 123456700),
        ("1 234", 123400),
        # Spaces around are fine.
        ("  199.89  ", 19989),
        ("199.89 lei", 19989),
    ],
)
def test_parse_amount_valid(text, bani):
    assert parse_amount(text) == bani


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "lei",
        "12.3456",  # 4 digits after the separator
        "1.23.456",  # middle group not 3 digits
        "1,234.567.89",  # mixed thousands separators
        "1,234.567",  # mixed separators, no decimals
        "1.234.56",  # same separator used for thousands and decimals
        ".89",  # nothing before the decimal separator
        "199.",  # nothing after the separator
        "1234.567,89",  # first group longer than 3 digits when grouped
        "-5",
        "12a",
        "1..5",
        "1 234 5",  # last space group not 3 digits
    ],
)
def test_parse_amount_rejects_unclear_or_broken(text):
    with pytest.raises(AmountError):
        parse_amount(text)


def test_parse_amount_rejects_non_text():
    with pytest.raises(AmountError):
        parse_amount(None)


def test_amount_error_is_a_value_error():
    # Callers can catch it as a plain ValueError too.
    assert issubclass(AmountError, ValueError)
