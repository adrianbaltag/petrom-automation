"""Tests for the dashboard rows: month total, max carried forward, %, colour level."""

from datetime import date

import pytest
from db_helpers import open_db

from petrom_dashboard.dashboard import (
    STATUS_CRITICAL,
    STATUS_OK,
    STATUS_OVER,
    STATUS_UNSET,
    STATUS_WARNING,
    current_month,
    month_label,
    month_rows,
    percent_of_max,
    status_for,
)
from petrom_dashboard.db import init_db

MAX = 1000_00  # 1.000,00 lei


@pytest.mark.parametrize(
    ("total", "status"),
    [
        (0, STATUS_OK),
        (500_00, STATUS_OK),  # exactly 50% is still white
        (500_01, STATUS_WARNING),  # one ban over 50% turns orange
        (750_00, STATUS_WARNING),  # exactly 75% is still orange
        (750_01, STATUS_CRITICAL),
        (999_99, STATUS_CRITICAL),
        (1000_00, STATUS_OVER),  # reaching the max is over the limit
        (5000_00, STATUS_OVER),
    ],
)
def test_colour_level_uses_exact_bani(total, status):
    assert status_for(total, MAX) == status


@pytest.mark.parametrize("max_bani", [None, 0])
def test_no_usable_max_is_unset(max_bani):
    assert status_for(123_00, max_bani) == STATUS_UNSET


@pytest.mark.parametrize(
    ("total", "percent"),
    [(0, 0), (620_00, 62), (999_99, 99), (1000_00, 100), (1234_56, 123)],
)
def test_percent_is_rounded_down(total, percent):
    assert percent_of_max(total, MAX) == percent


@pytest.mark.parametrize("max_bani", [None, 0])
def test_percent_without_a_usable_max_is_none(max_bani):
    assert percent_of_max(123_00, max_bani) is None


def test_current_month():
    assert current_month(date(2026, 11, 7)) == "2026-11"


def test_month_label_is_romanian():
    assert month_label("2026-11") == "noiembrie 2026"
    assert month_label("2026-01") == "ianuarie 2026"


@pytest.fixture()
def db_file(tmp_path):
    path = tmp_path / "petrom.db"
    init_db(path)
    return path


def add_company(conn, cui, nume, arhivat=0):
    cur = conn.execute(
        "INSERT INTO firme (cui, nume, arhivat) VALUES (?, ?, ?)", (cui, nume, arhivat)
    )
    return cur.lastrowid


def add_max(conn, firma_id, luna, max_bani):
    conn.execute(
        "INSERT INTO limite (firma_id, luna, max_bani) VALUES (?, ?, ?)",
        (firma_id, luna, max_bani),
    )


def add_invoice(conn, firma_id, data_factura, total_bani):
    n = conn.execute("SELECT COUNT(*) FROM facturi").fetchone()[0] + 1
    conn.execute(
        "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (firma_id, data_factura, total_bani, f"f{n}.pdf", f"amp{n}", f"nr{n}"),
    )


def rows_by_cui(db_file, luna):
    with open_db(db_file) as conn:
        return {row["cui"]: row for row in month_rows(conn, luna)}


def test_month_total_counts_only_that_months_invoices(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-11", MAX)
        add_invoice(conn, alfa, "2026-10-31", 50_00)  # last month: not counted
        add_invoice(conn, alfa, "2026-11-01", 400_00)
        add_invoice(conn, alfa, "2026-11-30", 220_00)
        add_invoice(conn, alfa, "2026-12-01", 70_00)  # next month: not counted

    row = rows_by_cui(db_file, "2026-11")["111"]

    assert row["total_bani"] == 620_00
    assert row["max_bani"] == MAX
    assert row["procent"] == 62
    assert row["stare"] == STATUS_WARNING
    assert row["nume"] == "ALFA SRL"


def test_company_without_invoices_shows_zero(db_file):
    with open_db(db_file) as conn:
        beta = add_company(conn, "222", "BETA SRL")
        add_max(conn, beta, "2026-11", MAX)

    row = rows_by_cui(db_file, "2026-11")["222"]

    assert row["total_bani"] == 0
    assert row["procent"] == 0
    assert row["stare"] == STATUS_OK


def test_max_is_carried_forward_from_an_earlier_month(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-06", 500_00)
        add_max(conn, alfa, "2026-09", 800_00)

    assert rows_by_cui(db_file, "2026-11")["111"]["max_bani"] == 800_00
    assert rows_by_cui(db_file, "2026-07")["111"]["max_bani"] == 500_00


def test_a_later_months_max_is_not_used(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-12", MAX)
        add_invoice(conn, alfa, "2026-11-05", 10_00)

    row = rows_by_cui(db_file, "2026-11")["111"]

    assert row["max_bani"] is None
    assert row["procent"] is None
    assert row["stare"] == STATUS_UNSET


def test_archived_companies_are_left_out(db_file):
    with open_db(db_file) as conn:
        add_company(conn, "111", "ALFA SRL")
        add_company(conn, "999", "VECHE SRL", arhivat=1)

    assert set(rows_by_cui(db_file, "2026-11")) == {"111"}


def test_rows_carry_display_text(db_file):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-11", MAX)
        add_invoice(conn, alfa, "2026-11-02", 1234_56)
        add_company(conn, "222", "BETA SRL")

    rows = rows_by_cui(db_file, "2026-11")

    assert rows["111"]["suma_text"] == "1.234,56 lei"
    assert rows["111"]["max_text"] == "1.000,00 lei"
    assert rows["111"]["procent_text"] == "123%"
    assert rows["111"]["eticheta"] == "PESTE LIMITĂ"
    assert rows["222"]["max_text"] == "Max nesetat"
    assert rows["222"]["procent_text"] == "—"
    assert rows["222"]["eticheta"] == "Max nesetat"


def test_a_max_of_zero_is_shown_as_unset_and_logged(db_file, caplog):
    with open_db(db_file) as conn:
        alfa = add_company(conn, "111", "ALFA SRL")
        add_max(conn, alfa, "2026-11", 0)
        add_invoice(conn, alfa, "2026-11-05", 10_00)

    with caplog.at_level("WARNING", logger="petrom_dashboard.dashboard"):
        row = rows_by_cui(db_file, "2026-11")["111"]

    assert row["max_bani"] is None  # the page puts None rows last when sorting
    assert row["max_text"] == "Max nesetat"
    assert row["stare"] == STATUS_UNSET
    assert "111" in caplog.text and "max of 0" in caplog.text
