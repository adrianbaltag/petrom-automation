"""The Setări page's logic (M7): the three folders, manual backups, opening folders.

Folders are typed (pasted) as text, because a web page can't hand the server a real folder
path. So every box is checked here before anything is saved:
- a full path, without characters Windows refuses;
- an existing folder the app can write in, or one that can be created (Salvează creates it);
- never inside the app folder, because a new release replaces that folder and its contents;
- no two boxes on the same folder. A folder inside another of the three is fine: a run reads
  only the PDFs sitting directly in Facturi-noi.
Saving moves no files. If the old Facturi-noi still holds PDFs, the answer says so.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from petrom_dashboard import automation
from petrom_dashboard.automation import count_words
from petrom_dashboard.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

FOLDER_KEYS = ("noi", "procesate", "erori")
LABELS = {"noi": "Facturi-noi", "procesate": "Facturi-procesate", "erori": "Facturi-erori"}
OPENABLE = (*FOLDER_KEYS, "backup", "date")
MANUAL_BACKUP_PREFIX = "petrom-manual"  # own group of 30: never pushes out run backups
WINDOWS_BAD_CHARS = set('<>"|?*')

# Romanian messages shown to the user.
EMPTY = "Scrie calea folderului."
NOT_FULL = "Scrie calea completă, de exemplu C:\\Users\\Nume\\Desktop\\Facturi-noi."
BAD_CHARS = 'Calea conține caractere nepermise: < > " | ? *'
IS_FILE = "Aici e un fișier, nu un folder."
FILE_ON_THE_WAY = "Nu pot crea folderul aici: o parte din cale e un fișier."
NO_DRIVE = "Nu găsesc discul sau folderul de început al căii."
CANT_READ = "Nu pot citi această cale."
CANT_WRITE = "Nu am voie să scriu în acest folder."
CANT_CREATE = "Nu am voie să creez un folder aici."
IN_APP_FOLDER = (
    "E în folderul aplicației, care se înlocuiește la fiecare actualizare. Alege alt folder."
)
SAME_AS = "Același folder ca {label}."
EXISTS = "Există."
WILL_CREATE = "Nu există încă: îl creez când apeși Salvează."
CREATE_FAILED = "Nu am putut crea folderul."
NOT_SAVED = "Nu am salvat nimic. Corectează folderele marcate cu ✗."
SAVED = "Folderele au fost salvate."
CREATED = "Am creat folderul {path}."
BACK_ON_DESKTOP = "Folderele sunt din nou cele de pe Desktop."
NO_BACKUPS = "Încă nu există niciun backup."
SUMMARY_FAILED = "Nu am putut citi lista copiilor de siguranță (detalii în jurnal)."

# Backup names: <prefix>-YYYYMMDD-HHMMSS-micro.db, e.g. petrom-stergere-20261107-143210-000001.db
_BACKUP_NAME = re.compile(r"^petrom(?:-[a-z]+)?-(\d{8})-(\d{6})-\d+\.db$")


class SetariError(Exception):
    """Nothing was saved. `mesaj` is the Romanian headline, `rezultate` the per-folder checks."""

    def __init__(self, mesaj, rezultate):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.rezultate = rezultate


@dataclass(frozen=True)
class FolderCheck:
    cheie: str  # noi / procesate / erori
    cale: str  # the path as it will be saved (spaces and quotes removed)
    ok: bool
    mesaj: str  # Romanian, shown next to the box
    exista: bool = False

    def to_dict(self):
        return {"cheie": self.cheie, "cale": self.cale, "ok": self.ok, "mesaj": self.mesaj}


@dataclass
class SaveResult:
    mesaj: str
    note: list = field(default_factory=list)  # plain remarks, e.g. folders created
    avertizari: list = field(default_factory=list)  # needs her attention: PDFs left behind


def clean_path(text):
    """Remove spaces around the path and one pair of quotes.

    Explorer's "Copy as path" adds the quotes.
    """
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


# ---------- checking ----------


def check_folders(boxes, app_dir=PROJECT_ROOT):
    """Check the three boxes. Creates and saves nothing. Returns one FolderCheck per folder."""
    results = {key: _check_one(key, boxes.get(key, "")) for key in FOLDER_KEYS}

    app_key = _same_key(app_dir)
    for key, result in results.items():
        if result.ok and _is_inside(_same_key(result.cale), app_key):
            results[key] = replace(result, ok=False, mesaj=IN_APP_FOLDER)

    for key, result in results.items():
        if not result.ok:
            continue
        twin = next(
            (
                other
                for other, other_result in results.items()
                if other != key
                and other_result.cale
                and _same_key(other_result.cale) == _same_key(result.cale)
            ),
            None,
        )
        if twin:
            results[key] = replace(result, ok=False, mesaj=SAME_AS.format(label=LABELS[twin]))
    return list(results.values())


def _check_one(key, typed):
    text = clean_path(typed)
    if not text:
        return FolderCheck(key, text, False, EMPTY)
    if WINDOWS_BAD_CHARS & set(text):
        return FolderCheck(key, text, False, BAD_CHARS)
    path = Path(text)
    if not path.is_absolute():
        return FolderCheck(key, text, False, NOT_FULL)
    cale = str(path)
    try:
        if path.is_dir():
            if not _can_write(path):
                return FolderCheck(key, cale, False, CANT_WRITE, exista=True)
            mesaj = _pdfs_message(path) if key == "noi" else EXISTS
            return FolderCheck(key, cale, True, mesaj, exista=True)
        if path.exists():
            return FolderCheck(key, cale, False, IS_FILE, exista=True)
        start = _nearest_existing(path)
        if start is None:
            return FolderCheck(key, cale, False, NO_DRIVE)
        if not start.is_dir():
            return FolderCheck(key, cale, False, FILE_ON_THE_WAY)
        if not _can_create_folder(start):
            return FolderCheck(key, cale, False, CANT_CREATE)
    except OSError:
        logger.warning("Could not check folder path %r", text, exc_info=True)
        return FolderCheck(key, cale, False, CANT_READ)
    return FolderCheck(key, cale, True, WILL_CREATE)


def _pdfs_message(folder):
    try:
        n = _count_pdfs(folder)
    except OSError:
        logger.warning("Could not count the PDFs in %s", folder, exc_info=True)
        return EXISTS
    if n == 0:
        return "Există · niciun PDF de citit."
    return f"Există · {count_words(n, 'PDF', 'PDF-uri')} de citit."


def _count_pdfs(folder):
    """PDFs sitting directly in the folder: the same files a run would read."""
    return sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def _nearest_existing(path):
    """The closest part of the path that exists, or None (for example a missing disk)."""
    return next((p for p in path.parents if p.exists()), None)


def _can_write(folder):
    """Really try: write a temporary file and delete it. (os.access lies on Windows.)"""
    try:
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError:
        return False
    return True


def _can_create_folder(parent):
    """Really try: create an empty folder and remove it.

    Folder rights, not file rights: on Windows a user may create folders in C:\\ but not files.
    """
    try:
        os.rmdir(tempfile.mkdtemp(dir=parent))
    except OSError:
        return False
    return True


def _same_key(path):
    """A form of the path for comparing: full, tidied, without case on Windows, and with links,
    junctions and mapped drives followed for the parts that exist.

    On Windows, following links touches the disk and can fail (an offline network share);
    then the path is compared as written, so a dead share never breaks the checks.
    """
    try:
        full = os.path.realpath(path)
    except OSError:
        logger.warning("Could not follow links in %s, comparing it as written", path, exc_info=True)
        full = os.path.abspath(path)
    return os.path.normcase(full)


def _is_inside(key, folder_key):
    return key == folder_key or key.startswith(folder_key.rstrip(os.sep) + os.sep)


# ---------- saving ----------


def save_folders(conn, boxes, app_dir=PROJECT_ROOT):
    """Check, create missing folders, then save all three. Raises SetariError, saving nothing.

    The caller commits (the route uses `with conn:`).
    """
    results = check_folders(boxes, app_dir)
    if not all(r.ok for r in results):
        raise SetariError(NOT_SAVED, results)

    old = automation.get_folders(conn)
    note = []
    for i, result in enumerate(results):
        if result.exista:
            continue
        try:
            Path(result.cale).mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Could not create folder %s; folders not saved", result.cale)
            results[i] = replace(result, ok=False, mesaj=CREATE_FAILED)
            raise SetariError(NOT_SAVED, results) from None
        note.append(CREATED.format(path=result.cale))

    conn.executemany(
        "INSERT INTO setari (cheie, valoare) VALUES (?, ?)"
        " ON CONFLICT(cheie) DO UPDATE SET valoare = excluded.valoare",
        [(f"folder_{r.cheie}", r.cale) for r in results],
    )
    logger.info("Folders saved: %s", {r.cheie: r.cale for r in results})
    return SaveResult(SAVED, note, _left_pdfs_note(old.noi, Path(results[0].cale)))


def reset_folders(conn):
    """Forget the saved folders, so runs use the Desktop ones again. Moves no files."""
    old = automation.get_folders(conn)
    conn.executemany("DELETE FROM setari WHERE cheie = ?", [(f"folder_{k}",) for k in FOLDER_KEYS])
    new = automation.get_folders(conn)
    logger.info("Folders reset to the Desktop ones")
    return SaveResult(BACK_ON_DESKTOP, avertizari=_left_pdfs_note(old.noi, new.noi))


def _left_pdfs_note(old_noi, new_noi):
    """A warning when the Facturi-noi we stop reading still holds PDFs."""
    if _same_key(old_noi) == _same_key(new_noi):
        return []
    try:
        n = _count_pdfs(old_noi) if old_noi.is_dir() else 0
    except OSError:
        logger.warning("Could not count the PDFs left in %s", old_noi, exc_info=True)
        return []
    if n == 0:
        return []
    if n == 1:
        return [
            f"În vechiul folder {old_noi} a rămas 1 PDF. Mută-l în folderul nou ca să fie citit."
        ]
    return [
        f"În vechiul folder {old_noi} au rămas {count_words(n, 'PDF', 'PDF-uri')}. "
        "Mută-le în folderul nou ca să fie citite."
    ]


# ---------- backups ----------


def manual_backup(db_file, backup_dir):
    """The "Fă backup acum" button: a backup in its own group of 30."""
    return automation.backup_database(db_file, backup_dir, prefix=MANUAL_BACKUP_PREFIX)


def backup_summary(backup_dir):
    """For example "Ultimul backup: 07.11.2026 14:32 · 42 de copii" (all groups together)."""
    backup_dir = Path(backup_dir)
    try:
        names = [p.name for p in backup_dir.iterdir()] if backup_dir.is_dir() else []
    except OSError:
        logger.warning("Could not read the backup folder %s", backup_dir, exc_info=True)
        return SUMMARY_FAILED
    stamps = []
    for name in names:
        match = _BACKUP_NAME.match(name)
        if not match:
            continue
        try:
            stamps.append(datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S"))
        except ValueError:
            logger.warning("Backup %s has an impossible date in its name, not counted", name)
    if not stamps:
        return NO_BACKUPS
    newest = max(stamps)
    return f"Ultimul backup: {newest:%d.%m.%Y %H:%M} · {count_words(len(stamps), 'copie', 'copii')}"


# ---------- opening folders ----------


def open_folder(conn, name, data_dir):
    """Open one of the app's own folders in Explorer/Finder, creating it first if missing.

    `name` is one of OPENABLE; anything else raises KeyError. The page never sends a path,
    so no web page can make the app open an arbitrary folder.
    """
    data_dir = Path(data_dir)
    if name in FOLDER_KEYS:
        path = getattr(automation.get_folders(conn), name)
    elif name == "backup":
        path = data_dir / "backups"
    elif name == "date":
        path = data_dir
    else:
        raise KeyError(name)
    path.mkdir(parents=True, exist_ok=True)
    open_in_file_manager(path)
    return path


def open_in_file_manager(path):
    """Show the folder in Explorer (Windows) or Finder (Mac)."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - Windows only, a folder of our own
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
