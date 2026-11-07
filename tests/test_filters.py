"""Tests for the M6 filters: date ranges, the month list and the rows for a date range."""

from datetime import date

import pytest
from db_helpers import open_db
from test_dashboard import MAX, add_company, add_invoice, add_max

from petrom_dashboard.dashboard import (
    PeriodError,
    edit_max_inputs,
    last_days,
    month_choices,
    period_from_args,
    range_label,
    range_rows,
)
from petrom_dashboard.db import init_db

TODAY = date(2026, 11, 7)


@pytest.fixture()
def db_file(tmp_path):
    path = tmp_path / "petrom.db"
    init_db(path)
    return path


# --- last 7 / 30 days ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "today", "start"),
    [
        (7, date(2026, 11, 7), date(2026, 11, 1)),  # today plus the 6 days before
        (30, date(2026, 11, 7), date(2026, 10, 9)),
        (7, date(2026, 1, 3), date(2025, 12, 28)),  # crosses into last year
        (30, date(2024, 3, 15), date(2024, 2, 15)),  # leap year: February has 29 days
        (30, date(2026, 3, 15), date(2026, 2, 14)),  # normal year: 28 days
        (7, date(2026, 3, 1), date(2026, 2, 23)),
    ],
)
def test_last_days_ends_today(days, today, start):
    assert last_days(days, today) == (start, today)


# --- reading the filter from the page's request ----------------------------------------


def test_no_filter_means_this_month():
    period = period_from_args({}, TODAY)
    assert period.luna == "2026-11"
    assert period.titlu == "noiembrie 2026"


def test_a_past_month():
    period = period_from_args({"luna": "2026-09"}, TODAY)
    assert period.luna == "2026-09"
    assert period.titlu == "septembrie 2026"


@pytest.mark.parametrize("days", ["7", "30"])
def test_last_days_filter(days):
    period = period_from_args({"zile": days}, TODAY)
    assert period.luna is None
    assert period.end == TODAY
    assert (period.end - period.start).days == int(days) - 1


def test_calendar_range():
    period = period_from_args({"de": "2026-10-25", "pana": "2026-11-03"}, TODAY)
    assert (period.start, period.end) == (date(2026, 10, 25), date(2026, 11, 3))
    assert period.luna is None


def test_calendar_range_of_one_day_is_allowed():
    period = period_from_args({"de": "2026-11-07", "pana": "2026-11-07"}, TODAY)
    assert period.start == period.end == TODAY


def test_calendar_range_has_no_length_limit():
    period = period_from_args({"de": "2019-01-01", "pana": "2026-11-07"}, TODAY)
    assert period.start == date(2019, 1, 1)


@pytest.mark.parametrize(
    ("args", "words"),
    [
        ({"de": "2026-11-01"}, "ambele"),  # Până la missing
        ({"pana": "2026-11-01"}, "ambele"),  # De la missing
        ({"de": "", "pana": ""}, "ambele"),
        ({"de": "2026-11-05", "pana": "2026-11-01"}, "înainte"),  # wrong order
        ({"de": "2026-11-01", "pana": "2026-11-08"}, "viitor"),  # tomorrow
        ({"de": "2026-11-08", "pana": "2026-11-09"}, "viitor"),
        ({"de": "2026-02-30", "pana": "2026-03-01"}, "greșită"),  # no such day
        ({"de": "07.11.2026", "pana": "2026-11-07"}, "greșită"),
        ({"de": "20261101", "pana": "2026-11-07"}, "greșită"),  # Python would accept this
        ({"zile": "10"}, "necunoscut"),
        ({"zile": "abc"}, "necunoscut"),
        ({"luna": "2026-13"}, "greșită"),
        ({"luna": "2026-1"}, "greșită"),
        ({"luna": "noiembrie"}, "greșită"),
        ({"luna": "2026-12"}, "viitor"),
    ],
)
def test_bad_filters_are_refused_in_romanian(args, words):
    with pytest.raises(PeriodError) as err:
        period_from_args(args, TODAY)
    assert words in err.value.mesaj


def test_two_filters_at_once_are_refused():
    with pytest.raises(PeriodError):
        period_from_args({"luna": "2026-11", "zile": "7"}, TODAY)


# --- the range title -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "text"),
    [
        (date(2026, 11, 1), date(2026, 11, 7), "1 – 7 noiembrie 2026"),
        (date(2026, 10, 9), date(2026, 11, 7), "9 octombrie – 7 noiembrie 2026"),
        (date(2025, 12, 28), date(2026, 1, 3), "28 decembrie 2025 – 3 ianuarie 2026"),
        (date(2026, 11, 7), date(2026, 11, 7), "7 noiembrie 2026"),
    ],
)
def test_range_label_is_romanian(start, end, text):
    assert range_label(start, end) == text


# --- rows for a date range -------------------------------------------------------------


def rows_by_cui(db_file, start, end):
    with open_db(db_file) as conn:
        return {row["cui"]: row for row in range_rows(conn, start, end)}


def test_range_counts_invoices_on_both_edge_days(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_invoice(conn, alfa, "2026-10-31", 1_00)  # the day before: not counted
        add_invoice(conn, alfa, "2026-11-01", 10_00)  # first day: counted
        add_invoice(conn, alfa, "2026-11-04", 200_00)
        add_invoice(conn, alfa, "2026-11-07", 3000_00)  # last day: counted
        add_invoice(conn, alfa, "2026-11-08", 9_00)  # the day after: not counted

    row = rows_by_cui(db_file, date(2026, 11, 1), date(2026, 11, 7))["111"]

    assert row["total_bani"] == 3210_00
    assert row["suma_text"] == "3.210,00 lei"
    assert row["nume"] == "ALFA SRL"


def test_range_shows_every_active_company_even_with_zero(db_file):
    with open_db(db_file) as conn:
        add_company(conn, "111", "ALFA SRL")
        veche = add_company(conn, "999", "VECHE SRL", arhivat=1)
        add_invoice(conn, veche, "2026-11-03", 50_00)  # archived: still left out

    rows = rows_by_cui(db_file, date(2026, 11, 1), date(2026, 11, 7))

    assert set(rows) == {"111"}
    assert rows["111"]["total_bani"] == 0
    assert rows["111"]["suma_text"] == "0,00 lei"


def test_range_rows_carry_no_max_or_colour(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-11", MAX)
        add_invoice(conn, alfa, "2026-11-02", 5000_00)

    row = rows_by_cui(db_file, date(2026, 11, 1), date(2026, 11, 7))["111"]

    assert row["stare"] == ""
    assert "max_bani" not in row
    assert "procent" not in row


# --- the month list --------------------------------------------------------------------


def test_month_list_without_invoices_is_just_this_month(db_file):
    with open_db(db_file) as conn:
        assert month_choices(conn, TODAY) == [{"luna": "2026-11", "text": "noiembrie 2026"}]


def test_month_list_goes_back_to_the_oldest_invoice_newest_first(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_invoice(conn, alfa, "2026-09-15", 1_00)
        add_invoice(conn, alfa, "2025-12-03", 1_00)  # the oldest: December last year

    with open_db(db_file) as conn:
        months = [m["luna"] for m in month_choices(conn, TODAY)]

    assert months == [
        "2026-11", "2026-10", "2026-09", "2026-08", "2026-07", "2026-06",
        "2026-05", "2026-04", "2026-03", "2026-02", "2026-01", "2025-12",
    ]  # fmt: skip


def test_month_list_counts_archived_companies_invoices_too(db_file):
    # Restoring a company brings its history back, so its months stay in the list.
    with open_db(db_file) as conn:
        veche = add_company(conn, "999", "VECHE SRL", arhivat=1)
        add_invoice(conn, veche, "2026-10-02", 1_00)

    with open_db(db_file) as conn:
        assert [m["luna"] for m in month_choices(conn, TODAY)] == ["2026-11", "2026-10"]


def test_month_list_ignores_an_invoice_dated_in_the_future(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_invoice(conn, alfa, "2027-02-01", 1_00)

    with open_db(db_file) as conn:
        assert [m["luna"] for m in month_choices(conn, TODAY)] == ["2026-11"]


# --- the edit window's max box ---------------------------------------------------------


def test_edit_box_always_gets_this_months_max(db_file):
    # Looking at September must not fill the edit box with September's max: saving the
    # form would then quietly set it as this month's max.
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-09", 500_00)
        add_max(conn, alfa, "2026-11", 800_00)
        beta = add_company(conn, "222", "BETA SRL")
        gama = add_company(conn, "333", "GAMA SRL")
        add_max(conn, gama, "2026-11", 0)  # an old stored 0 counts as unset

    with open_db(db_file) as conn:
        boxes = edit_max_inputs(conn, "2026-11")

    assert boxes == {alfa: "800,00", beta: "", gama: ""}
