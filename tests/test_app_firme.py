"""The M5 routes: add, edit, archive, restore, invoice list and invoice delete, as JSON."""

import pytest
from db_helpers import open_db

from petrom_dashboard.dashboard import current_month

MONTH = current_month()
CUI = "46133455"


def db(app):
    return open_db(app.config["DATABASE"])


def add_via_api(client, cui=CUI, nume="ALFA SRL", max_text=""):
    return client.post("/firme", json={"cui": cui, "nume": nume, "max": max_text})


def add_invoice(app, firma_id, total_bani=100_00, numar="FP1"):
    with db(app) as conn:
        return conn.execute(
            "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (firma_id, f"{MONTH}-03", total_bani, f"{numar}.pdf", f"amp-{numar}", numar),
        ).lastrowid


def table_names(client):
    return [row["nume"] for row in client.get("/date").get_json()["firme"]]


# --- Add ------------------------------------------------------------------------------


def test_add_company_shows_it_in_the_table(client):
    response = add_via_api(client, cui="RO46133455", max_text="5.000")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True and isinstance(body["id"], int)
    row = client.get("/date").get_json()["firme"][0]
    assert (row["cui"], row["nume"], row["max_bani"]) == (CUI, "ALFA SRL", 5000_00)


def test_add_with_bad_cui_says_why(client):
    response = add_via_api(client, cui="46133445")

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "mesaj": "CUI invalid, verifică cifrele."}


def test_add_active_duplicate_is_refused_with_the_reason(client):
    add_via_api(client)

    response = add_via_api(client, nume="ALTA SRL")

    assert response.status_code == 400
    assert "Un CUI poate aparține unei singure firme" in response.get_json()["mesaj"]


def test_add_archived_cui_offers_restore(client):
    firma_id = add_via_api(client).get_json()["id"]
    client.post(f"/firme/{firma_id}/arhiveaza")

    response = add_via_api(client, nume="ALTA SRL")

    assert response.status_code == 409
    body = response.get_json()
    assert body["ok"] is False
    assert body["arhivata"] == {"id": firma_id, "nume": "ALFA SRL"}


@pytest.mark.parametrize("payload", [None, "text", ["list"]])
def test_add_without_a_json_object_is_refused(client, payload):
    if payload is None:
        response = client.post("/firme", data="cui=1", content_type="text/plain")
    else:
        response = client.post("/firme", json=payload)

    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_add_with_non_text_fields_is_refused(client):
    response = client.post("/firme", json={"cui": 46133455, "nume": "ALFA", "max": ""})

    assert response.status_code == 400


def test_add_from_another_website_is_refused(client):
    response = client.post(
        "/firme",
        json={"cui": CUI, "nume": "ALFA", "max": ""},
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403


# --- Edit -----------------------------------------------------------------------------


def test_edit_name_and_max(client):
    firma_id = add_via_api(client, max_text="5000").get_json()["id"]

    response = client.post(f"/firme/{firma_id}", json={"nume": "ALFA NOU", "max": "6.000"})

    assert response.get_json() == {"ok": True}
    row = client.get("/date").get_json()["firme"][0]
    assert (row["nume"], row["max_bani"]) == ("ALFA NOU", 6000_00)


def test_edit_cannot_empty_the_max(client):
    firma_id = add_via_api(client, max_text="5000").get_json()["id"]

    response = client.post(f"/firme/{firma_id}", json={"nume": "ALFA", "max": ""})

    assert response.status_code == 400
    assert response.get_json()["mesaj"] == "Max-ul nu poate fi șters, doar schimbat."


def test_edit_unknown_company_is_404(client):
    response = client.post("/firme/999", json={"nume": "ALFA", "max": ""})

    assert response.status_code == 404
    assert response.get_json()["ok"] is False


# --- Archive and restore --------------------------------------------------------------


def test_archive_hides_and_restore_brings_back(client):
    firma_id = add_via_api(client).get_json()["id"]

    assert client.post(f"/firme/{firma_id}/arhiveaza").get_json() == {"ok": True}
    assert table_names(client) == []
    assert client.get("/firme/arhivate").get_json() == {
        "ok": True,
        "firme": [{"id": firma_id, "cui": CUI, "nume": "ALFA SRL"}],
    }

    assert client.post(f"/firme/{firma_id}/restaureaza").get_json() == {"ok": True}
    assert table_names(client) == ["ALFA SRL"]
    assert client.get("/firme/arhivate").get_json()["firme"] == []


@pytest.mark.parametrize("action", ["arhiveaza", "restaureaza"])
def test_archive_or_restore_unknown_company_is_404(client, action):
    assert client.post(f"/firme/999/{action}").status_code == 404


# --- Invoices -------------------------------------------------------------------------


def test_invoice_list_for_this_month(app, client):
    firma_id = add_via_api(client).get_json()["id"]
    add_invoice(app, firma_id, total_bani=1234_56, numar="FP7")

    body = client.get(f"/firme/{firma_id}/facturi").get_json()

    assert body["ok"] is True
    assert body["luna_text"]  # e.g. "noiembrie 2026"
    [row] = body["facturi"]
    assert (row["numar"], row["total_text"], row["fisier"]) == ("FP7", "1.234,56 lei", "FP7.pdf")


def test_invoice_list_of_unknown_company_is_404(client):
    assert client.get("/firme/999/facturi").status_code == 404


def test_delete_invoice_makes_a_backup_first_and_lowers_the_total(app, client, data_dir):
    firma_id = add_via_api(client, max_text="5000").get_json()["id"]
    factura_id = add_invoice(app, firma_id, total_bani=100_00)

    response = client.post(f"/facturi/{factura_id}/sterge")

    assert response.get_json() == {"ok": True}
    assert len(list((data_dir / "backups").glob("petrom-*.db"))) == 1
    assert client.get("/date").get_json()["firme"][0]["total_bani"] == 0


def test_delete_invoice_is_refused_when_the_backup_fails(app, client, monkeypatch):
    from petrom_dashboard import automation

    firma_id = add_via_api(client).get_json()["id"]
    factura_id = add_invoice(app, firma_id)

    def broken_backup(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(automation, "backup_database", broken_backup)

    response = client.post(f"/facturi/{factura_id}/sterge")

    assert response.status_code == 500
    assert "copia de siguranță" in response.get_json()["mesaj"]
    with db(app) as conn:
        assert conn.execute("SELECT COUNT(*) FROM facturi").fetchone()[0] == 1


def test_delete_unknown_invoice_is_404_and_makes_no_backup(client, data_dir):
    response = client.post("/facturi/999/sterge")

    assert response.status_code == 404
    assert not list((data_dir / "backups").glob("petrom-*.db"))


def test_unexpected_error_is_500_with_a_romanian_message(client, monkeypatch):
    from petrom_dashboard import firme

    def crash(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(firme, "add_company", crash)

    response = add_via_api(client)

    assert response.status_code == 500
    assert response.get_json()["mesaj"] == "Nu am putut salva (detalii în jurnal)."


def test_failure_reading_the_invoice_before_delete_is_500_and_makes_no_backup(
    app, client, data_dir, monkeypatch
):
    from petrom_dashboard import firme

    firma_id = add_via_api(client).get_json()["id"]
    factura_id = add_invoice(app, firma_id)

    def crash(*args, **kwargs):
        raise RuntimeError("database locked")

    monkeypatch.setattr(firme, "get_invoice", crash)

    response = client.post(f"/facturi/{factura_id}/sterge")

    assert response.status_code == 500
    assert response.get_json()["mesaj"] == "Nu am putut salva (detalii în jurnal)."
    assert not list((data_dir / "backups").glob("petrom-*.db"))


def test_delete_backup_goes_in_its_own_group(app, client, data_dir):
    firma_id = add_via_api(client).get_json()["id"]
    factura_id = add_invoice(app, firma_id)

    client.post(f"/facturi/{factura_id}/sterge")

    assert len(list((data_dir / "backups").glob("petrom-stergere-*.db"))) == 1


def test_restore_with_a_typed_max_answers_the_new_max(client):
    firma_id = add_via_api(client).get_json()["id"]
    client.post(f"/firme/{firma_id}/arhiveaza")

    response = client.post(f"/firme/{firma_id}/restaureaza", json={"max": "5.000"})

    assert response.get_json() == {"ok": True, "max_text": "5.000,00 lei"}
    assert client.get("/date").get_json()["firme"][0]["max_bani"] == 5000_00


def test_refused_input_is_written_to_the_log(client, caplog):
    with caplog.at_level("INFO"):
        add_via_api(client, cui="46133445")
        client.post("/firme", data="x", content_type="text/plain")

    log = caplog.text
    assert "CUI invalid" in log
    assert "not a JSON object" in log


def test_archived_company_moves_to_the_setari_page_and_back(client):
    # M7: the archived list moved from under the table to Setări.
    firma_id = add_via_api(client).get_json()["id"]
    add_via_api(client, cui="1590082", nume="BETA SRL")
    assert "Firme arhivate (0)" in client.get("/setari").get_data(as_text=True)

    client.post(f"/firme/{firma_id}/arhiveaza")

    html = client.get("/setari").get_data(as_text=True)
    assert "Firme arhivate (1)" in html and "ALFA SRL" in html

    client.post(f"/firme/{firma_id}/restaureaza")

    assert "Firme arhivate (0)" in client.get("/setari").get_data(as_text=True)
