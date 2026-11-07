"""The repo is public: real data and secrets must never be tracked by Git."""

import subprocess
from pathlib import Path

FORBIDDEN_SUFFIXES = {".pdf", ".db", ".sqlite", ".log", ".ini"}
FORBIDDEN_NAMES = {".env"}
FORBIDDEN_FOLDERS = {"samples", "data"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def is_forbidden(path):
    """True for a file that must never be committed."""
    path = Path(path)
    if path.parts and path.parts[0] in FORBIDDEN_FOLDERS:
        return True
    if path.name.lower() in FORBIDDEN_NAMES or path.name.lower().startswith(".env."):
        return True
    return path.suffix.lower() in FORBIDDEN_SUFFIXES


def tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [Path(line) for line in result.stdout.splitlines()]


def test_no_forbidden_files_are_tracked():
    assert [str(path) for path in tracked_files() if is_forbidden(path)] == []


def test_dotenv_files_are_forbidden():
    assert is_forbidden(".env")
    assert is_forbidden("config/.env")
    assert is_forbidden(".env.local")


def test_data_and_samples_folders_are_forbidden():
    assert is_forbidden("data/petrom.db.bak")
    assert is_forbidden("samples/factura.txt")


def test_data_files_are_forbidden():
    assert is_forbidden("Factura_12.PDF")
    assert is_forbidden("petrom.db")


def test_code_files_are_allowed():
    assert not is_forbidden("petrom_dashboard/db.py")
    assert not is_forbidden(".gitignore")
