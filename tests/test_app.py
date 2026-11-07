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
