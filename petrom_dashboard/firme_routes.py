"""Web routes for changes made by hand (M5). All answers are JSON: {"ok": ..., "mesaj": ...}.

A Flask Blueprint is a group of routes kept in its own file; create_app() plugs it in.
The "other websites" guard in create_app() runs before every route here too.
"""

import logging
from contextlib import closing
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from petrom_dashboard import automation, firme
from petrom_dashboard import dashboard as table
from petrom_dashboard.db import connect
from petrom_dashboard.money import format_lei

logger = logging.getLogger(__name__)

bp = Blueprint("firme", __name__)

BAD_REQUEST = "Cerere greșită: datele nu au venit din formular."
SAVE_FAILED = "Nu am putut salva (detalii în jurnal)."
DELETE_BACKUP_PREFIX = "petrom-stergere"  # own group of 30: never pushes out run backups
BACKUP_FAILED = "Nu am putut face copia de siguranță, așa că nu am șters factura."


def _fields(*names, body_optional=False):
    """The named text fields of the JSON body. None if the body is not what the page sends."""
    body = request.get_json(silent=True)
    if body is None and body_optional and not request.get_data():
        body = {}
    if not isinstance(body, dict):
        logger.warning("Refused %s %s: body is not a JSON object", request.method, request.path)
        return None
    values = [body.get(name, "") for name in names]
    if not all(isinstance(value, str) for value in values):
        logger.warning("Refused %s %s: a field is not text", request.method, request.path)
        return None
    return values


def _refused(err):
    status = 404 if isinstance(err, (firme.CompanyNotFound, firme.InvoiceNotFound)) else 400
    return jsonify(ok=False, mesaj=err.mesaj), status


def _change(action, *args):
    """Run `action(conn, *args)` and commit it. Any refusal or error saves nothing."""
    db_file = current_app.config["DATABASE"]
    with closing(connect(db_file)) as conn, conn:
        return action(conn, *args)


def _answer(action, *args, ok=None):
    """Run a change and turn the result or the refusal into a JSON answer."""
    try:
        result = _change(action, *args)
    except firme.ArchivedCompany as err:
        return jsonify(
            ok=False, mesaj=err.mesaj, arhivata={"id": err.firma_id, "nume": err.nume}
        ), 409
    except firme.FirmaError as err:
        logger.info("Refused %s%s: %s", action.__name__, args, err.mesaj)
        return _refused(err)
    except Exception:
        logger.exception("Change %s%s failed", action.__name__, args)
        return jsonify(ok=False, mesaj=SAVE_FAILED), 500
    return jsonify(ok=True, **(ok(result) if ok else {}))


@bp.post("/firme")
def add():
    fields = _fields("cui", "nume", "max")
    if fields is None:
        return jsonify(ok=False, mesaj=BAD_REQUEST), 400
    return _answer(
        firme.add_company, *fields, table.current_month(), ok=lambda firma_id: {"id": firma_id}
    )


@bp.post("/firme/<int:firma_id>")
def edit(firma_id):
    fields = _fields("nume", "max")
    if fields is None:
        return jsonify(ok=False, mesaj=BAD_REQUEST), 400
    return _answer(firme.update_company, firma_id, *fields, table.current_month())


@bp.post("/firme/<int:firma_id>/arhiveaza")
def archive(firma_id):
    return _answer(firme.archive_company, firma_id)


@bp.post("/firme/<int:firma_id>/restaureaza")
def restore(firma_id):
    """Restore an archived company. The Adaugă form may send the max typed there."""
    fields = _fields("max", body_optional=True)
    if fields is None:
        return jsonify(ok=False, mesaj=BAD_REQUEST), 400
    return _answer(
        firme.restore_company,
        firma_id,
        *fields,
        table.current_month(),
        ok=lambda max_bani: {} if max_bani is None else {"max_text": format_lei(max_bani)},
    )


@bp.get("/firme/arhivate")
def archived():
    return _answer(firme.archived_companies, ok=lambda rows: {"firme": [dict(r) for r in rows]})


@bp.get("/firme/<int:firma_id>/facturi")
def invoices(firma_id):
    luna = table.current_month()
    return _answer(
        firme.month_invoices,
        firma_id,
        luna,
        ok=lambda rows: {"facturi": rows, "luna_text": table.month_label(luna)},
    )


@bp.post("/facturi/<int:factura_id>/sterge")
def delete_invoice(factura_id):
    """Delete a wrong invoice. A backup of the database is made first; no backup, no delete."""
    db_file = current_app.config["DATABASE"]
    try:
        _change(firme.get_invoice, factura_id)  # unknown id: refuse before making a backup
    except firme.FirmaError as err:
        return _refused(err)
    except Exception:
        logger.exception("Could not read invoice id %s before deleting it", factura_id)
        return jsonify(ok=False, mesaj=SAVE_FAILED), 500
    try:
        automation.backup_database(
            db_file, Path(current_app.config["DATA_DIR"]) / "backups", prefix=DELETE_BACKUP_PREFIX
        )
    except Exception:
        logger.exception("Backup before deleting invoice id %s failed; nothing deleted", factura_id)
        return jsonify(ok=False, mesaj=BACKUP_FAILED), 500
    return _answer(firme.delete_invoice, factura_id)
