"""One logging setup for a project.

Copy this file and test_setup_logging.py into a project. Never import them from ~/.claude:
a prod VM can't reach this folder.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_BYTES = 5_000_000
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(log_file, level=logging.INFO, max_bytes=MAX_BYTES, backup_count=BACKUP_COUNT):
    """Send log lines to a rotating file and the terminal. Call once when the program starts."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[file_handler, logging.StreamHandler()],
        force=True,  # Replaces earlier handlers, so calling this twice can't double every line.
    )
