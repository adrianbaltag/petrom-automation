"""Tests for GET /date with the M6 filters (month, last 7 / 30 days, calendar range)."""

from datetime import date

import pytest
from db_helpers import open_db

from petrom_dashboard import dashboard


@pytest.fixture()
def today(monkeypatch):
    monkeypatch.setattr(dashboard, "today", lambda: date(2026, 11, 7))


@pytest.fixture()
def alfa(app, today):
    """ALFA SRL: max 500 lei from September, 800 lei from November, invoices in both."""
    with open_db(app.config["DATABASE"]) as conn:
        conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '111', 'ALFA SRL')")
        conn.execute("INSERT INTO limite VALUES (1, '2026-09', 50000)")
        conn.execute("INSERT INTO limite VALUES (1, '2026-11', 80000)")
        for n, (day, bani) in enumerate(
            [("2026-09-10", 40000), ("2026-10-20", 1000), ("2026-11-02", 2500)], start=1
        ):
            conn.execute(
                "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta,"
                " numar) VALUES (1, ?, ?, ?, ?, ?)",
                (day, bani, f"f{n}.pdf", f"a{n}", f"n{n}"),
            )


def test_no_filter_shows_this_month(client, alfa):
    body = client.get("/date").get_json()

    assert body["ok"] is True
    assert body["tip"] == "luna"
    assert body["luna"] == "2026-11"
    assert body["titlu"] == "noiembrie 2026"
    assert body["firme"][0]["total_bani"] == 2500
    assert body["firme"][0]["stare"] == "ok"


def test_a_past_month_uses_that_months_max(client, alfa):
    body = client.get("/date?luna=2026-09").get_json()

    assert body["tip"] == "luna"
    assert body["titlu"] == "septembrie 2026"
    row = body["firme"][0]
    assert row["total_bani"] == 40000
    assert row["max_bani"] == 50000
    assert row["stare"] == "critic"  # 80% of September's 500 lei


def test_edit_box_shows_this_months_max_in_a_past_month(client, alfa):
    row = client.get("/date?luna=2026-09").get_json()["firme"][0]
    assert row["max_input"] == "800,00"  # this month's max, not September's 500


def test_last_7_days(client, alfa):
    body = client.get("/date?zile=7").get_json()

    assert body["tip"] == "perioada"
    assert body["titlu"] == "1 – 7 noiembrie 2026"
    assert body["de"] == "2026-11-01"
    assert body["pana"] == "2026-11-07"
    row = body["firme"][0]
    assert row["total_bani"] == 2500
    assert row["stare"] == ""
    assert row["max_input"] == "800,00"


def test_last_30_days(client, alfa):
    body = client.get("/date?zile=30").get_json()

    assert body["titlu"] == "9 octombrie – 7 noiembrie 2026"
    assert body["firme"][0]["total_bani"] == 3500  # 20 October + 2 November


def test_calendar_range(client, alfa):
    body = client.get("/date?de=2026-09-01&pana=2026-10-31").get_json()

    assert body["tip"] == "perioada"
    assert body["titlu"] == "1 septembrie – 31 octombrie 2026"
    assert body["firme"][0]["total_bani"] == 41000


def test_month_list_comes_with_every_answer(client, alfa):
    body = client.get("/date?zile=7").get_json()

    assert [m["luna"] for m in body["luni"]] == ["2026-11", "2026-10", "2026-09"]
    assert body["luni"][0]["text"] == "noiembrie 2026"


@pytest.mark.parametrize(
    "query",
    ["de=2026-11-05&pana=2026-11-01", "de=2026-11-01&pana=2026-11-09", "zile=12", "luna=2026-13"],
)
def test_a_bad_filter_gets_a_romanian_message(client, today, query, caplog):
    with caplog.at_level("WARNING"):
        response = client.get(f"/date?{query}")

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["mesaj"]
    assert "Refused filter" in caplog.text


def test_a_database_failure_in_a_range_is_reported(client, today, monkeypatch):
    import sqlite3

    def broken(conn, start, end):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(dashboard, "range_rows", broken)

    response = client.get("/date?zile=7")

    assert response.status_code == 500
    assert "jurnal" in response.get_json()["mesaj"]
