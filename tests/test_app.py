def test_dashboard_page_opens(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Petrom" in response.get_data(as_text=True)


def test_page_is_in_romanian(client):
    html = client.get("/").get_data(as_text=True)

    assert '<html lang="ro">' in html


def test_app_creates_data_folder_and_database(app, data_dir):
    assert (data_dir / "petrom.db").exists()


def test_app_writes_a_log_file(app, data_dir):
    assert (data_dir / "logs" / "petrom.log").exists()


def point_folders_at(app, base):
    """Store the three folder paths in the settings, like Setări will in M7."""
    from db_helpers import open_db

    with open_db(app.config["DATABASE"]) as conn:
        for key in ("noi", "procesate", "erori"):
            conn.execute(
                "INSERT INTO setari (cheie, valoare) VALUES (?, ?)",
                (f"folder_{key}", str(base / key)),
            )


def test_ruleaza_runs_and_returns_the_summary(app, client, tmp_path):
    point_folders_at(app, tmp_path)

    response = client.post("/ruleaza")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["mesaj"] == "Niciun PDF nou în Facturi-noi."
    assert body["adaugate"] == [] and body["erori"] == [] and body["note"] == []
    assert (tmp_path / "noi").is_dir()


def test_ruleaza_says_already_running_when_locked(app, client, data_dir, tmp_path):
    from petrom_dashboard.automation import LOCK_FILE_NAME, RunLock

    point_folders_at(app, tmp_path)
    with RunLock(data_dir / LOCK_FILE_NAME):
        response = client.post("/ruleaza")

    assert response.status_code == 409
    assert response.get_json() == {"ok": False, "mesaj": "Automatizarea rulează deja."}


def test_ruleaza_reports_a_failed_backup(app, client, tmp_path, monkeypatch):
    from petrom_dashboard import automation

    def broken_backup(*args, **kwargs):
        raise OSError("disk full")

    point_folders_at(app, tmp_path)
    (tmp_path / "noi").mkdir()
    (tmp_path / "noi" / "f.pdf").write_bytes(b"any pdf: the backup comes before reading")
    monkeypatch.setattr(automation, "backup_database", broken_backup)
    response = client.post("/ruleaza")

    assert response.status_code == 500
    assert response.get_json()["ok"] is False
    assert "backup" in response.get_json()["mesaj"].lower()


def test_ruleaza_only_accepts_post(client):
    assert client.get("/ruleaza").status_code == 405


def test_ruleaza_crash_returns_json_and_is_logged(app, client, tmp_path, monkeypatch, caplog):
    from petrom_dashboard import UNEXPECTED_RUN_ERROR, automation

    def crash(*args, **kwargs):
        raise RuntimeError("boom")

    point_folders_at(app, tmp_path)
    monkeypatch.setattr(automation, "run_automation", crash)
    response = client.post("/ruleaza")

    assert response.status_code == 500
    assert response.get_json() == {"ok": False, "mesaj": UNEXPECTED_RUN_ERROR}
    assert any(r.exc_info and "crashed" in r.getMessage() for r in caplog.records)


# ---------- guard against other websites ----------


def test_post_from_another_website_is_refused(app, client, tmp_path):
    point_folders_at(app, tmp_path)

    response = client.post("/ruleaza", headers={"Origin": "http://evil.example"})

    assert response.status_code == 403
    assert response.get_json()["ok"] is False
    assert not (tmp_path / "noi").exists()  # the run never started


def test_post_from_the_dashboard_itself_is_allowed(app, client, tmp_path):
    point_folders_at(app, tmp_path)

    response = client.post("/ruleaza", headers={"Origin": "http://localhost"})

    assert response.status_code == 200


def test_request_with_a_foreign_host_name_is_refused(client):
    # DNS rebinding: a website whose name points at 127.0.0.1 would send its own name.
    assert client.get("/", base_url="http://evil.example").status_code == 403
    assert client.get("/", base_url="http://127.0.0.1:8765").status_code == 200
