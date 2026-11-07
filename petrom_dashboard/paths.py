"""Where the app keeps its data (database, backups, logs, config).

- Windows (person B): %LOCALAPPDATA%\\PetromDashboard. Outside OneDrive, so syncing can't lock
  or duplicate the database, and outside the app folder, so updating the app never touches it.
- Mac (development): the project's own data/ folder, ignored by Git.
- PETROM_DATA_DIR, when set, wins over both (tests use it).
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def default_data_dir():
    override = os.environ.get("PETROM_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "PetromDashboard"
    return PROJECT_ROOT / "data"
