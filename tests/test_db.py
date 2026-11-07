import sqlite3

import pytest

from petrom_dashboard.db import connect, init_db


@pytest.fixture()
def conn(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    connection = connect(db_file)
    yield connection
    connection.close()


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_creates_the_four_tables(conn):
    assert table_names(conn) == {"firme", "limite", "facturi", "setari"}


def test_init_twice_keeps_existing_data(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    with connect(db_file) as conn:
        conn.execute("INSERT INTO firme (cui, nume) VALUES ('46133455', 'ALFA SRL')")
    init_db(db_file)

    with connect(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM firme").fetchone()[0] == 1


def test_cui_must_be_unique(conn):
    conn.execute("INSERT INTO firme (cui, nume) VALUES ('46133455', 'ALFA SRL')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO firme (cui, nume) VALUES ('46133455', 'ALFA 2 SRL')")


def test_one_max_per_company_per_month(conn):
    conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '46133455', 'ALFA SRL')")
    conn.execute("INSERT INTO limite (firma_id, luna, max_bani) VALUES (1, '2026-05', 100000)")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO limite (firma_id, luna, max_bani) VALUES (1, '2026-05', 200000)")


def test_same_pdf_fingerprint_cannot_be_saved_twice(conn):
    conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '46133455', 'ALFA SRL')")
    insert = (
        "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta) "
        "VALUES (1, '2026-06-05', 19929, ?, 'abc123')"
    )
    conn.execute(insert, ("Factura_1.pdf",))

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("Factura_1 (copie).pdf",))


def test_invoice_total_must_be_whole_bani(conn):
    conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '46133455', 'ALFA SRL')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta) "
            "VALUES (1, '2026-06-05', 199.29, 'Factura_1.pdf', 'abc123')"
        )


def test_monthly_max_must_be_whole_bani(conn):
    conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '46133455', 'ALFA SRL')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO limite (firma_id, luna, max_bani) VALUES (1, '2026-05', 1000.5)")


def test_invoice_must_belong_to_an_existing_company(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta) "
            "VALUES (999, '2026-06-05', 19929, 'Factura_1.pdf', 'abc123')"
        )
