from pathlib import Path

from petrom_dashboard import paths
from petrom_dashboard.paths import default_data_dir

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_on_mac_data_lives_in_the_project_data_folder(monkeypatch):
    monkeypatch.delenv("PETROM_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")

    assert default_data_dir() == PROJECT_ROOT / "data"


def test_on_windows_data_lives_in_local_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("PETROM_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_data_dir() == tmp_path / "PetromDashboard"


def test_on_windows_without_localappdata_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("PETROM_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert default_data_dir() == Path.home() / "AppData" / "Local" / "PetromDashboard"


def test_env_variable_overrides_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PETROM_DATA_DIR", str(tmp_path))

    assert default_data_dir() == tmp_path
