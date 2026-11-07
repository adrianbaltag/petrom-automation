"""Company and invoice changes by hand (M5): add, edit, archive, restore, delete invoice."""

import sqlite3

import pytest
from db_helpers import open_db

from petrom_dashboard import firme
from petrom_dashboard.db import init_db

MONTH = "2026-11"


@pytest.fixture()
def db_file(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    return db_file


def company(db_file, firma_id):
    with open_db(db_file) as conn:
        return conn.execute("SELECT * FROM firme WHERE id = ?", (firma_id,)).fetchone()


def maxes(db_file, firma_id):
    with open_db(db_file) as conn:
        rows = conn.execute(
            "SELECT luna, max_bani FROM limite WHERE firma_id = ? ORDER BY luna", (firma_id,)
        ).fetchall()
    return [(row["luna"], row["max_bani"]) for row in rows]


def add(db_file, cui="46133455", nume="ALFA SRL", max_text="", luna=MONTH):
    with open_db(db_file) as conn:
        return firme.add_company(conn, cui, nume, max_text, luna)


def add_invoice(db_file, firma_id, data_factura, total_bani, numar="FP1"):
    with open_db(db_file) as conn:
        return conn.execute(
            "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (firma_id, data_factura, total_bani, f"{numar}.pdf", f"amp-{numar}", numar),
        ).lastrowid


# --- CUI ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "46133455",  # the real sample invoice's buyer
        "1590082",  # OMV Petrom (public)
        "2816464",  # Dedeman (public)
        "RO46133455",
        "ro 46133455",
        "  RO 46133455  ",
    ],
)
def test_valid_cuis_are_accepted_and_kept_as_digits(text):
    assert firme.normalize_cui(text) in {"46133455", "1590082", "2816464"}


@pytest.mark.parametrize(
    ("text", "saved"), [("046133455", "46133455"), ("RO 0001590082", "1590082")]
)
def test_leading_zeros_are_dropped_so_the_pdf_reader_finds_the_company(text, saved):
    assert firme.normalize_cui(text) == saved


@pytest.mark.parametrize("text", ["0000000000", "00", "05"])
def test_cui_of_only_zeros_or_one_digit_after_zeros_is_refused(text):
    with pytest.raises(firme.FirmaError, match="CUI"):
        firme.normalize_cui(text)


def test_ro_prefix_and_spaces_are_removed():
    assert firme.normalize_cui(" ro 46133455 ") == "46133455"


@pytest.mark.parametrize("text", ["46133445", "46133454", "1590083"])
def test_a_typo_fails_the_check_digit(text):
    with pytest.raises(firme.FirmaError, match="CUI invalid"):
        firme.normalize_cui(text)


@pytest.mark.parametrize("text", ["", "   ", "RO", "4", "12345678901", "4613a455", "46-133455"])
def test_cui_that_is_not_2_to_10_digits_is_refused(text):
    with pytest.raises(firme.FirmaError, match="CUI"):
        firme.normalize_cui(text)


def test_check_digit_of_10_becomes_0():
    # Body 1000013 -> 001000013 against key 753217532 -> sum 12 -> 120 % 11 = 10 -> 0.
    assert firme.check_digit("1000013") == 0
    assert firme.normalize_cui("10000130") == "10000130"
    with pytest.raises(firme.FirmaError):
        firme.normalize_cui("10000131")


# --- Name and max ---------------------------------------------------------------------


def test_name_is_trimmed():
    assert firme.clean_name("  ALFA SRL  ") == "ALFA SRL"


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_name_is_refused(text):
    with pytest.raises(firme.FirmaError, match="Numele"):
        firme.clean_name(text)


def test_name_longer_than_200_characters_is_refused():
    firme.clean_name("A" * 200)
    with pytest.raises(firme.FirmaError, match="200"):
        firme.clean_name("A" * 201)


@pytest.mark.parametrize(
    ("text", "bani"),
    [("5000", 5000_00), ("5.000", 5000_00), ("5.000,00", 5000_00), ("5000,5", 5000_50)],
)
def test_max_uses_the_romanian_amount_rules(text, bani):
    assert firme.parse_max(text) == bani


@pytest.mark.parametrize("text", ["0", "0,00", "abc", "5.00.0"])
def test_zero_or_unclear_max_is_refused(text):
    with pytest.raises(firme.FirmaError, match="Max"):
        firme.parse_max(text)


# --- Add ------------------------------------------------------------------------------


def test_add_company_without_max(db_file):
    firma_id = add(db_file, cui="RO46133455", nume=" ALFA SRL ")

    row = company(db_file, firma_id)
    assert (row["cui"], row["nume"], row["arhivat"]) == ("46133455", "ALFA SRL", 0)
    assert maxes(db_file, firma_id) == []


def test_add_company_with_max_sets_it_for_this_month(db_file):
    firma_id = add(db_file, max_text="5.000")

    assert maxes(db_file, firma_id) == [(MONTH, 5000_00)]


def test_add_refuses_an_active_duplicate_and_names_the_company(db_file):
    add(db_file, nume="ALFA SRL")

    with pytest.raises(firme.FirmaError) as err:
        add(db_file, cui="RO46133455", nume="ALTA SRL")

    assert "ALFA SRL" in err.value.mesaj and "46133455" in err.value.mesaj
    assert not isinstance(err.value, firme.ArchivedCompany)


def test_add_with_an_archived_cui_offers_restore(db_file):
    firma_id = add(db_file, nume="ALFA SRL")
    with open_db(db_file) as conn:
        firme.archive_company(conn, firma_id)

    with pytest.raises(firme.ArchivedCompany) as err:
        add(db_file, nume="ALTA SRL")

    assert err.value.firma_id == firma_id
    assert err.value.nume == "ALFA SRL"
    assert "arhivată" in err.value.mesaj


def test_add_with_bad_input_saves_nothing(db_file):
    with pytest.raises(firme.FirmaError):
        add(db_file, max_text="0")

    with open_db(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM firme").fetchone()[0] == 0


def test_two_companies_may_share_a_name(db_file):
    add(db_file, cui="46133455", nume="TRANS SRL")
    add(db_file, cui="1590082", nume="TRANS SRL")

    with open_db(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM firme").fetchone()[0] == 2


# --- Edit -----------------------------------------------------------------------------


def update(db_file, firma_id, nume="ALFA SRL", max_text="", luna=MONTH):
    with open_db(db_file) as conn:
        firme.update_company(conn, firma_id, nume, max_text, luna)


def test_edit_changes_the_name(db_file):
    firma_id = add(db_file)

    update(db_file, firma_id, nume=" ALFA NOU SRL ")

    assert company(db_file, firma_id)["nume"] == "ALFA NOU SRL"


def test_edit_max_writes_this_month_and_keeps_earlier_months(db_file):
    firma_id = add(db_file, max_text="8000", luna="2026-07")

    update(db_file, firma_id, max_text="9000", luna="2026-08")

    assert maxes(db_file, firma_id) == [("2026-07", 8000_00), ("2026-08", 9000_00)]


def test_last_edit_in_a_month_wins(db_file):
    firma_id = add(db_file, max_text="5000")

    update(db_file, firma_id, max_text="6000")
    update(db_file, firma_id, max_text="6.500")

    assert maxes(db_file, firma_id) == [(MONTH, 6500_00)]


def test_unchanged_max_writes_no_new_month(db_file):
    firma_id = add(db_file, max_text="8000", luna="2026-07")

    update(db_file, firma_id, nume="ALFA NOU SRL", max_text="8.000,00", luna="2026-08")

    assert maxes(db_file, firma_id) == [("2026-07", 8000_00)]


def test_max_cannot_be_emptied_once_set(db_file):
    firma_id = add(db_file, max_text="5000", luna="2026-07")

    with pytest.raises(firme.FirmaError, match="Max"):
        update(db_file, firma_id, max_text="  ", luna="2026-08")

    assert maxes(db_file, firma_id) == [("2026-07", 5000_00)]


def test_empty_max_on_a_company_without_one_keeps_it_unset(db_file):
    firma_id = add(db_file)

    update(db_file, firma_id, nume="ALFA NOU SRL", max_text="")

    assert maxes(db_file, firma_id) == []
    assert company(db_file, firma_id)["nume"] == "ALFA NOU SRL"


def test_old_stored_max_of_zero_counts_as_unset_when_editing(db_file):
    firma_id = add(db_file)
    with open_db(db_file) as conn:  # old data, from before M5 refused 0
        conn.execute("INSERT INTO limite VALUES (?, ?, 0)", (firma_id, MONTH))

    update(db_file, firma_id, nume="ALFA NOU SRL", max_text="")

    assert company(db_file, firma_id)["nume"] == "ALFA NOU SRL"


def test_edit_with_bad_max_changes_nothing(db_file):
    firma_id = add(db_file, max_text="5000")

    with pytest.raises(firme.FirmaError):
        update(db_file, firma_id, nume="ALFA NOU SRL", max_text="0")

    assert company(db_file, firma_id)["nume"] == "ALFA SRL"
    assert maxes(db_file, firma_id) == [(MONTH, 5000_00)]


def test_edit_unknown_company_is_refused(db_file):
    with pytest.raises(firme.CompanyNotFound):
        update(db_file, 999)


# --- Archive and restore --------------------------------------------------------------


def test_archive_and_restore(db_file):
    firma_id = add(db_file, max_text="5000")
    with open_db(db_file) as conn:
        firme.archive_company(conn, firma_id)
    assert company(db_file, firma_id)["arhivat"] == 1

    with open_db(db_file) as conn:
        assert [dict(r) for r in firme.archived_companies(conn)] == [
            {"id": firma_id, "cui": "46133455", "nume": "ALFA SRL"}
        ]
        firme.restore_company(conn, firma_id)

    assert company(db_file, firma_id)["arhivat"] == 0
    assert maxes(db_file, firma_id) == [(MONTH, 5000_00)]  # history kept


def test_archived_list_is_sorted_by_name(db_file):
    b = add(db_file, cui="46133455", nume="BETA SRL")
    a = add(db_file, cui="1590082", nume="ALFA SRL")
    with open_db(db_file) as conn:
        firme.archive_company(conn, b)
        firme.archive_company(conn, a)
        assert [r["nume"] for r in firme.archived_companies(conn)] == ["ALFA SRL", "BETA SRL"]


@pytest.mark.parametrize("action", ["archive_company", "restore_company"])
def test_archive_or_restore_unknown_company_is_refused(db_file, action):
    with open_db(db_file) as conn, pytest.raises(firme.CompanyNotFound):
        getattr(firme, action)(conn, 999)


# --- Invoices -------------------------------------------------------------------------


def test_month_invoices_lists_only_that_month_newest_first(db_file):
    firma_id = add(db_file)
    other = add(db_file, cui="1590082", nume="BETA SRL")
    add_invoice(db_file, firma_id, "2026-11-03", 100_00, numar="FP1")
    add_invoice(db_file, firma_id, "2026-11-20", 1234_56, numar="FP2")
    add_invoice(db_file, firma_id, "2026-10-31", 50_00, numar="FP0")  # last month
    add_invoice(db_file, other, "2026-11-05", 70_00, numar="FP9")  # other company

    with open_db(db_file) as conn:
        rows = firme.month_invoices(conn, firma_id, MONTH)

    assert [r["numar"] for r in rows] == ["FP2", "FP1"]
    assert rows[0]["data_text"] == "20.11.2026"
    assert rows[0]["total_text"] == "1.234,56 lei"
    assert rows[0]["fisier"] == "FP2.pdf"


def test_month_invoices_of_unknown_company_is_refused(db_file):
    with open_db(db_file) as conn, pytest.raises(firme.CompanyNotFound):
        firme.month_invoices(conn, 999, MONTH)


def test_delete_invoice_removes_it_and_returns_what_was_deleted(db_file):
    firma_id = add(db_file)
    factura_id = add_invoice(db_file, firma_id, "2026-11-03", 100_00, numar="FP1")

    with open_db(db_file) as conn:
        deleted = firme.delete_invoice(conn, factura_id)

    assert deleted["numar"] == "FP1" and deleted["total_bani"] == 100_00
    with open_db(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM facturi").fetchone()[0] == 0


def test_after_delete_the_same_pdf_can_be_saved_again(db_file):
    firma_id = add(db_file)
    factura_id = add_invoice(db_file, firma_id, "2026-11-03", 100_00, numar="FP1")
    with open_db(db_file) as conn:
        firme.delete_invoice(conn, factura_id)

    add_invoice(db_file, firma_id, "2026-11-03", 100_00, numar="FP1")  # no UNIQUE error


def test_delete_unknown_invoice_is_refused(db_file):
    with open_db(db_file) as conn, pytest.raises(firme.InvoiceNotFound):
        firme.delete_invoice(conn, 999)


class HidesCompaniesOnce:
    """A connection whose first CUI lookup finds nothing: as if an automation run saved
    the same CUI between add_company's duplicate check and its INSERT."""

    def __init__(self, conn):
        self.conn = conn
        self.hidden = False

    def execute(self, sql, params=()):
        if not self.hidden and sql.startswith("SELECT id, cui, nume, arhivat FROM firme WHERE cui"):
            self.hidden = True
            return self.conn.execute("SELECT 1 WHERE 0")
        return self.conn.execute(sql, params)


@pytest.mark.parametrize("archived", [False, True])
def test_cui_saved_by_a_run_in_the_meantime_gets_the_same_refusal(db_file, archived):
    firma_id = add(db_file, nume="ALFA SRL")
    if archived:
        with open_db(db_file) as conn:
            firme.archive_company(conn, firma_id)

    with open_db(db_file) as conn, pytest.raises(firme.FirmaError) as err:
        firme.add_company(HidesCompaniesOnce(conn), "46133455", "ALTA SRL", "5000", MONTH)

    assert isinstance(err.value, firme.ArchivedCompany) is archived
    assert "ALFA SRL" in err.value.mesaj
    with open_db(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM firme").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM limite").fetchone()[0] == 0


def test_cui_pasted_with_odd_spaces_is_accepted():
    # Non-breaking space, thin space and a tab, as copied from a PDF, email or Excel.
    assert firme.normalize_cui("RO\u00a046\u00a0133\u2009455\t") == "46133455"


class InsertAlwaysClashes:
    """A connection where the CUI is never found, yet the INSERT clashes: the row that
    clashed is gone again by the time it is looked up."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        if sql.startswith("SELECT id, cui, nume, arhivat FROM firme WHERE cui"):
            return self.conn.execute("SELECT 1 WHERE 0")
        if sql.startswith("INSERT INTO firme"):
            raise sqlite3.IntegrityError("UNIQUE constraint failed: firme.cui")
        return self.conn.execute(sql, params)


def test_clash_with_a_row_that_is_gone_again_is_a_clear_refusal(db_file):
    with open_db(db_file) as conn, pytest.raises(firme.FirmaError) as err:
        firme.add_company(InsertAlwaysClashes(conn), "46133455", "ALFA SRL", "", MONTH)

    assert "încearcă din nou" in err.value.mesaj


def test_restore_with_a_typed_max_sets_it_for_this_month(db_file):
    firma_id = add(db_file, max_text="5000", luna="2026-07")
    with open_db(db_file) as conn:
        firme.archive_company(conn, firma_id)
        firme.restore_company(conn, firma_id, "6.000", MONTH)

    assert company(db_file, firma_id)["arhivat"] == 0
    assert company(db_file, firma_id)["nume"] == "ALFA SRL"
    assert maxes(db_file, firma_id) == [("2026-07", 5000_00), (MONTH, 6000_00)]


def test_restore_with_a_bad_max_restores_nothing(db_file):
    firma_id = add(db_file)
    with open_db(db_file) as conn:
        firme.archive_company(conn, firma_id)
    with open_db(db_file) as conn, pytest.raises(firme.FirmaError, match="Max"):
        firme.restore_company(conn, firma_id, "0", MONTH)

    assert company(db_file, firma_id)["arhivat"] == 1
