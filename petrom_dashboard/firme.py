"""Changes made by hand from the dashboard (M5): add, edit, archive and restore a company,
list a company's invoices for a month, and delete a wrong invoice.

Every function takes an open connection and leaves committing to the caller, so a refused
change saves nothing. Errors carry a Romanian message (`mesaj`) for the page.
"""

import logging
import sqlite3

from petrom_dashboard.cui import clean_cui
from petrom_dashboard.dashboard import has_max
from petrom_dashboard.money import AmountError, format_lei, parse_amount

logger = logging.getLogger(__name__)

NAME_MAX_LENGTH = 200

# Romanian CUI check digit: the digits before the last one are lined up on the right
# against this key, multiplied pair by pair and added up.
_CUI_KEY = "753217532"

CUI_NOT_DIGITS = "CUI-ul trebuie să aibă între 2 și 10 cifre (poate începe cu RO)."
CUI_BAD_CHECK = "CUI invalid, verifică cifrele."
NAME_EMPTY = "Numele firmei este obligatoriu."
NAME_TOO_LONG = f"Numele firmei poate avea cel mult {NAME_MAX_LENGTH} de caractere."
MAX_UNCLEAR = "Max-ul nu este o sumă clară. Exemple: 5000, 5.000 sau 5.000,00."
MAX_NOT_POSITIVE = "Max-ul trebuie să fie mai mare decât 0."
MAX_CANNOT_EMPTY = "Max-ul nu poate fi șters, doar schimbat."
COMPANY_MISSING = "Firma nu mai există. Reîncarcă pagina."
INVOICE_MISSING = "Factura nu mai există. Reîncarcă pagina."
ADD_CLASH = "Nu am putut salva firma, încearcă din nou."


class FirmaError(ValueError):
    """A change was refused. `mesaj` says why, in Romanian."""

    def __init__(self, mesaj):
        super().__init__(mesaj)
        self.mesaj = mesaj


class ArchivedCompany(FirmaError):
    """The CUI belongs to an archived company: offer to restore it instead."""

    def __init__(self, firma_id, nume):
        super().__init__(f"Firma {nume} e arhivată. O poți restaura, cu istoricul ei.")
        self.firma_id = firma_id
        self.nume = nume


class CompanyNotFound(FirmaError):
    def __init__(self):
        super().__init__(COMPANY_MISSING)


class InvoiceNotFound(FirmaError):
    def __init__(self):
        super().__init__(INVOICE_MISSING)


# --- Checking what was typed ----------------------------------------------------------


def check_digit(body):
    """The check digit a CUI must end with, given the digits before it."""
    total = sum(int(d) * int(k) for d, k in zip(body.rjust(9, "0"), _CUI_KEY, strict=True))
    rest = total * 10 % 11
    return 0 if rest == 10 else rest


def normalize_cui(text):
    """Return the CUI as digits only ('RO 46133455' -> '46133455'), or raise FirmaError."""
    digits = clean_cui(text)  # same rule as the PDF reader, so invoices find the company
    if not (digits.isascii() and digits.isdigit() and 2 <= len(digits) <= 10):
        raise FirmaError(CUI_NOT_DIGITS)
    if check_digit(digits[:-1]) != int(digits[-1]):
        raise FirmaError(CUI_BAD_CHECK)
    return digits


def clean_name(text):
    """Return the name without spaces at either end, or raise FirmaError."""
    name = (text or "").strip()
    if not name:
        raise FirmaError(NAME_EMPTY)
    if len(name) > NAME_MAX_LENGTH:
        raise FirmaError(NAME_TOO_LONG)
    return name


def parse_max(text):
    """Return the max in whole bani (above 0), or raise FirmaError."""
    try:
        bani = parse_amount(text)
    except AmountError as err:
        raise FirmaError(MAX_UNCLEAR) from err
    if bani <= 0:
        raise FirmaError(MAX_NOT_POSITIVE)
    return bani


# --- Companies ------------------------------------------------------------------------


def _get_company(conn, firma_id):
    row = conn.execute("SELECT id, cui, nume, arhivat FROM firme WHERE id = ?", (firma_id,))
    firma = row.fetchone()
    if firma is None:
        logger.warning("Company id %s not found", firma_id)
        raise CompanyNotFound
    return firma


def _max_for(conn, firma_id, luna):
    """The max that applies to `luna` (latest set in or before it), or None."""
    row = conn.execute(
        "SELECT max_bani FROM limite WHERE firma_id = ? AND luna <= ? ORDER BY luna DESC LIMIT 1",
        (firma_id, luna),
    ).fetchone()
    return None if row is None else row["max_bani"]


def _set_max(conn, firma_id, luna, max_bani):
    """Set the max for `luna`; a second edit in the same month replaces the first."""
    conn.execute(
        "INSERT INTO limite (firma_id, luna, max_bani) VALUES (?, ?, ?) "
        "ON CONFLICT (firma_id, luna) DO UPDATE SET max_bani = excluded.max_bani",
        (firma_id, luna, max_bani),
    )


def _refuse_duplicate(existing):
    if existing["arhivat"]:
        logger.info("Add refused: CUI %s belongs to archived company", existing["cui"])
        raise ArchivedCompany(existing["id"], existing["nume"])
    logger.info(
        "Add refused: CUI %s already used by company id %s", existing["cui"], existing["id"]
    )
    raise FirmaError(
        f"Firma {existing['nume']} are deja CUI-ul {existing['cui']}. Un CUI poate aparține "
        "unei singure firme, altfel facturile nu ar ști la ce firmă să meargă."
    )


def add_company(conn, cui_text, nume_text, max_text, luna):
    """Add a company (max optional, set for `luna`). Returns the new company id."""
    cui = normalize_cui(cui_text)
    nume = clean_name(nume_text)
    max_bani = parse_max(max_text) if (max_text or "").strip() else None

    existing = conn.execute("SELECT id, cui, nume, arhivat FROM firme WHERE cui = ?", (cui,))
    found = existing.fetchone()
    if found is not None:
        _refuse_duplicate(found)
    try:
        firma_id = conn.execute(
            "INSERT INTO firme (cui, nume) VALUES (?, ?)", (cui, nume)
        ).lastrowid
    except sqlite3.IntegrityError:
        # Saved by an automation run in the split second since the check above.
        found = conn.execute(
            "SELECT id, cui, nume, arhivat FROM firme WHERE cui = ?", (cui,)
        ).fetchone()
        if found is None:  # the clashing row is gone again: nothing to name
            logger.warning("Add of CUI %s clashed on insert, but no company has it now", cui)
            raise FirmaError(ADD_CLASH) from None
        _refuse_duplicate(found)
    if max_bani is not None:
        _set_max(conn, firma_id, luna, max_bani)
    logger.info("Company added by hand: id %s, CUI %s, max %s", firma_id, cui, max_bani)
    return firma_id


def update_company(conn, firma_id, nume_text, max_text, luna):
    """Change the name and/or the max. A new max applies to `luna` and later months."""
    _get_company(conn, firma_id)
    nume = clean_name(nume_text)
    current = _max_for(conn, firma_id, luna)
    if (max_text or "").strip():
        new_max = parse_max(max_text)
    elif has_max(current):  # an old stored 0 counts as unset (the M4 rule)
        raise FirmaError(MAX_CANNOT_EMPTY)
    else:
        new_max = None

    conn.execute("UPDATE firme SET nume = ? WHERE id = ?", (nume, firma_id))
    if new_max is not None and new_max != current:
        _set_max(conn, firma_id, luna, new_max)
        logger.info("Company id %s max for %s: %s -> %s", firma_id, luna, current, new_max)
    logger.info("Company id %s saved, name %r", firma_id, nume)


def archive_company(conn, firma_id):
    _get_company(conn, firma_id)
    conn.execute("UPDATE firme SET arhivat = 1 WHERE id = ?", (firma_id,))
    logger.info("Company id %s archived by hand", firma_id)


def restore_company(conn, firma_id, max_text="", luna=None):
    """Bring an archived company back. A max typed in the Adaugă form is set for `luna`.

    Returns the new max in bani, or None when no max was typed. The name is kept.
    """
    _get_company(conn, firma_id)
    max_bani = parse_max(max_text) if (max_text or "").strip() else None
    conn.execute("UPDATE firme SET arhivat = 0 WHERE id = ?", (firma_id,))
    if max_bani is not None:
        _set_max(conn, firma_id, luna, max_bani)
    logger.info("Company id %s restored by hand, new max %s", firma_id, max_bani)
    return max_bani


def archived_companies(conn):
    return conn.execute(
        "SELECT id, cui, nume FROM firme WHERE arhivat = 1 ORDER BY nume, cui"
    ).fetchall()


# --- Invoices -------------------------------------------------------------------------


def month_invoices(conn, firma_id, luna):
    """A company's invoices dated in `luna`, newest first, with display text."""
    _get_company(conn, firma_id)
    rows = conn.execute(
        "SELECT id, data_factura, numar, total_bani, fisier FROM facturi "
        "WHERE firma_id = ? AND substr(data_factura, 1, 7) = ? "
        "ORDER BY data_factura DESC, id DESC",
        (firma_id, luna),
    ).fetchall()
    result = []
    for row in rows:
        year, month, day = row["data_factura"].split("-")
        result.append(
            {
                "id": row["id"],
                "numar": row["numar"],
                "fisier": row["fisier"],
                "total_bani": row["total_bani"],
                "total_text": format_lei(row["total_bani"]),
                "data_text": f"{day}.{month}.{year}",
            }
        )
    return result


def get_invoice(conn, factura_id):
    row = conn.execute("SELECT * FROM facturi WHERE id = ?", (factura_id,)).fetchone()
    if row is None:
        logger.warning("Invoice id %s not found", factura_id)
        raise InvoiceNotFound
    return dict(row)


def delete_invoice(conn, factura_id):
    """Delete one invoice row (the PDF file is not touched). Returns the deleted row."""
    invoice = get_invoice(conn, factura_id)
    conn.execute("DELETE FROM facturi WHERE id = ?", (factura_id,))
    logger.info("Invoice deleted by hand: %s", invoice)
    return invoice
