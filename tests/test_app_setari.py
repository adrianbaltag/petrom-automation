"""The M7 routes: the Setări page, folders, manual backup and opening folders."""

import errno
import os

import pytest
from db_helpers import open_db
from fake_invoice import make_invoice_pdf

import petrom_dashboard
from petrom_dashboard import automation, setari


@pytest.fixture(autouse=True)
def desktop(tmp_path, monkeypatch):
    """A fake Desktop for every test here: the real one is never touched."""
    path = tmp_path / "Desktop"
    monkeypatch.setattr(automation, "desktop_dir", lambda: path)
    return path


@pytest.fixture()
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(setari, "open_in_file_manager", calls.append)
    return calls


def boxes(base):
    return {"noi": str(base / "A"), "procesate": str(base / "B"), "erori": str(base / "E")}


def saved_rows(app):
    with open_db(app.config["DATABASE"]) as conn:
        return dict(conn.execute("SELECT cheie, valoare FROM setari").fetchall())


# --- the page --------------------------------------------------------------------------


def test_version_is_one_constant():
    assert petrom_dashboard.__version__ == "0.7.0"


def test_setari_page_shows_folders_backup_and_about(client, app, data_dir, desktop):
    html = client.get("/setari").get_data(as_text=True)

    assert '<html lang="ro">' in html
    assert "Setări" in html
    assert str(desktop / "Facturi-noi") in html
    assert str(desktop / "Facturi-erori") in html
    assert "Încă nu există niciun backup." in html
    assert "Versiunea 0.7.0" in html
    assert str(data_dir) in html


def test_setari_page_lists_archived_companies(client, app):
    with open_db(app.config["DATABASE"]) as conn:
        conn.execute("INSERT INTO firme (cui, nume, arhivat) VALUES ('111', 'VECHE SRL', 1)")
        conn.execute("INSERT INTO firme (cui, nume, arhivat) VALUES ('222', 'ACTIVA SRL', 0)")

    html = client.get("/setari").get_data(as_text=True)

    assert "VECHE SRL" in html
    assert "ACTIVA SRL" not in html
    assert "Firme arhivate (1)" in html


def test_setari_page_with_no_archived_companies(client):
    assert "Nicio firmă arhivată." in client.get("/setari").get_data(as_text=True)


def test_setari_page_escapes_company_names(client, app):
    with open_db(app.config["DATABASE"]) as conn:
        conn.execute("INSERT INTO firme (cui, nume, arhivat) VALUES ('111', '<b>X</b>', 1)")

    html = client.get("/setari").get_data(as_text=True)

    assert "<b>X</b>" not in html
    assert "&lt;b&gt;X&lt;/b&gt;" in html


def test_setari_page_reports_a_database_failure(client, monkeypatch, app):
    def broken(conn):
        raise OSError("disk gone")

    monkeypatch.setattr(automation, "get_folders", broken)

    response = client.get("/setari")

    assert response.status_code == 500
    assert "Nu am putut citi setările" in response.get_data(as_text=True)
    log = (app.config["DATA_DIR"] / "logs" / "petrom.log").read_text(encoding="utf-8")
    assert "Could not read the settings page data" in log


def test_dashboard_links_to_setari_and_has_no_archived_link(client):
    html = client.get("/").get_data(as_text=True)

    assert 'href="/setari"' in html
    assert 'id="arhivate"' not in html
    assert 'id="dialog-arhivate"' not in html


def test_date_no_longer_carries_the_archived_count(client):
    assert "arhivate" not in client.get("/date").get_json()


# --- folders ---------------------------------------------------------------------------


def test_check_answers_per_folder_and_saves_nothing(client, app, tmp_path):
    (tmp_path / "A").mkdir()
    typed = boxes(tmp_path)
    typed["erori"] = "relativ"

    response = client.post("/setari/foldere/verifica", json=typed)

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is False
    assert [(f["cheie"], f["ok"]) for f in body["foldere"]] == [
        ("noi", True),
        ("procesate", True),
        ("erori", False),
    ]
    assert body["foldere"][0]["mesaj"] == "Există · niciun PDF de citit."
    assert saved_rows(app) == {}
    assert not (tmp_path / "B").exists()


def test_check_all_good_says_ok(client, tmp_path):
    body = client.post("/setari/foldere/verifica", json=boxes(tmp_path)).get_json()

    assert body["ok"] is True
    assert body["mesaj"] == "Toate cele 3 foldere sunt în regulă."


def test_save_creates_and_saves_the_folders(client, app, tmp_path):
    response = client.post("/setari/foldere", json=boxes(tmp_path))

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["mesaj"] == "Folderele au fost salvate."
    assert body["note"][0] == f"Am creat folderul {tmp_path / 'A'}."
    assert body["avertizari"] == []
    assert body["foldere"] == boxes(tmp_path)
    assert saved_rows(app) == {f"folder_{k}": v for k, v in boxes(tmp_path).items()}
    assert (tmp_path / "E").is_dir()


def test_save_refused_says_why_per_folder(client, app, tmp_path):
    typed = boxes(tmp_path)
    typed["procesate"] = typed["noi"]

    response = client.post("/setari/foldere", json=typed)

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["mesaj"] == "Nu am salvat nimic. Corectează folderele marcate cu ✗."
    assert body["foldere"][1]["mesaj"] == "Același folder ca Facturi-noi."
    assert saved_rows(app) == {}


def test_save_database_failure_is_reported_and_logged(client, app, tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(setari, "save_folders", broken)

    response = client.post("/setari/foldere", json=boxes(tmp_path))

    assert response.status_code == 500
    assert response.get_json() == {"ok": False, "mesaj": "Nu am putut salva (detalii în jurnal)."}
    log = (app.config["DATA_DIR"] / "logs" / "petrom.log").read_text(encoding="utf-8")
    assert "Saving the folders failed" in log


@pytest.mark.parametrize(
    "body",
    [None, ["a"], {"noi": "x", "procesate": "y"}, {"noi": 1, "procesate": "y", "erori": "z"}],
)
def test_folder_routes_refuse_bodies_not_sent_by_the_page(client, body, app):
    for url in ("/setari/foldere", "/setari/foldere/verifica"):
        response = client.post(url, json=body) if body is not None else client.post(url)

        assert response.status_code == 400
        assert response.get_json()["ok"] is False
    assert saved_rows(app) == {}


def test_reset_goes_back_to_the_desktop(client, app, tmp_path, desktop):
    client.post("/setari/foldere", json=boxes(tmp_path))
    (tmp_path / "A" / "f.pdf").write_bytes(b"%PDF")

    response = client.post("/setari/foldere/desktop")

    body = response.get_json()
    assert response.status_code == 200
    assert body["mesaj"] == "Folderele sunt din nou cele de pe Desktop."
    assert body["foldere"]["noi"] == str(desktop / "Facturi-noi")
    assert body["avertizari"][0].startswith(f"În vechiul folder {tmp_path / 'A'} a rămas 1 PDF.")
    assert saved_rows(app) == {}


def test_post_from_another_website_cannot_change_folders(client, app, tmp_path):
    response = client.post(
        "/setari/foldere", json=boxes(tmp_path), headers={"Origin": "http://evil.example"}
    )

    assert response.status_code == 403
    assert saved_rows(app) == {}


def test_a_run_uses_the_folders_saved_in_setari_even_on_another_drive(
    client, tmp_path, monkeypatch, desktop
):
    """The M3 open item: folders changed in Setări, on a different drive than Facturi-noi."""
    client.post("/setari/foldere", json=boxes(tmp_path))
    make_invoice_pdf(tmp_path / "A" / "f.pdf", data="05.06.2026")

    def rename_across_drives(*args, **kwargs):
        raise OSError(errno.EXDEV, "different drive")

    monkeypatch.setattr(os, "rename", rename_across_drives)

    body = client.post("/ruleaza").get_json()

    assert body["adaugate"] == ["f.pdf"]
    assert (tmp_path / "B" / "2026-06" / "f.pdf").exists()
    assert not (tmp_path / "A" / "f.pdf").exists()
    assert not desktop.exists()  # the Desktop default was never used


# --- backup ----------------------------------------------------------------------------


def test_backup_now_makes_a_copy_and_returns_the_summary(client, data_dir):
    response = client.post("/setari/backup")

    body = response.get_json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["mesaj"] == "Backup făcut."
    assert body["rezumat"].startswith("Ultimul backup: ")
    assert body["rezumat"].endswith("· 1 copie")
    assert len(list((data_dir / "backups").glob("petrom-manual-*.db"))) == 1


def test_backup_failure_is_reported_and_logged(client, app, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(setari, "manual_backup", broken)

    response = client.post("/setari/backup")

    assert response.status_code == 500
    assert response.get_json() == {
        "ok": False,
        "mesaj": "Nu am putut face backup-ul (detalii în jurnal).",
    }
    log = (app.config["DATA_DIR"] / "logs" / "petrom.log").read_text(encoding="utf-8")
    assert "Manual backup failed" in log


# --- opening folders -------------------------------------------------------------------


def test_open_a_known_folder(client, opened, desktop, data_dir):
    assert client.post("/setari/deschide/erori").get_json() == {"ok": True}
    assert client.post("/setari/deschide/backup").get_json() == {"ok": True}

    assert opened == [desktop / "Facturi-erori", data_dir / "backups"]


def test_open_an_unknown_name_is_refused(client, opened):
    response = client.post("/setari/deschide/Windows")

    assert response.status_code == 404
    assert opened == []


def test_open_needs_post(client, opened):
    assert client.get("/setari/deschide/date").status_code == 405
    assert opened == []


def test_open_failure_is_reported_and_logged(client, app, monkeypatch):
    def broken(path):
        raise OSError("no file manager")

    monkeypatch.setattr(setari, "open_in_file_manager", broken)

    response = client.post("/setari/deschide/date")

    assert response.status_code == 500
    assert response.get_json() == {
        "ok": False,
        "mesaj": "Nu am putut deschide folderul (detalii în jurnal).",
    }
    log = (app.config["DATA_DIR"] / "logs" / "petrom.log").read_text(encoding="utf-8")
    assert "Could not open folder 'date'" in log


# --- review round 1 -------------------------------------------------------------------


def test_pyproject_version_matches_the_app_version():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")

    assert f'version = "{petrom_dashboard.__version__}"' in text


def test_backup_made_but_summary_failing_still_says_backup_done(client, data_dir, monkeypatch):
    def broken(backup_dir):
        raise OSError("disk hiccup")

    monkeypatch.setattr(setari, "backup_summary", broken)

    response = client.post("/setari/backup")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["mesaj"] == "Backup făcut."
    assert body["rezumat"] == "Nu am putut citi lista copiilor de siguranță (detalii în jurnal)."
    assert len(list((data_dir / "backups").glob("petrom-manual-*.db"))) == 1


def test_setari_page_opens_even_if_the_backup_summary_fails(client, monkeypatch):
    def broken(backup_dir):
        raise OSError("disk hiccup")

    monkeypatch.setattr(setari, "backup_summary", broken)

    response = client.get("/setari")

    assert response.status_code == 200
    assert "Nu am putut citi lista copiilor" in response.get_data(as_text=True)


@pytest.mark.parametrize("url", ["/", "/setari", "/date", "/firme/arhivate"])
def test_pages_and_data_are_never_reused_from_the_browser_cache(client, url):
    # Otherwise the browser's Back arrow shows an old table or an old archived list.
    assert client.get(url).headers["Cache-Control"] == "no-store"


def test_style_and_scripts_may_be_cached(client):
    assert client.get("/static/style.css").headers.get("Cache-Control") != "no-store"


def test_check_crash_returns_json_and_is_logged(client, app, tmp_path, monkeypatch):
    def broken(boxes):
        raise OSError("unexpected")

    monkeypatch.setattr(setari, "check_folders", broken)

    response = client.post("/setari/foldere/verifica", json=boxes(tmp_path))

    assert response.status_code == 500
    assert response.get_json() == {
        "ok": False,
        "mesaj": "Nu am putut verifica folderele (detalii în jurnal).",
    }
    log = (app.config["DATA_DIR"] / "logs" / "petrom.log").read_text(encoding="utf-8")
    assert "Checking the folders failed" in log
