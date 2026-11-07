"""The automation run behind the "Rulează automatizarea" button.

One run:
1. Takes a lock, so two runs can never overlap (a second one gets "Rulează deja").
2. Creates the three folders if missing.
3. If Facturi-noi holds any PDF, backs up the database (newest 30 copies kept).
4. For each PDF in Facturi-noi: skip duplicates, read it, save it, THEN move it to
   Facturi-procesate/YYYY-MM. Anything wrong goes to Facturi-erori, with a line in
   motive.txt (also when the file has to stay in Facturi-noi).
5. Returns a summary for the page.

Why save first, then move: if the move fails (the PDF is open in a viewer on Windows),
the money is already counted and the file just stays behind; the next run sees it was
saved but not moved and moves it then. The other order could leave a moved PDF whose
money was never counted, and nobody would notice.
"""

import errno
import hashlib
import logging
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from petrom_dashboard.db import connect
from petrom_dashboard.pdf_reader import InvoiceError, read_invoice

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)

LOCK_FILE_NAME = "rulare.lock"
BACKUPS_KEPT = 30
MOTIVE_FILE_NAME = "motive.txt"

# Romanian messages shown to the user.
ALREADY_RUNNING = "Automatizarea rulează deja."
ALREADY_PROCESSED = "Factură deja procesată"
BACKUP_FAILED = "Backup-ul bazei de date a eșuat, așa că automatizarea nu a pornit."
FOLDER_FAILED = "Nu am putut crea folderul {folder}."
MOVE_FAILED = "salvată, dar nu am putut-o muta (e deschisă în alt program?)"
ERRORS_MOVE_FAILED = "nu am putut-o muta în Facturi-erori, a rămas în Facturi-noi"
UNEXPECTED = "Eroare neașteptată, fișierul a rămas în Facturi-noi (detalii în jurnal)"
STILL_NOT_MOVED = (
    "Salvată deja, dar tot nu am putut-o muta (e deschisă în alt program?), a rămas în Facturi-noi"
)


class RunError(Exception):
    """The run could not start. `mesaj` is the Romanian text for the page."""

    def __init__(self, mesaj):
        super().__init__(mesaj)
        self.mesaj = mesaj


class AlreadyRunning(RunError):
    def __init__(self):
        super().__init__(ALREADY_RUNNING)


class BackupError(RunError):
    def __init__(self):
        super().__init__(BACKUP_FAILED)


@dataclass(frozen=True)
class Folders:
    noi: Path  # Facturi-noi: where she drops new PDFs
    procesate: Path  # Facturi-procesate: saved invoices, one subfolder per month
    erori: Path  # Facturi-erori: refused files, plus motive.txt with the reasons

    def all(self):
        return [self.noi, self.procesate, self.erori]


@dataclass
class RunSummary:
    total: int = 0  # PDFs found in Facturi-noi
    adaugate: list = field(default_factory=list)  # file names saved this run
    erori: list = field(default_factory=list)  # (file name, Romanian reason)
    mutate: list = field(default_factory=list)  # saved on an earlier run, moved now
    note: list = field(default_factory=list)  # other Romanian remarks for the page

    def mesaj(self):
        """The headline, for example "10 PDF-uri: 9 adăugate, 1 eroare"."""
        if self.total == 0:
            return "Niciun PDF nou în Facturi-noi."
        text = (
            f"{count_words(self.total, 'PDF', 'PDF-uri')}: "
            f"{count_words(len(self.adaugate), 'adăugată', 'adăugate')}, "
            f"{count_words(len(self.erori), 'eroare', 'erori')}"
        )
        if self.mutate:
            text += ", " + count_words(
                len(self.mutate), "mutată (salvată deja)", "mutate (salvate deja)"
            )
        return text

    def to_dict(self):
        return {
            "ok": True,
            "mesaj": self.mesaj(),
            "total": self.total,
            "adaugate": self.adaugate,
            "erori": [{"fisier": name, "motiv": motiv} for name, motiv in self.erori],
            "mutate": self.mutate,
            "note": self.note,
        }


def count_words(n, one, many):
    """Romanian counting: '1 eroare', '2 erori', '20 de erori'.

    'de' goes in when the last two digits are 00 or 20-99 (so '101 erori' but '120 de erori').
    """
    if n == 1:
        return f"1 {one}"
    de = "de " if n != 0 and (n % 100 >= 20 or n % 100 == 0) else ""
    return f"{n} {de}{many}"


# ---------- building blocks ----------


def fingerprint(path):
    """A SHA-256 of the file's bytes: the same file always gives the same value."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_destination(folder, name):
    """folder/name, or folder/'name (2)', 'name (3)'... if that name is already taken."""
    folder = Path(folder)
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def _move(src, folder):
    """Move src into folder (created if missing) without overwriting. Returns the new path.

    Never leaves the PDF in two places. shutil.move is avoided on purpose: when a PDF is
    open in a viewer on Windows, it copies the file and then fails to delete the original.
    """
    src, folder = Path(src), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_destination(folder, src.name)
    try:
        os.rename(src, dest)  # same drive: instant, and fails cleanly if the file is open
    except OSError as exc:
        if exc.errno != errno.EXDEV:  # EXDEV = the folders are on different drives
            raise
        _copy_then_delete(src, dest)
    return dest


def _copy_then_delete(src, dest):
    """Different drives: copy, then delete the original.

    If either step fails, the copy (whole or half-written) is removed, so the PDF is
    never left in two places.
    """
    try:
        shutil.copy2(src, dest)
        os.unlink(src)
    except OSError:
        try:
            os.unlink(dest)
        except FileNotFoundError:
            pass  # the copy never started
        except OSError:
            logger.warning("Could not remove the extra copy %s", dest, exc_info=True)
        raise


def backup_database(db_file, backup_dir, keep=BACKUPS_KEPT, prefix="petrom"):
    """Copy the database to backup_dir/<prefix>-YYYYMMDD-HHMMSS-micro.db; keep the newest
    `keep` with that prefix.

    Each prefix is its own group: run backups ("petrom-2026...") and invoice-delete backups
    ("petrom-stergere-2026...") never push each other out.
    Uses SQLite's own backup, which is safe even while the database is open.
    """
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{prefix}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    with closing(sqlite3.connect(db_file)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    logger.info("Database backed up to %s", target)

    # "[0-9]" right after the prefix: "petrom-[0-9]*" does not match "petrom-stergere-...".
    backups = sorted(backup_dir.glob(f"{prefix}-[0-9]*.db"))  # names sort oldest first
    for old in backups[:-keep]:
        try:
            old.unlink()
        except OSError:
            logger.warning("Could not delete old backup %s", old, exc_info=True)
    return target


class RunLock:
    """Only one run at a time, even across two copies of the app.

    The operating system holds the lock on a small file in the data folder. If the app
    crashes, the operating system frees it, so a crash can never block runs forever.
    """

    def __init__(self, lock_file):
        self.lock_file = Path(lock_file)
        self._fh = None

    def __enter__(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_file, "a+b")
        try:
            _lock(fh)
        except OSError as exc:
            fh.close()
            logger.warning("Run refused: another run holds %s", self.lock_file)
            raise AlreadyRunning() from exc
        self._fh = fh
        return self

    def __exit__(self, *exc_info):
        try:
            _unlock(self._fh)
        finally:
            self._fh.close()
            self._fh = None


if sys.platform == "win32":

    def _lock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # fails at once if someone holds it

    def _unlock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:

    def _lock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # fails at once if held

    def _unlock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def desktop_dir():
    """The real Desktop. On Windows we ask Windows, because OneDrive can move the Desktop."""
    if sys.platform == "win32":
        try:
            return _windows_desktop()
        except Exception:  # ctypes can fail in many ways; the home Desktop is a safe fallback
            logger.warning(
                "Could not ask Windows for the Desktop, using the home one", exc_info=True
            )
    return Path.home() / "Desktop"


def _windows_desktop():
    """Ask Windows for the Desktop folder (SHGetKnownFolderPath, FOLDERID_Desktop)."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
    desktop_id = GUID(
        0xB4BFCC3A,
        0xDB2C,
        0x424C,
        (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
    )
    path_ptr = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(desktop_id), 0, None, ctypes.byref(path_ptr)
    )
    try:
        if result != 0:
            raise OSError(f"SHGetKnownFolderPath failed with code {result}")
        return Path(path_ptr.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)


def get_folders(conn):
    """The three folders: from Setări if set there, otherwise on the Desktop."""
    saved = dict(
        conn.execute("SELECT cheie, valoare FROM setari WHERE cheie LIKE 'folder_%'").fetchall()
    )
    defaults = {"noi": "Facturi-noi", "procesate": "Facturi-procesate", "erori": "Facturi-erori"}
    paths = {}
    desktop = None  # asked at most once, and only if a folder isn't set
    for key, default_name in defaults.items():
        value = saved.get(f"folder_{key}")
        if value:
            paths[key] = Path(value)
        else:
            if desktop is None:
                desktop = desktop_dir()
            paths[key] = desktop / default_name
    return Folders(**paths)


# ---------- the run ----------


def run_automation(db_file, folders, data_dir):
    """Process every PDF in folders.noi. Raises RunError if the run can't start."""
    data_dir = Path(data_dir)
    with RunLock(data_dir / LOCK_FILE_NAME):
        for folder in folders.all():
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.exception("Could not create folder %s, run stopped", folder)
                raise RunError(FOLDER_FAILED.format(folder=folder)) from exc

        pdfs = sorted(
            p for p in folders.noi.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
        )
        summary = RunSummary(total=len(pdfs))
        logger.info("Run started: %d PDF(s) in %s", len(pdfs), folders.noi)
        if not pdfs:
            # Nothing will change, so no backup: empty clicks must not push out useful copies.
            return summary

        try:
            backup_database(db_file, data_dir / "backups")
        except (OSError, sqlite3.Error) as exc:
            logger.exception("Backup failed, run stopped before touching any file")
            raise BackupError() from exc

        with closing(connect(db_file)) as conn:
            for pdf in pdfs:
                try:
                    _process_one(conn, pdf, folders, summary)
                except Exception:  # one bad file must never stop the others
                    conn.rollback()
                    logger.exception("Unexpected error on %s, file left in place", pdf.name)
                    summary.erori.append((pdf.name, UNEXPECTED))
                    _write_reason(folders.erori, pdf.name, UNEXPECTED)
        logger.info("Run finished: %s", summary.mesaj())
        return summary


_FIND_SAVED = {
    "amprenta": "SELECT id, data_factura, mutat FROM facturi WHERE amprenta = ?",
    "numar": "SELECT id, data_factura, mutat FROM facturi WHERE numar = ?",
}


def _find_saved(conn, column, value):
    """The saved invoice with this fingerprint ("amprenta") or number ("numar"), or None."""
    return conn.execute(_FIND_SAVED[column], (value,)).fetchone()


def _process_one(conn, path, folders, summary):
    amprenta = fingerprint(path)
    seen = _find_saved(conn, "amprenta", amprenta)
    if seen:
        _handle_seen(conn, path, seen, folders, summary)
        return

    try:
        invoice = read_invoice(path)  # logs its own refusals
    except InvoiceError as err:
        _send_to_errors(path, err.motiv, folders, summary)
        return

    seen = _find_saved(conn, "numar", invoice.numar)
    if seen:
        _handle_seen(conn, path, seen, folders, summary)
        return

    factura_id = _save(conn, invoice, path.name, amprenta, summary)
    summary.adaugate.append(path.name)
    logger.info("Saved %s: CUI %s, %d bani", path.name, invoice.cui, invoice.total_bani)

    try:
        _move_and_mark(conn, path, folders.procesate / invoice.data.strftime("%Y-%m"), factura_id)
    except OSError:
        logger.warning("Saved %s but could not move it", path.name, exc_info=True)
        summary.note.append(f"{path.name}: {MOVE_FAILED}")


def _handle_seen(conn, path, seen, folders, summary):
    """The same file or invoice number is already saved."""
    if seen["mutat"]:
        logger.info("%s was already processed", path.name)
        _send_to_errors(path, ALREADY_PROCESSED, folders, summary)
        return
    # Saved on an earlier run, but that move failed: finish the move now. No money added.
    try:
        _move_and_mark(conn, path, folders.procesate / seen["data_factura"][:7], seen["id"])
    except OSError:
        logger.warning("Still cannot move %s", path.name, exc_info=True)
        summary.erori.append((path.name, STILL_NOT_MOVED))
        _write_reason(folders.erori, path.name, STILL_NOT_MOVED)
        return
    summary.mutate.append(path.name)
    logger.info("Moved %s, saved on an earlier run", path.name)


def _move_and_mark(conn, path, month_folder, factura_id):
    """Move a saved invoice's PDF to its month folder, then mark it moved under its final name.

    Raises OSError if the move fails; the invoice then stays marked as not moved.
    """
    dest = _move(path, month_folder)
    try:
        _mark_moved(conn, factura_id, dest.name)
    except sqlite3.Error:
        # The PDF is in place and its money was saved earlier; only the "moved" flag is
        # missing, which matters only while a file sits in Facturi-noi. Not an error for her.
        conn.rollback()
        logger.exception("Moved %s but could not mark invoice %s as moved", dest, factura_id)


def _mark_moved(conn, factura_id, file_name):
    conn.execute("UPDATE facturi SET mutat = 1, fisier = ? WHERE id = ?", (file_name, factura_id))
    conn.commit()


def _save(conn, invoice, file_name, amprenta, summary):
    """Save the invoice (creating or restoring its company). Returns the new invoice id."""
    firma = conn.execute(
        "SELECT id, nume, arhivat FROM firme WHERE cui = ?", (invoice.cui,)
    ).fetchone()
    restored = None
    if firma is None:
        firma_id = conn.execute(
            "INSERT INTO firme (cui, nume) VALUES (?, ?)", (invoice.cui, invoice.nume)
        ).lastrowid
        logger.info("New company created: CUI %s, %s", invoice.cui, invoice.nume)
    else:
        firma_id = firma["id"]
        if firma["arhivat"]:
            conn.execute("UPDATE firme SET arhivat = 0 WHERE id = ?", (firma_id,))
            restored = firma["nume"]
            logger.info("Archived company CUI %s restored by a new invoice", invoice.cui)

    factura_id = conn.execute(
        "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            firma_id,
            invoice.data.isoformat(),
            invoice.total_bani,
            file_name,
            amprenta,
            invoice.numar,
        ),
    ).lastrowid
    conn.commit()
    if restored:
        summary.note.append(f"Firma {restored} a fost restaurată (era arhivată).")
    return factura_id


def _send_to_errors(path, motiv, folders, summary):
    """Move a refused file to Facturi-erori and write the reason in motive.txt."""
    summary.erori.append((path.name, motiv))
    try:
        dest = _move(path, folders.erori)
    except OSError:
        logger.warning("Could not move %s to the errors folder", path.name, exc_info=True)
        summary.note.append(f"{path.name}: {ERRORS_MOVE_FAILED}")
        _write_reason(folders.erori, path.name, f"{motiv} ({ERRORS_MOVE_FAILED})")
        return
    _write_reason(folders.erori, dest.name, motiv)


def _write_reason(errors_folder, file_name, motiv):
    """Add one line to motive.txt. utf-8-sig so Notepad shows ă, ș, ț correctly."""
    line = f"{datetime.now():%d.%m.%Y %H:%M}  {file_name}  {motiv}\n"
    try:
        with open(Path(errors_folder) / MOTIVE_FILE_NAME, "a", encoding="utf-8-sig") as fh:
            fh.write(line)
    except OSError:
        logger.warning("Could not write the reason for %s to motive.txt", file_name, exc_info=True)
