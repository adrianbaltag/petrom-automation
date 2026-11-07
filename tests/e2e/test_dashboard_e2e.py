"""End to end in a real browser (Playwright): the dashboard page with fake companies.

The app runs on a real local web server with a temporary data folder, and Chromium opens it.
"""

import json
import re
from datetime import date, datetime, time, timedelta

import pytest
from db_helpers import open_db
from fake_invoice import make_invoice_pdf
from playwright.sync_api import expect

from petrom_dashboard.dashboard import current_month, month_label

MONTH = current_month()
MAX = 1000_00


def add_company(conn, cui, nume, total_bani=0, max_bani=MAX):
    firma_id = conn.execute("INSERT INTO firme (cui, nume) VALUES (?, ?)", (cui, nume)).lastrowid
    if max_bani is not None:
        conn.execute("INSERT INTO limite VALUES (?, ?, ?)", (firma_id, MONTH, max_bani))
    if total_bani:
        conn.execute(
            "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta, numar)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (firma_id, f"{MONTH}-01", total_bani, f"{cui}.pdf", f"amp{cui}", f"nr{cui}"),
        )


@pytest.fixture()
def four_companies(server_app):
    with open_db(server_app.config["DATABASE"]) as conn:
        add_company(conn, "1001", "GAMA SRL", total_bani=100_00)  # 10%: white
        add_company(conn, "1002", "BETA SRL", total_bani=620_00)  # 62%: orange
        add_company(conn, "1003", "ALFA SRL", total_bani=1200_00)  # 120%: over
        add_company(conn, "1004", "DELTA SRL", total_bani=50_00, max_bani=None)  # unset


def names(page):
    return page.locator("#tabel tbody tr .nume-text").all_inner_texts()


def test_rows_are_sorted_by_percent_with_colour_and_label(page, live_url, four_companies):
    page.goto(live_url)

    expect(page.locator("#tabel tbody tr")).to_have_count(4)
    assert names(page) == ["ALFA SRL", "BETA SRL", "GAMA SRL", "DELTA SRL"]
    over = page.locator("#tabel tbody tr").nth(0)
    expect(over).to_have_attribute("data-stare", "peste")
    expect(over).to_contain_text("1.200,00 lei")
    expect(over).to_contain_text("120%")
    expect(over).to_contain_text("PESTE LIMITĂ")
    expect(page.locator("#tabel tbody tr").nth(1)).to_have_attribute("data-stare", "atentie")
    unset = page.locator("#tabel tbody tr").nth(3)
    expect(unset).to_have_attribute("data-stare", "nesetat")
    expect(unset).to_contain_text("Max nesetat")
    # Colour is real: the over-limit row and the white row are painted differently.
    paint = "el => getComputedStyle(el).backgroundColor"
    assert over.evaluate(paint) != page.locator("#tabel tbody tr").nth(2).evaluate(paint)
    expect(page.locator("#luna")).to_have_text(month_label(MONTH))


def test_header_click_resorts_and_unset_stays_last(page, live_url, four_companies):
    page.goto(live_url)
    expect(page.locator("#tabel tbody tr")).to_have_count(4)

    page.get_by_role("button", name="Firmă", exact=True).click()
    assert names(page) == ["ALFA SRL", "BETA SRL", "DELTA SRL", "GAMA SRL"]

    page.get_by_role("button", name="% din max").click()
    page.get_by_role("button", name="% din max").click()  # second click: lowest % first
    assert names(page) == ["GAMA SRL", "BETA SRL", "ALFA SRL", "DELTA SRL"]


def test_search_by_name_or_cui(page, live_url, four_companies):
    page.goto(live_url)
    search = page.get_by_placeholder("Caută firmă sau CUI")

    search.fill("beta")
    expect(page.locator("#tabel tbody tr")).to_have_count(1)
    assert names(page) == ["BETA SRL"]

    search.fill("1004")
    assert names(page) == ["DELTA SRL"]

    search.fill("nu exista")
    expect(page.locator("#tabel tbody tr")).to_have_count(0)
    expect(page.locator("#gol")).to_have_text("Nicio firmă găsită.")


FIT_JS = """() => {
  const box = document.getElementById("tabel-loc");
  const inner = box.getBoundingClientRect().top + box.clientTop + box.clientHeight;
  const rows = document.querySelectorAll("#tabel tbody tr");
  const last = rows[rows.length - 1].getBoundingClientRect();
  return { spaceBottom: inner, lastBottom: last.bottom, rowHeight: last.height };
}"""


def assert_rows_fill_the_table(page):
    """The last row is fully inside the table area, and one more row would not fit."""
    fit = page.evaluate(FIT_JS)
    assert fit["lastBottom"] <= fit["spaceBottom"] + 0.5, fit  # nothing hidden below
    assert fit["spaceBottom"] - fit["lastBottom"] < fit["rowHeight"], fit  # no wasted row


def add_many_companies(server_app, count):
    with open_db(server_app.config["DATABASE"]) as conn:
        for i in range(count):
            add_company(conn, f"{2000 + i}", f"FIRMA {i:02d} SRL", total_bani=i * 10_00)


def test_rows_per_page_fit_the_window(page, live_url, server_app):
    add_many_companies(server_app, 40)
    page.set_viewport_size({"width": 1280, "height": 600})
    page.goto(live_url)

    rows = page.locator("#tabel tbody tr")
    expect(page.locator("#paginare-info")).to_contain_text("40 firme")
    shown = rows.count()
    assert 1 < shown < 40
    pages = -(-40 // shown)  # rounded up
    expect(page.locator("#paginare-info")).to_have_text(f"Pagina 1 din {pages} · 40 firme")
    assert_rows_fill_the_table(page)

    page.get_by_role("button", name="Pagina următoare").click()
    expect(page.locator("#paginare-info")).to_have_text(f"Pagina 2 din {pages} · 40 firme")

    page.set_viewport_size({"width": 1280, "height": 1400})
    expect(page.locator("#paginare-info")).not_to_have_text(re.compile(rf"din {pages} "))
    page.get_by_role("button", name="Pagina 1", exact=True).click()
    assert rows.count() > shown  # a taller window fits more rows on a full page
    assert_rows_fill_the_table(page)


def test_long_pager_is_shortened_with_dots(page, live_url, server_app):
    add_many_companies(server_app, 80)
    page.set_viewport_size({"width": 1280, "height": 420})
    page.goto(live_url)
    expect(page.locator("#paginare-info")).to_contain_text("80 firme")
    pages = int(re.search(r"din (\d+)", page.locator("#paginare-info").inner_text())[1])
    assert pages > 9

    numbers = page.locator("#numere-pagini")
    assert numbers.locator("> *").all_inner_texts() == ["1", "2", "…", str(pages)]

    page.get_by_role("button", name=f"Pagina {pages}", exact=True).click()
    assert numbers.locator("> *").all_inner_texts() == ["1", "…", str(pages - 1), str(pages)]

    page.get_by_role("button", name=f"Pagina {pages - 1}", exact=True).click()
    page.get_by_role("button", name=f"Pagina {pages - 2}", exact=True).click()
    page.get_by_role("button", name=f"Pagina {pages - 3}", exact=True).click()
    page.get_by_role("button", name=f"Pagina {pages - 4}", exact=True).click()
    current = pages - 4
    assert numbers.locator("> *").all_inner_texts() == [
        "1", "…", str(current - 1), str(current), str(current + 1), "…", str(pages)
    ]  # fmt: skip


def test_table_switches_month_when_left_open_past_midnight(page, live_url):
    year, month = map(int, MONTH.split("-"))
    first_of_next = date(year + month // 12, month % 12 + 1, 1)
    next_month = f"{first_of_next.year:04d}-{first_of_next.month:02d}"
    data_calls = []
    page.on("request", lambda req: data_calls.append(req) if req.url.endswith("/date") else None)
    midnight = datetime.combine(first_of_next, time())
    # The fake clock keeps ticking in real time, so start well before midnight and freeze
    # it at a fixed moment once the page is loaded: a slow load can't pass midnight early.
    page.clock.install(time=midnight - timedelta(seconds=60))
    page.goto(live_url)
    expect(page.locator("#luna")).to_have_text(month_label(MONTH))
    page.clock.pause_at(midnight - timedelta(seconds=4))

    page.clock.run_for(3000)  # still before midnight: the page must not reload
    page.wait_for_timeout(300)
    assert len(data_calls) == 1

    # The server's clock isn't faked, so answer /date as the server would after midnight.
    body = json.dumps(
        {
            "ok": True,
            "tip": "luna",
            "luna": next_month,
            "titlu": month_label(next_month),
            "luni": [{"luna": next_month, "text": month_label(next_month)}],
            "firme": [],
        }
    )
    page.route(
        "**/date",
        lambda route: route.fulfill(status=200, content_type="application/json", body=body),
    )
    page.clock.run_for(3000)  # passes midnight into the next month
    expect(page.locator("#luna")).to_have_text(month_label(next_month))

    page.clock.run_for(5000)  # once switched, no more reloads
    page.wait_for_timeout(300)
    assert len(data_calls) == 2


def test_clock_shows_romanian_day_date_and_time(page, live_url):
    page.goto(live_url)

    day = "(Luni|Marți|Miercuri|Joi|Vineri|Sâmbătă|Duminică)"
    expect(page.locator("#ceas")).to_have_text(
        re.compile(rf"^{day}, \d\d\.\d\d\.\d{{4}} · \d\d:\d\d:\d\d$")
    )
    expect(page.locator("#ceas")).to_contain_text(date.today().strftime("%d.%m.%Y"))


def test_later_milestone_buttons_are_hidden(page, live_url):
    page.goto(live_url)

    expect(page.get_by_role("button", name="Ecran complet")).to_be_visible()
    expect(page.get_by_role("button", name="Adaugă firmă")).to_be_visible()  # arrived in M5
    expect(page.get_by_role("link", name="Setări")).to_be_visible()  # arrived in M7


def test_run_button_greys_out_shows_summary_and_reloads_table(page, live_url, server_app, tmp_path):
    desktop = tmp_path / "Desktop"
    with open_db(server_app.config["DATABASE"]) as conn:
        for key in ("noi", "procesate", "erori"):
            conn.execute("INSERT INTO setari VALUES (?, ?)", (f"folder_{key}", str(desktop / key)))
    (desktop / "noi").mkdir(parents=True)
    year, month = MONTH.split("-")
    make_invoice_pdf(
        desktop / "noi" / "alfa.pdf",
        cui="22222226",
        nume="ALFA NOUA SRL",
        numar="109000000000099",
        total="250,00",
        data=f"03.{month}.{year}",
    )
    (desktop / "noi" / "stricat.pdf").write_bytes(b"not a pdf")

    held = []
    page.route("**/ruleaza", lambda route: held.append(route))
    page.goto(live_url)
    expect(page.locator("#gol")).to_have_text("Nicio firmă încă.")

    button = page.get_by_role("button", name="Rulează automatizarea")
    button.click()
    expect(button).to_be_disabled()  # greyed out while the run is going
    for _ in range(100):  # wait up to 5 s for the request to reach the route
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the button did not call /ruleaza"
    held[0].continue_()

    expect(page.locator("#rezultat")).to_contain_text("2 PDF-uri: 1 adăugată, 1 eroare")
    expect(page.locator("#rezultat")).to_contain_text("stricat.pdf")
    expect(button).to_be_enabled()
    expect(page.locator("#tabel tbody tr")).to_have_count(1)
    assert names(page) == ["ALFA NOUA SRL"]
    expect(page.locator("#tabel tbody tr").nth(0)).to_contain_text("250,00 lei")


def test_run_button_shows_a_refusal_message(page, live_url):
    page.route(
        "**/ruleaza",
        lambda route: route.fulfill(
            status=409,
            content_type="application/json",
            body='{"ok": false, "mesaj": "Automatizarea rulează deja."}',
        ),
    )
    page.goto(live_url)

    page.get_by_role("button", name="Rulează automatizarea").click()

    expect(page.locator("#rezultat")).to_contain_text("Automatizarea rulează deja.")
    expect(page.locator("#rezultat")).to_have_attribute("data-tip", "eroare")
