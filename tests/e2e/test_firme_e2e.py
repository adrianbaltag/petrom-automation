"""End to end in a real browser (Playwright): add, edit, archive, restore, delete invoice."""

import re

from db_helpers import open_db
from playwright.sync_api import expect

from petrom_dashboard.dashboard import current_month

MONTH = current_month()


def add_company(server_app, cui, nume, max_bani=None, invoices=()):
    with open_db(server_app.config["DATABASE"]) as conn:
        firma_id = conn.execute(
            "INSERT INTO firme (cui, nume) VALUES (?, ?)", (cui, nume)
        ).lastrowid
        if max_bani is not None:
            conn.execute("INSERT INTO limite VALUES (?, ?, ?)", (firma_id, MONTH, max_bani))
        for numar, total_bani in invoices:
            conn.execute(
                "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (firma_id, f"{MONTH}-03", total_bani, f"{numar}.pdf", f"amp-{numar}", numar),
            )
    return firma_id


def row(page, nume):
    return page.locator("#tabel tbody tr").filter(has_text=nume)


def test_add_a_company_and_see_it_in_the_table(page, live_url):
    page.goto(live_url)
    expect(page.locator("#gol")).to_have_text("Nicio firmă încă.")

    page.get_by_role("button", name="Adaugă firmă").click()
    dialog = page.get_by_role("dialog", name="Adaugă firmă")
    dialog.get_by_label("CUI").fill("RO 46133455")
    dialog.get_by_label("Nume firmă").fill("ALFA SRL")
    dialog.get_by_label("Max lunar (lei, opțional)").fill("5.000")
    dialog.get_by_role("button", name="Salvează").click()

    expect(dialog).to_be_hidden()
    expect(page.locator("#rezultat")).to_contain_text("Firma ALFA SRL a fost adăugată.")
    expect(page.locator("#rezultat")).to_have_css("background-color", "rgb(220, 240, 221)")  # green
    alfa = row(page, "ALFA SRL")
    expect(alfa).to_contain_text("46133455")
    expect(alfa).to_contain_text("5.000,00 lei")
    expect(alfa).to_contain_text("0%")


def test_a_wrong_cui_is_explained_and_nothing_is_added(page, live_url):
    page.goto(live_url)
    page.get_by_role("button", name="Adaugă firmă").click()
    dialog = page.get_by_role("dialog", name="Adaugă firmă")
    dialog.get_by_label("CUI").fill("46133445")
    dialog.get_by_label("Nume firmă").fill("ALFA SRL")
    dialog.get_by_role("button", name="Salvează").click()

    expect(dialog.get_by_role("alert")).to_have_text("CUI invalid, verifică cifrele.")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Anulează").click()
    expect(page.locator("#tabel tbody tr")).to_have_count(0)


def test_edit_name_and_max(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", max_bani=5000_00, invoices=[("FP1", 3000_00)])
    page.goto(live_url)
    expect(row(page, "ALFA SRL")).to_contain_text("Peste 50%")

    page.get_by_role("button", name="Editează ALFA SRL").click()
    dialog = page.get_by_role("dialog", name="Editează firma")
    expect(dialog.get_by_label("Max lunar (lei)")).to_have_value("5.000,00")
    dialog.get_by_label("Nume firmă").fill("ALFA NOU SRL")
    dialog.get_by_label("Max lunar (lei)").fill("10.000")
    dialog.get_by_role("button", name="Salvează").click()

    expect(dialog).to_be_hidden()
    alfa = row(page, "ALFA NOU SRL")
    expect(alfa).to_contain_text("10.000,00 lei")
    expect(alfa).to_contain_text("30%")
    expect(alfa).to_have_attribute("data-stare", "ok")


def test_emptying_the_max_is_refused(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", max_bani=5000_00)
    page.goto(live_url)

    page.get_by_role("button", name="Editează ALFA SRL").click()
    dialog = page.get_by_role("dialog", name="Editează firma")
    dialog.get_by_label("Max lunar (lei)").fill("")
    dialog.get_by_role("button", name="Salvează").click()

    expect(dialog.get_by_role("alert")).to_have_text("Max-ul nu poate fi șters, doar schimbat.")


def test_archive_then_restore_from_the_link_under_the_table(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", max_bani=5000_00)
    add_company(server_app, "1590082", "BETA SRL")
    page.goto(live_url)
    expect(page.get_by_role("button", name=re.compile("Firme arhivate"))).to_be_hidden()

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Arhivează firma").click()
    confirm = page.get_by_role("dialog", name="Arhivezi firma?")
    expect(confirm).to_contain_text("Revine automat dacă vine o factură nouă")
    confirm.get_by_role("button", name="Da, arhivează").click()

    expect(page.locator("#tabel tbody tr")).to_have_count(1)
    expect(page.locator("#rezultat")).to_contain_text("ALFA SRL a fost arhivată")
    link = page.get_by_role("button", name="Firme arhivate (1)")
    link.click()
    archived = page.get_by_role("dialog", name="Firme arhivate")
    archived.get_by_role("button", name="Restaurează ALFA SRL").click()

    expect(archived).to_be_hidden()  # last one restored: the window closes
    expect(row(page, "ALFA SRL")).to_contain_text("5.000,00 lei")  # old max kept
    expect(link).to_be_hidden()


def test_cancel_on_archive_keeps_the_company(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL")
    page.goto(live_url)

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Arhivează firma").click()
    page.get_by_role("dialog", name="Arhivezi firma?").get_by_role(
        "button", name="Anulează"
    ).click()

    expect(page.get_by_role("dialog", name="Editează firma")).to_be_visible()
    page.keyboard.press("Escape")
    expect(row(page, "ALFA SRL")).to_have_count(1)


def test_adding_an_archived_cui_offers_restore(page, live_url, server_app):
    firma_id = add_company(server_app, "46133455", "ALFA SRL")
    with open_db(server_app.config["DATABASE"]) as conn:
        conn.execute("UPDATE firme SET arhivat = 1 WHERE id = ?", (firma_id,))
    page.goto(live_url)

    page.get_by_role("button", name="Adaugă firmă").click()
    dialog = page.get_by_role("dialog", name="Adaugă firmă")
    dialog.get_by_label("CUI").fill("46133455")
    dialog.get_by_label("Nume firmă").fill("ALTA SRL")
    dialog.get_by_label("Max lunar (lei, opțional)").fill("5.000")
    dialog.get_by_role("button", name="Salvează").click()
    expect(dialog.get_by_role("alert")).to_contain_text("Firma ALFA SRL e arhivată")
    dialog.get_by_role("button", name="Restaurează").click()

    expect(dialog).to_be_hidden()
    expect(row(page, "ALFA SRL")).to_contain_text("5.000,00 lei")  # typed max used
    expect(row(page, "ALTA SRL")).to_have_count(0)  # old name kept
    expect(page.locator("#rezultat")).to_contain_text("Max-ul nou: 5.000,00 lei")


def test_delete_an_invoice_after_confirming(page, live_url, server_app, data_dir):
    add_company(
        server_app, "46133455", "ALFA SRL", max_bani=1000_00,
        invoices=[("FP1", 600_00), ("FP2", 100_00)],
    )  # fmt: skip
    page.goto(live_url)
    expect(row(page, "ALFA SRL")).to_contain_text("700,00 lei")

    page.get_by_role("button", name="Editează ALFA SRL").click()
    dialog = page.get_by_role("dialog", name="Editează firma")
    expect(dialog.locator("#facturi-lista li")).to_have_count(2)
    dialog.get_by_role("button", name="Șterge factura FP1").click()
    confirm = page.get_by_role("dialog", name="Ștergi factura?")
    expect(confirm).to_contain_text("FP1 (600,00 lei)")
    confirm.get_by_role("button", name="Da, șterge").click()

    expect(dialog.locator("#facturi-stare")).to_have_text("Factura FP1 a fost ștearsă.")
    expect(dialog.locator("#facturi-lista li")).to_have_count(1)
    expect(row(page, "ALFA SRL").locator("td").nth(2)).to_have_text("100,00 lei")
    assert len(list((data_dir / "backups").glob("petrom-*.db"))) == 1


def test_phone_width_shows_only_the_pencil(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL")
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(live_url)

    button = page.get_by_role("button", name="Editează ALFA SRL")
    expect(button).to_be_visible()
    expect(button.locator(".editeaza-text")).to_be_hidden()
    no_page_scroll = "() => document.documentElement.scrollWidth <= window.innerWidth"
    assert page.evaluate(no_page_scroll)


def focused_label(page):
    return page.evaluate(
        "() => document.activeElement.getAttribute('aria-label') || document.activeElement.id"
    )


def test_keyboard_focus_comes_back_after_save_and_delete(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", max_bani=1000_00, invoices=[("FP1", 100_00)])
    page.goto(live_url)

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Șterge factura FP1").click()
    page.get_by_role("dialog", name="Ștergi factura?").get_by_role(
        "button", name="Da, șterge"
    ).click()
    expect(page.locator("#facturi-stare")).to_have_text("Factura FP1 a fost ștearsă.")
    assert focused_label(page) == "facturi-titlu"

    dialog = page.get_by_role("dialog", name="Editează firma")
    dialog.get_by_role("button", name="Salvează").click()
    expect(dialog).to_be_hidden()
    expect(page.locator("#rezultat")).to_contain_text("au fost salvate")
    page.wait_for_timeout(800)  # the result box resizes the table, which redraws it
    assert focused_label(page) == "Editează ALFA SRL"


def test_closing_the_window_during_a_delete_still_updates_the_table(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", max_bani=1000_00, invoices=[("FP1", 600_00)])
    page.goto(live_url)
    expect(row(page, "ALFA SRL")).to_contain_text("600,00 lei")
    held = []
    page.route("**/facturi/*/sterge", lambda route: held.append(route))  # slow disk

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Șterge factura FP1").click()
    page.get_by_role("dialog", name="Ștergi factura?").get_by_role(
        "button", name="Da, șterge"
    ).click()
    for _ in range(50):  # wait until the delete request is being held
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the delete request never started"
    page.keyboard.press("Escape")  # she closes the window while the delete is running
    expect(page.get_by_role("dialog", name="Editează firma")).to_be_hidden()
    held[0].continue_()

    expect(row(page, "ALFA SRL").locator("td").nth(2)).to_have_text("0,00 lei")  # Suma lunii


def test_a_slow_delete_does_not_write_into_another_companys_window(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL", invoices=[("FP1", 600_00)])
    add_company(server_app, "1590082", "BETA SRL", invoices=[("FP9", 50_00)])
    page.goto(live_url)
    held = []
    page.route("**/facturi/*/sterge", lambda route: held.append(route))

    page.get_by_role("button", name="Editează ALFA SRL").click()
    page.get_by_role("button", name="Șterge factura FP1").click()
    page.get_by_role("dialog", name="Ștergi factura?").get_by_role(
        "button", name="Da, șterge"
    ).click()
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the delete request never started"
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Editează BETA SRL").click()
    expect(page.get_by_role("button", name="Șterge factura FP9")).to_be_visible()
    held[0].continue_()

    expect(row(page, "ALFA SRL").locator("td").nth(2)).to_have_text("0,00 lei")
    expect(page.locator("#facturi-stare")).to_have_text("")  # nothing about FP1 here
    expect(page.get_by_role("button", name="Șterge factura FP9")).to_be_visible()


def test_a_page_load_asks_the_server_once(page, live_url, server_app):
    add_company(server_app, "46133455", "ALFA SRL")
    asked = []
    page.on(
        "request", lambda req: asked.append(req.url) if "/firme/arhivate" in req.url else None
    )

    page.goto(live_url)
    expect(row(page, "ALFA SRL")).to_have_count(1)
    page.wait_for_timeout(300)

    assert asked == []  # the archived count comes with /date


def test_a_failed_archived_list_keeps_the_link(page, live_url, server_app):
    firma_id = add_company(server_app, "46133455", "ALFA SRL")
    with open_db(server_app.config["DATABASE"]) as conn:
        conn.execute("UPDATE firme SET arhivat = 1 WHERE id = ?", (firma_id,))
    page.goto(live_url)
    link = page.get_by_role("button", name="Firme arhivate (1)")
    expect(link).to_be_visible()
    page.route(
        "**/firme/arhivate",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"ok": false, "mesaj": "Nu am putut salva (detalii în jurnal)."}',
        ),
    )

    link.click()
    archived = page.get_by_role("dialog", name="Firme arhivate")
    expect(archived.get_by_role("alert")).to_contain_text("Nu am putut")
    archived.get_by_role("button", name="Închide").click()

    expect(link).to_be_visible()  # the archived company still exists
