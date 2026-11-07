"""The SQLite database: one file holding companies, monthly limits, invoices and settings.

Money is stored as whole bani (1 leu = 100 bani), so 199,29 lei is saved as 19929.
Whole numbers never get rounding errors; the pages turn them back into lei with decimals.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
-- One row per company. The CUI (tax code, digits only) is how invoices find their company.
CREATE TABLE IF NOT EXISTS firme (
    id      INTEGER PRIMARY KEY,
    cui     TEXT    NOT NULL UNIQUE,
    nume    TEXT    NOT NULL,
    arhivat INTEGER NOT NULL DEFAULT 0          -- 1 = hidden from the table, history kept
);

-- The max amount of a company for one month (luna looks like '2026-06').
CREATE TABLE IF NOT EXISTS limite (
    firma_id INTEGER NOT NULL REFERENCES firme(id),
    luna     TEXT    NOT NULL,
    max_bani INTEGER NOT NULL CHECK (typeof(max_bani) = 'integer'),  -- whole bani only
    PRIMARY KEY (firma_id, luna)                -- only one max per company per month
);

-- One row per processed PDF invoice.
CREATE TABLE IF NOT EXISTS facturi (
    id           INTEGER PRIMARY KEY,
    firma_id     INTEGER NOT NULL REFERENCES firme(id),
    data_factura TEXT    NOT NULL,              -- invoice date, '2026-06-05'
    total_bani   INTEGER NOT NULL               -- 'Total de plata' in bani
                 CHECK (typeof(total_bani) = 'integer'),  -- 199.29 by mistake is refused
    fisier       TEXT    NOT NULL,              -- original file name
    amprenta     TEXT    NOT NULL UNIQUE,       -- file fingerprint: same PDF can't count twice
    numar        TEXT    NOT NULL UNIQUE,       -- invoice number: a re-downloaded copy can't count
    mutat        INTEGER NOT NULL DEFAULT 0,    -- 1 = the PDF reached Facturi-procesate
    procesat_la  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Simple key/value settings, for example the three folder paths.
CREATE TABLE IF NOT EXISTS setari (
    cheie   TEXT PRIMARY KEY,
    valoare TEXT NOT NULL
);
"""


def connect(db_file):
    """Open the database. Rows can be read by column name, and company links are enforced."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_file):
    """Create the database file and its tables if missing. Existing data is kept."""
    db_file = Path(db_file)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = connect(db_file)
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("Could not create the database at %s", db_file)
        raise
