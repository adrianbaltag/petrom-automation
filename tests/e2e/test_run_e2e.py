"""End to end: a fake Facturi-noi folder, the /ruleaza web address, then the database and folders.

Runs the real app, real PDF reading and real file moves, all inside a temporary folder.
"""

from db_helpers import open_db
from fake_invoice import make_invoice_pdf

from petrom_dashboard.automation import ALREADY_PROCESSED, LOCK_FILE_NAME, RunLock
from petrom_dashboard.pdf_reader import PDF_DAMAGED


def test_full_run_on_a_fake_folder(app, client, data_dir, tmp_path):
    desktop = tmp_path / "Desktop"
    with open_db(app.config["DATABASE"]) as conn:
        for key in ("noi", "procesate", "erori"):
            conn.execute("INSERT INTO setari VALUES (?, ?)", (f"folder_{key}", str(desktop / key)))
    noi = desktop / "noi"
    noi.mkdir(parents=True)

    make_invoice_pdf(
        noi / "alfa_iunie.pdf",
        cui="22222226",
        nume="ALFA SRL",
        numar="109000000000011",
        total="1.234,56",
        data="05.06.2026",
    )
    make_invoice_pdf(
        noi / "alfa_iulie.pdf",
        cui="22222226",
        nume="ALFA SRL",
        numar="109000000000012",
        total="100",
        data="02.07.2026",
    )
    make_invoice_pdf(
        noi / "beta.pdf",
        cui="33333339",
        nume="BETA SRL",
        numar="109000000000013",
        total="199.29",
        data="10.06.2026",
    )
    make_invoice_pdf(
        noi / "beta_dublura.pdf",
        cui="33333339",
        nume="BETA SRL",
        numar="109000000000013",
        total="1",
        data="10.06.2026",
    )
    (noi / "stricat.pdf").write_bytes(b"not a pdf at all")

    response = client.post("/ruleaza")

    assert response.status_code == 200
    body = response.get_json()
    assert body["mesaj"] == "5 PDF-uri: 3 adăugate, 2 erori"
    assert sorted(body["adaugate"]) == ["alfa_iulie.pdf", "alfa_iunie.pdf", "beta.pdf"]
    assert sorted((e["fisier"], e["motiv"]) for e in body["erori"]) == [
        ("beta_dublura.pdf", ALREADY_PROCESSED),
        ("stricat.pdf", PDF_DAMAGED),
    ]

    # Folders: Facturi-noi empty, good ones by month, bad ones in errors with reasons.
    assert list(noi.iterdir()) == []
    assert (desktop / "procesate" / "2026-06" / "alfa_iunie.pdf").exists()
    assert (desktop / "procesate" / "2026-06" / "beta.pdf").exists()
    assert (desktop / "procesate" / "2026-07" / "alfa_iulie.pdf").exists()
    motive = (desktop / "erori" / "motive.txt").read_text(encoding="utf-8-sig")
    assert "beta_dublura.pdf" in motive and "stricat.pdf" in motive

    # Database: two companies created, three invoices in whole bani, all marked moved.
    with open_db(app.config["DATABASE"]) as conn:
        firme = conn.execute("SELECT cui, nume FROM firme ORDER BY cui").fetchall()
        facturi = conn.execute(
            "SELECT f.numar, f.total_bani, f.mutat, c.cui FROM facturi f "
            "JOIN firme c ON c.id = f.firma_id ORDER BY f.numar"
        ).fetchall()
    assert [tuple(r) for r in firme] == [("22222226", "ALFA SRL"), ("33333339", "BETA SRL")]
    assert [tuple(r) for r in facturi] == [
        ("109000000000011", 123456, 1, "22222226"),
        ("109000000000012", 10000, 1, "22222226"),
        ("109000000000013", 19929, 1, "33333339"),
    ]

    # A backup was made before the run.
    assert len(list((data_dir / "backups").glob("petrom-*.db"))) == 1

    # A second click while a run is going is refused.
    with RunLock(data_dir / LOCK_FILE_NAME):
        busy = client.post("/ruleaza")
    assert busy.status_code == 409
