"""Petrom Dashboard: a small local web app that tracks company invoice totals per month."""

import logging
from contextlib import closing
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from petrom_dashboard import automation, firme_routes
from petrom_dashboard import dashboard as table  # "dashboard" is also the page's view name
from petrom_dashboard.db import connect, init_db
from petrom_dashboard.paths import default_data_dir
from petrom_dashboard.setup_logging import setup_logging

logger = logging.getLogger(__name__)

UNEXPECTED_RUN_ERROR = (
    "Automatizarea s-a oprit din cauza unei erori neașteptate (detalii în jurnal)."
)
REFUSED = "Cerere refuzată: nu vine din dashboard."
DATA_FAILED = "Nu am putut citi datele (detalii în jurnal)."

# The only names the dashboard is opened with. Another name means a website pointing its
# own name at this computer (DNS rebinding), so it is refused.
ALLOWED_HOST_NAMES = {"127.0.0.1", "localhost"}


def create_app(test_config=None):
    """Build the app. Tests pass test_config to use a temporary data folder."""
    app = Flask(__name__)
    app.config.from_mapping(DATA_DIR=default_data_dir())
    if test_config:
        app.config.from_mapping(test_config)

    data_dir = Path(app.config["DATA_DIR"])
    app.config["DATABASE"] = data_dir / "petrom.db"

    setup_logging(data_dir / "logs" / "petrom.log")
    init_db(app.config["DATABASE"])
    logger.info("App started, data folder: %s", data_dir)

    @app.before_request
    def refuse_other_websites():
        """Only the dashboard's own page may talk to the app.

        Listening on 127.0.0.1 keeps other computers out, but not other websites open in
        her browser: they could send a hidden form here. Browsers always add an Origin
        header to such a form, so a POST from any other origin is refused.
        """
        host_name = request.host.rsplit(":", 1)[0]
        if host_name not in ALLOWED_HOST_NAMES:
            logger.warning(
                "Refused %s %s: unknown host %r", request.method, request.path, request.host
            )
            return jsonify(ok=False, mesaj=REFUSED), 403
        origin = request.headers.get("Origin")
        if (
            request.method == "POST"
            and origin is not None
            and origin != request.host_url.rstrip("/")
        ):
            logger.warning("Refused POST %s from origin %r", request.path, origin)
            return jsonify(ok=False, mesaj=REFUSED), 403
        return None

    @app.route("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/date")
    def date_tabel():
        """The table's rows as JSON, for the filter the page sends (none = this month).

        `?luna=2026-09`, `?zile=7` or `?zile=30`, or `?de=2026-10-01&pana=2026-10-15`.
        The page reads it on load, on each filter change and after each run.
        """
        today = table.today()
        try:
            period = table.period_from_args(request.args, today)
        except table.PeriodError as err:
            logger.warning("Refused filter %s: %s", dict(request.args), err.mesaj)
            return jsonify(ok=False, mesaj=err.mesaj), 400
        try:
            with closing(connect(app.config["DATABASE"])) as conn:
                if period.luna:
                    rows = table.month_rows(conn, period.luna)
                else:
                    rows = table.range_rows(conn, period.start, period.end)
                # The edit window's max box always starts from this month's max.
                boxes = table.edit_max_inputs(conn, table.current_month(today))
                for row in rows:
                    row["max_input"] = boxes.get(row["id"], "")
                luni = table.month_choices(conn, today)
                arhivate = table.archived_count(conn)
        except Exception:
            logger.exception("Could not read the dashboard rows for %s", period.titlu)
            return jsonify(ok=False, mesaj=DATA_FAILED), 500
        answer = {
            "ok": True,
            "tip": "luna" if period.luna else "perioada",
            "titlu": period.titlu,
            "firme": rows,
            "luni": luni,
            "arhivate": arhivate,
        }
        if period.luna:
            answer["luna"] = period.luna
        else:
            answer["de"], answer["pana"] = period.start.isoformat(), period.end.isoformat()
        return jsonify(answer)

    @app.post("/ruleaza")
    def ruleaza():
        """Run the automation (the button calls this) and send back the summary as JSON."""
        db_file = app.config["DATABASE"]
        try:
            with closing(connect(db_file)) as conn:
                folders = automation.get_folders(conn)
            summary = automation.run_automation(db_file, folders, data_dir)
        except automation.AlreadyRunning as err:
            return jsonify(ok=False, mesaj=err.mesaj), 409
        except automation.RunError as err:
            return jsonify(ok=False, mesaj=err.mesaj), 500
        except Exception:
            logger.exception("Automation run crashed")
            return jsonify(ok=False, mesaj=UNEXPECTED_RUN_ERROR), 500
        return jsonify(summary.to_dict())

    app.register_blueprint(firme_routes.bp)
    return app
