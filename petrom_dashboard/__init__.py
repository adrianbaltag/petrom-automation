"""Petrom Dashboard: a small local web app that tracks company invoice totals per month."""

import logging
from pathlib import Path

from flask import Flask, render_template

from petrom_dashboard.db import init_db
from petrom_dashboard.paths import default_data_dir
from petrom_dashboard.setup_logging import setup_logging

logger = logging.getLogger(__name__)


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

    @app.route("/")
    def dashboard():
        return render_template("index.html")

    return app
