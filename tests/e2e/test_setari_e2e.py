"""End to end in a real browser (Playwright): the Setări page (M7)."""

import pytest
from db_helpers import open_db
from playwright.sync_api import expect

from petrom_dashboard import automation, setari


@pytest.fixture(autouse=True)
def desktop(tmp_path, monkeypatch):
    """A fake Desktop: the test server runs in this process, so this reaches it too."""
    path = tmp_path / "Desktop"
    monkeypatch.setattr(automation, "desktop_dir", lambda: path)
    return path


@pytest.fixture()
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(setari, "open_in_file_manager", calls.append)
    return calls


def saved_rows(server_app):
    with open_db(server_app.config["DATABASE"]) as conn:
        return dict(conn.execute("SELECT cheie, valoare FROM setari").fetchall())


def result(page):
    return page.locator("#rezultat")


def test_setari_opens_from_the_dashboard_and_goes_back(page, live_url, desktop):
    page.goto(live_url)

    page.get_by_role("link", name="Setări").click()

    expect(page).to_have_url(f"{live_url}/setari")
    expect(page.get_by_role("heading", name="Setări", exact=True)).to_be_visible()
    expect(page.get_by_label("Facturi-noi", exact=True)).to_have_value(str(desktop / "Facturi-noi"))
    expect(page.get_by_text("Versiunea 0.7.0")).to_be_visible()
    page.get_by_role("link", name="← Înapoi la tabel").click()
    expect(page).to_have_url(f"{live_url}/")


def test_save_folders_creates_them_and_shows_the_clean_paths(page, live_url, server_app, tmp_path):
    page.goto(f"{live_url}/setari")

    page.get_by_label("Facturi-noi", exact=True).fill(
        f'"{tmp_path / "A"}"'
    )  # as "Copy as path" gives it
    page.get_by_label("Facturi-procesate", exact=True).fill(str(tmp_path / "B"))
    page.get_by_label("Facturi-erori", exact=True).fill(str(tmp_path / "E"))
    page.get_by_role("button", name="Salvează").click()

    expect(result(page)).to_contain_text("Folderele au fost salvate.")
    expect(result(page)).to_contain_text(f"Am creat folderul {tmp_path / 'A'}.")
    expect(result(page)).to_have_attribute("data-tip", "ok")
    expect(page.get_by_label("Facturi-noi", exact=True)).to_have_value(str(tmp_path / "A"))
    assert (tmp_path / "E").is_dir()
    assert saved_rows(server_app)["folder_noi"] == str(tmp_path / "A")


def test_check_marks_each_box_and_saves_nothing(page, live_url, server_app, tmp_path):
    page.goto(f"{live_url}/setari")
    page.get_by_label("Facturi-noi", exact=True).fill(str(tmp_path / "A"))
    page.get_by_label("Facturi-procesate", exact=True).fill(
        str(tmp_path / "A")
    )  # same as Facturi-noi
    page.get_by_label("Facturi-erori", exact=True).fill(str(tmp_path / "E"))

    page.get_by_role("button", name="Verifică").click()

    expect(page.locator("#folder-procesate-stare")).to_have_text("✗ Același folder ca Facturi-noi.")
    expect(page.locator("#folder-erori-stare")).to_have_text(
        "✓ Nu există încă: îl creez când apeși Salvează."
    )
    expect(page.get_by_label("Facturi-procesate", exact=True)).to_have_attribute(
        "aria-invalid", "true"
    )
    expect(result(page)).to_have_attribute("data-tip", "eroare")
    assert saved_rows(server_app) == {}
    assert not (tmp_path / "E").exists()

    page.get_by_label("Facturi-procesate", exact=True).fill(
        str(tmp_path / "B")
    )  # editing clears the ✗
    expect(page.locator("#folder-procesate-stare")).to_be_hidden()


def test_refused_save_puts_focus_on_the_bad_box(page, live_url, server_app, tmp_path):
    page.goto(f"{live_url}/setari")
    page.get_by_label("Facturi-erori", exact=True).fill("Facturi-erori")  # not a full path

    page.get_by_role("button", name="Salvează").click()

    expect(result(page)).to_contain_text("Nu am salvat nimic.")
    expect(page.locator("#folder-erori-stare")).to_contain_text("✗ Scrie calea completă")
    expect(page.get_by_label("Facturi-erori", exact=True)).to_be_focused()
    assert saved_rows(server_app) == {}


def test_pdfs_left_in_the_old_noi_give_an_orange_warning(page, live_url, desktop, tmp_path):
    (desktop / "Facturi-noi").mkdir(parents=True)
    (desktop / "Facturi-noi" / "f.pdf").write_bytes(b"%PDF")
    page.goto(f"{live_url}/setari")

    page.get_by_label("Facturi-noi", exact=True).fill(str(tmp_path / "A"))
    page.get_by_role("button", name="Salvează").click()

    expect(result(page)).to_have_attribute("data-tip", "atentie")
    expect(result(page)).to_contain_text("a rămas 1 PDF. Mută-l în folderul nou")
    assert (desktop / "Facturi-noi" / "f.pdf").exists()  # nothing was moved


def test_back_to_desktop_fills_the_desktop_paths(page, live_url, server_app, desktop, tmp_path):
    page.goto(f"{live_url}/setari")
    page.get_by_label("Facturi-noi", exact=True).fill(str(tmp_path / "A"))
    page.get_by_role("button", name="Salvează").click()
    expect(result(page)).to_contain_text("Folderele au fost salvate.")

    page.get_by_role("button", name="Revino la Desktop").click()

    expect(result(page)).to_contain_text("Folderele sunt din nou cele de pe Desktop.")
    expect(page.get_by_label("Facturi-noi", exact=True)).to_have_value(str(desktop / "Facturi-noi"))
    assert saved_rows(server_app) == {}


def test_backup_now_updates_the_summary_and_stays_in_view(page, live_url, data_dir):
    page.set_viewport_size({"width": 1024, "height": 500})  # short window: the page scrolls
    page.goto(f"{live_url}/setari")
    expect(page.locator("#backup-rezumat")).to_have_text("Încă nu există niciun backup.")

    page.get_by_role("button", name="Fă backup acum").click()

    expect(page.locator("#backup-rezumat")).to_contain_text("· 1 copie")
    expect(result(page)).to_contain_text("Backup făcut.")
    expect(result(page)).to_be_in_viewport()  # sticky: visible though Backup is lower down
    assert len(list((data_dir / "backups").glob("petrom-manual-*.db"))) == 1


def test_open_buttons_send_only_the_folder_name(page, live_url, desktop, data_dir, opened):
    page.goto(f"{live_url}/setari")
    sent = []
    page.on("request", lambda req: sent.append(req.url) if "/deschide/" in req.url else None)

    with page.expect_response("**/deschide/erori"):
        page.get_by_role("button", name="Deschide folderul salvat Facturi-erori").click()
    with page.expect_response("**/deschide/date"):
        page.get_by_role("button", name="Deschide folderul de date").click()

    assert opened == [desktop / "Facturi-erori", data_dir]
    assert [url.rsplit("/", 1)[1] for url in sent] == ["erori", "date"]


def test_open_failure_shows_a_red_message(page, live_url, monkeypatch):
    def broken(path):
        raise OSError("no file manager")

    monkeypatch.setattr(setari, "open_in_file_manager", broken)
    page.goto(f"{live_url}/setari")

    page.get_by_role("button", name="Deschide folderul de backup").click()

    expect(result(page)).to_contain_text("Nu am putut deschide folderul")
    expect(result(page)).to_have_attribute("data-tip", "eroare")


def test_phone_width_has_no_sideways_scroll(page, live_url):
    page.set_viewport_size({"width": 375, "height": 740})
    page.goto(f"{live_url}/setari")

    expect(page.get_by_role("button", name="Salvează")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# --- review round 1: the browser's own Back / Forward arrows ---------------------------


def add_company(server_app, cui, nume, arhivat=0):
    with open_db(server_app.config["DATABASE"]) as conn:
        return conn.execute(
            "INSERT INTO firme (cui, nume, arhivat) VALUES (?, ?, ?)", (cui, nume, arhivat)
        ).lastrowid


def test_browser_back_after_a_restore_shows_the_company(page, live_url, server_app):
    add_company(server_app, "1590082", "BETA SRL")
    add_company(server_app, "46133455", "ALFA SRL", arhivat=1)
    page.goto(live_url)
    expect(page.locator("#tabel tbody tr")).to_have_count(1)
    page.get_by_role("link", name="Setări").click()

    page.get_by_role("button", name="Restaurează ALFA SRL").click()
    expect(page.locator("#rezultat")).to_contain_text("a fost restaurată")
    page.go_back()

    expect(page.locator("#tabel tbody tr").filter(has_text="ALFA SRL")).to_have_count(1)


def test_browser_forward_to_setari_after_an_archive_shows_it(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL")
    page.goto(live_url)
    page.get_by_role("link", name="Setări").click()
    expect(page.get_by_role("heading", name="Firme arhivate (0)")).to_be_visible()
    page.go_back()

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Arhivează firma").click()
    page.get_by_role("dialog", name="Arhivezi firma?").get_by_role(
        "button", name="Da, arhivează"
    ).click()
    expect(page.locator("#rezultat")).to_contain_text("a fost arhivată")
    page.go_forward()

    expect(page.get_by_role("heading", name="Firme arhivate (1)")).to_be_visible()


FAKE_BFCACHE_RETURN = (
    "window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))"
)


def test_dashboard_back_from_the_browser_memory_reads_the_rows_again(page, live_url):
    # Edge/Chrome may keep the whole page in memory (back/forward cache); fake that return.
    page.goto(live_url)
    expect(page.locator("#gol")).to_be_visible()

    with page.expect_request("**/date"):
        page.evaluate(FAKE_BFCACHE_RETURN)


def test_setari_back_from_the_browser_memory_reloads_the_page(page, live_url):
    page.goto(f"{live_url}/setari")

    with page.expect_navigation():
        page.evaluate(FAKE_BFCACHE_RETURN)
