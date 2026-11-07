"""Web routes for the Setări page (M7). Changes answer as JSON: {"ok": ..., "mesaj": ...}.

The "other websites" guard in create_app() runs before every route here too, so no other
web page open in her browser can change the folders or open a folder.
"""

import logging
from contextlib import closing
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request

import petrom_dashboard
from petrom_dashboard import automation, firme, setari
from petrom_dashboard.db import connect
from petrom_dashboard.firme_routes import BAD_REQUEST, SAVE_FAILED

logger = logging.getLogger(__name__)

bp = Blueprint("setari", __name__)

PAGE_FAILED = "Nu am putut citi setările (detalii în jurnal)."
ALL_GOOD = "Toate cele 3 foldere sunt în regulă."
CHECK_CRASHED = "Nu am putut verifica folderele (detalii în jurnal)."
CHECK_FAILED = "Unele foldere nu sunt în regulă. Vezi mesajele marcate cu ✗."
BACKUP_DONE = "Backup făcut."
BACKUP_FAILED = "Nu am putut face backup-ul (detalii în jurnal)."
OPEN_FAILED = "Nu am putut deschide folderul (detalii în jurnal)."
UNKNOWN_FOLDER = "Folder necunoscut."


def _data_dir():
    return Path(current_app.config["DATA_DIR"])


def _db():
    return closing(connect(current_app.config["DATABASE"]))


def _boxes():
    """The three folder boxes from the JSON body, or None if it is not what the page sends."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not all(
        isinstance(body.get(key), str) for key in setari.FOLDER_KEYS
    ):
        logger.warning("Refused %s %s: not the three folder boxes", request.method, request.path)
        return None
    return {key: body[key] for key in setari.FOLDER_KEYS}


def _folder_paths(conn):
    folders = automation.get_folders(conn)
    return {key: str(getattr(folders, key)) for key in setari.FOLDER_KEYS}


@bp.get("/setari")
def page():
    try:
        with _db() as conn:
            foldere = _folder_paths(conn)
            arhivate = [dict(row) for row in firme.archived_companies(conn)]
    except Exception:
        logger.exception("Could not read the settings page data")
        return PAGE_FAILED, 500
    return render_template(
        "setari.html",
        foldere=foldere,
        etichete=setari.LABELS,
        arhivate=arhivate,
        backup=_backup_summary(),
        versiune=petrom_dashboard.__version__,
        folder_date=str(_data_dir()),
    )


@bp.post("/setari/foldere/verifica")
def check():
    """Check the three boxes as typed. Saves and creates nothing."""
    boxes = _boxes()
    if boxes is None:
        return jsonify(ok=False, mesaj=BAD_REQUEST), 400
    try:
        results = setari.check_folders(boxes)
    except Exception:
        logger.exception("Checking the folders failed")
        return jsonify(ok=False, mesaj=CHECK_CRASHED), 500
    all_ok = all(r.ok for r in results)
    return jsonify(
        ok=all_ok,
        mesaj=ALL_GOOD if all_ok else CHECK_FAILED,
        foldere=[r.to_dict() for r in results],
    )


@bp.post("/setari/foldere")
def save():
    """Check, create missing folders and save. Any refusal saves nothing."""
    boxes = _boxes()
    if boxes is None:
        return jsonify(ok=False, mesaj=BAD_REQUEST), 400
    try:
        with _db() as conn, conn:
            result = setari.save_folders(conn, boxes)
            foldere = _folder_paths(conn)
    except setari.SetariError as err:
        logger.info("Folders not saved: %s", [r.to_dict() for r in err.rezultate if not r.ok])
        return jsonify(ok=False, mesaj=err.mesaj, foldere=[r.to_dict() for r in err.rezultate]), 400
    except Exception:
        logger.exception("Saving the folders failed")
        return jsonify(ok=False, mesaj=SAVE_FAILED), 500
    return _saved(result, foldere)


@bp.post("/setari/foldere/desktop")
def reset():
    """Revino la Desktop: forget the saved folders."""
    try:
        with _db() as conn, conn:
            result = setari.reset_folders(conn)
            foldere = _folder_paths(conn)
    except Exception:
        logger.exception("Resetting the folders failed")
        return jsonify(ok=False, mesaj=SAVE_FAILED), 500
    return _saved(result, foldere)


def _saved(result, foldere):
    return jsonify(
        ok=True, mesaj=result.mesaj, note=result.note, avertizari=result.avertizari, foldere=foldere
    )


def _backup_summary():
    """The backup line. A failure here never hides the rest of the page or a backup made."""
    try:
        return setari.backup_summary(_data_dir() / "backups")
    except Exception:
        logger.exception("Could not build the backup summary")
        return setari.SUMMARY_FAILED


@bp.post("/setari/backup")
def backup_now():
    try:
        setari.manual_backup(current_app.config["DATABASE"], _data_dir() / "backups")
    except Exception:
        logger.exception("Manual backup failed")
        return jsonify(ok=False, mesaj=BACKUP_FAILED), 500
    return jsonify(ok=True, mesaj=BACKUP_DONE, rezumat=_backup_summary())


@bp.post("/setari/deschide/<name>")
def open_folder(name):
    """Open one of the app's own folders. The page sends only its name, never a path."""
    if name not in setari.OPENABLE:
        logger.warning("Refused to open unknown folder name %r", name)
        return jsonify(ok=False, mesaj=UNKNOWN_FOLDER), 404
    try:
        with _db() as conn:
            setari.open_folder(conn, name, _data_dir())
    except Exception:
        logger.exception("Could not open folder %r", name)
        return jsonify(ok=False, mesaj=OPEN_FAILED), 500
    return jsonify(ok=True)
