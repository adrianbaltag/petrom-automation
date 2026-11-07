"""End to end in a real browser (Playwright): the M6 filters above the table."""

from datetime import date, datetime, time, timedelta

import pytest
from db_helpers import open_db
from playwright.sync_api import expect

from petrom_dashboard.dashboard import current_month, last_days, month_label, range_label

TODAY = date.today()
MONTH = current_month(TODAY)
# Two months back: far enough that "last 30 days" never reaches it.
_first = TODAY.replace(day=1)
OLD_MONTH = current_month((_first - timedelta(days=1)).replace(day=1) - timedelta(days=1))


@pytest.fixture()
def companies(server_app):
    """ALFA: 100 lei today, 20 lei 10 days ago, 400 lei in OLD_MONTH. BETA: 500 lei 3 days ago."""
    invoices = [
        (1, TODAY, 100_00),
        (1, TODAY - timedelta(days=10), 20_00),
        (1, date.fromisoformat(f"{OLD_MONTH}-15"), 400_00),
        (2, TODAY - timedelta(days=3), 500_00),
    ]
    with open_db(server_app.config["DATABASE"]) as conn:
        conn.execute("INSERT INTO firme (id, cui, nume) VALUES (1, '1001', 'ALFA SRL')")
        conn.execute("INSERT INTO firme (id, cui, nume) VALUES (2, '1002', 'BETA SRL')")
        conn.execute("INSERT INTO limite VALUES (1, ?, 50000)", (OLD_MONTH,))  # 500 lei then
        conn.execute("INSERT INTO limite VALUES (1, ?, 100000)", (MONTH,))  # 1.000 lei now
        for n, (firma_id, day, bani) in enumerate(invoices, start=1):
            conn.execute(
                "INSERT INTO facturi (firma_id, data_factura, total_bani, fisier, amprenta,"
                " numar) VALUES (?, ?, ?, ?, ?, ?)",
                (firma_id, day.isoformat(), bani, f"f{n}.pdf", f"a{n}", f"n{n}"),
            )


def names(page):
    return page.locator("#tabel tbody tr .nume-text").all_inner_texts()


def row(page, name):
    return page.locator("#tabel tbody tr", has_text=name)


def test_last_7_days_hides_limits_and_sorts_by_amount(page, live_url, companies):
    page.goto(live_url)
    expect(page.locator("#tabel tbody tr")).to_have_count(2)

    page.get_by_role("button", name="Ultimele 7 zile").click()

    expect(page.locator("#luna")).to_have_text(range_label(*last_days(7, TODAY)))
    expect(page.get_by_role("button", name="Ultimele 7 zile")).to_have_attribute(
        "aria-pressed", "true"
    )
    assert names(page) == ["BETA SRL", "ALFA SRL"]  # biggest amount first
    expect(row(page, "ALFA SRL")).to_contain_text("100,00 lei")
    expect(page.locator("#titlu-suma")).to_have_text("Suma perioadei")
    expect(page.get_by_role("button", name="% din max")).to_be_hidden()
    expect(page.get_by_role("columnheader", name="Stare")).to_be_hidden()
    expect(page.get_by_text("Culorile și limitele apar doar")).to_be_visible()

    page.get_by_role("button", name="Luna curentă").click()

    expect(page.locator("#luna")).to_have_text(month_label(MONTH))
    expect(page.get_by_role("button", name="% din max")).to_be_visible()
    expect(page.get_by_text("Culorile și limitele apar doar")).to_be_hidden()


def test_last_30_days_includes_older_invoices(page, live_url, companies):
    page.goto(live_url)

    page.get_by_role("button", name="Ultimele 30 de zile").click()

    expect(page.locator("#luna")).to_have_text(range_label(*last_days(30, TODAY)))
    expect(row(page, "ALFA SRL")).to_contain_text("120,00 lei")  # not the 400 lei, too old


def test_pick_a_past_month_from_the_list(page, live_url, companies):
    page.goto(live_url)
    expect(page.locator("#tabel tbody tr")).to_have_count(2)

    page.get_by_label("Luna", exact=True).select_option(label=month_label(OLD_MONTH))

    expect(page.locator("#luna")).to_have_text(month_label(OLD_MONTH))
    alfa = row(page, "ALFA SRL")
    expect(alfa).to_contain_text("400,00 lei")
    expect(alfa).to_contain_text("80%")  # against that month's max of 500 lei
    expect(alfa).to_have_attribute("data-stare", "critic")
    expect(page.get_by_role("button", name="Luna curentă")).to_have_attribute(
        "aria-pressed", "false"
    )
    # The edit window starts from THIS month's max: a new max is saved from this month on.
    page.get_by_role("button", name="Editează ALFA SRL").click()
    dialog = page.get_by_role("dialog", name="Editează firma")
    expect(dialog.get_by_label("Max lunar (lei)")).to_have_value("1.000,00")


def test_calendar_wrong_order_is_explained_then_a_good_range_works(page, live_url, companies):
    page.goto(live_url)
    expect(page.locator("#luna")).to_have_text(month_label(MONTH))

    page.get_by_label("De la").fill(TODAY.isoformat())
    page.get_by_label("Până la").fill((TODAY - timedelta(days=5)).isoformat())
    page.get_by_role("button", name="Aplică").click()

    expect(page.get_by_role("alert").filter(has_text="înainte")).to_be_visible()
    expect(page.locator("#luna")).to_have_text(month_label(MONTH))  # table unchanged

    start = TODAY - timedelta(days=10)
    page.get_by_label("De la").fill(start.isoformat())
    page.get_by_label("Până la").fill(TODAY.isoformat())
    page.get_by_role("button", name="Aplică").click()

    expect(page.locator("#luna")).to_have_text(range_label(start, TODAY))
    expect(row(page, "ALFA SRL")).to_contain_text("120,00 lei")
    expect(row(page, "BETA SRL")).to_contain_text("500,00 lei")
    expect(page.locator("#filtru-eroare")).to_be_hidden()


def test_filter_is_kept_after_editing_a_company(page, live_url, companies):
    page.goto(live_url)
    page.get_by_role("button", name="Ultimele 7 zile").click()
    expect(page.locator("#titlu-suma")).to_have_text("Suma perioadei")

    page.get_by_role("button", name="Editează ALFA SRL").click()
    dialog = page.get_by_role("dialog", name="Editează firma")
    dialog.get_by_label("Nume firmă").fill("ALFA NOU SRL")
    dialog.get_by_role("button", name="Salvează").click()

    expect(row(page, "ALFA NOU SRL")).to_contain_text("100,00 lei")
    expect(page.locator("#luna")).to_have_text(range_label(*last_days(7, TODAY)))
    expect(page.locator("#titlu-suma")).to_have_text("Suma perioadei")


def test_last_7_days_reloads_after_midnight(page, live_url, companies):
    calls = []
    page.on("request", lambda req: calls.append(req.url) if "zile=7" in req.url else None)
    midnight = datetime.combine(TODAY + timedelta(days=1), time())
    # Same trick as the month-switch test: start early, freeze just before midnight.
    page.clock.install(time=midnight - timedelta(seconds=60))
    page.goto(live_url)
    page.get_by_role("button", name="Ultimele 7 zile").click()
    expect(page.locator("#titlu-suma")).to_have_text("Suma perioadei")
    page.clock.pause_at(midnight - timedelta(seconds=4))

    page.clock.run_for(3000)  # still before midnight: no reload
    page.wait_for_timeout(300)
    assert len(calls) == 1

    page.clock.run_for(3000)  # passes midnight: the 7 days move one day forward
    page.wait_for_timeout(500)
    assert len(calls) == 2


def test_refused_range_keeps_the_page_she_was_on(page, live_url, server_app):
    with open_db(server_app.config["DATABASE"]) as conn:
        for i in range(40):
            conn.execute(
                "INSERT INTO firme (cui, nume) VALUES (?, ?)", (f"{2000 + i}", f"F{i:02d}")
            )
    page.set_viewport_size({"width": 1280, "height": 600})
    page.goto(live_url)
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 1 din")
    page.get_by_role("button", name="Pagina următoare").click()
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 2 din")

    page.get_by_label("De la").fill(TODAY.isoformat())
    page.get_by_label("Până la").fill((TODAY - timedelta(days=5)).isoformat())
    page.get_by_role("button", name="Aplică").click()
    expect(page.get_by_role("alert").filter(has_text="înainte")).to_be_visible()

    # Refused: still on page 2, so the next page is 3.
    page.get_by_role("button", name="Pagina următoare").click()
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 3 din")

    # An accepted filter starts again on page 1, also between two ranges (7 -> 30 days).
    page.get_by_role("button", name="Ultimele 7 zile").click()
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 1 din")
    page.get_by_role("button", name="Pagina următoare").click()
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 2 din")
    page.get_by_role("button", name="Ultimele 30 de zile").click()
    expect(page.locator("#paginare-info")).to_contain_text("Pagina 1 din")


@pytest.mark.parametrize("picked", ["luna", "calendar"])
def test_a_picked_month_or_range_stays_past_midnight_into_a_new_month(
    page, live_url, companies, picked
):
    start = TODAY - timedelta(days=5)
    if picked == "luna":
        sent, title = f"luna={OLD_MONTH}", month_label(OLD_MONTH)
    else:
        sent, title = f"de={start.isoformat()}&pana={TODAY.isoformat()}", range_label(start, TODAY)
    calls = []
    page.on("request", lambda req: calls.append(req.url) if "/date" in req.url else None)
    next_month = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    midnight = datetime.combine(next_month, time())
    page.clock.install(time=midnight - timedelta(seconds=60))
    page.goto(live_url)
    expect(page.locator("#tabel tbody tr")).to_have_count(2)
    if picked == "luna":
        page.get_by_label("Luna", exact=True).select_option(label=title)
    else:
        page.get_by_label("De la").fill(start.isoformat())
        page.get_by_label("Până la").fill(TODAY.isoformat())
        page.get_by_role("button", name="Aplică").click()
    expect(page.locator("#luna")).to_have_text(title)
    page.clock.pause_at(midnight - timedelta(seconds=4))
    assert len(calls) == 2  # the first load, then the picked filter

    page.clock.run_for(6000)  # passes midnight into a new month
    page.wait_for_timeout(500)

    # Reloaded once (so the month list gains the new month), with the same filter.
    assert len(calls) == 3
    assert calls[-1].endswith(f"/date?{sent}")
    expect(page.locator("#luna")).to_have_text(title)


def test_filter_is_kept_after_a_run(page, live_url, companies):
    summary = '{"ok": true, "mesaj": "Gata: 0 facturi noi.", "erori": [], "note": []}'
    page.route(
        "**/ruleaza",
        lambda route: route.fulfill(status=200, content_type="application/json", body=summary),
    )
    calls = []
    page.on("request", lambda req: calls.append(req.url) if "/date" in req.url else None)
    page.goto(live_url)
    page.get_by_role("button", name="Ultimele 30 de zile").click()
    expect(page.locator("#luna")).to_have_text(range_label(*last_days(30, TODAY)))

    assert len(calls) == 2  # the first load, then 30 days

    # Wait for the table's reload after the run: no reload at all fails here.
    with page.expect_response(lambda r: "/date" in r.url) as reload:
        page.get_by_role("button", name="Rulează automatizarea").click()
    expect(page.get_by_text("Gata: 0 facturi noi.")).to_be_visible()

    assert reload.value.url.endswith("/date?zile=30")  # the same filter, not this month
    assert len(calls) == 3
    expect(page.get_by_role("button", name="Ultimele 30 de zile")).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.locator("#luna")).to_have_text(range_label(*last_days(30, TODAY)))


def test_a_late_answer_from_an_earlier_click_is_ignored(page, live_url, companies):
    # On a slow laptop the answer to an earlier click can arrive after a later one.
    held = []
    page.route("**/date?zile=30", lambda route: held.append(route))
    page.goto(live_url)
    expect(page.locator("#luna")).to_have_text(month_label(MONTH))

    page.get_by_role("button", name="Ultimele 30 de zile").click()  # its answer is held back
    for _ in range(100):  # wait up to 5 s for the request to reach the route
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the 30-day button did not ask for data"
    page.get_by_role("button", name="Ultimele 7 zile").click()
    seven_days = range_label(*last_days(7, TODAY))
    expect(page.locator("#luna")).to_have_text(seven_days)

    with page.expect_response(lambda r: "zile=30" in r.url):
        held[0].continue_()  # the 30-day answer now arrives, last
    page.wait_for_timeout(300)  # time for the page to (wrongly) draw it

    expect(page.locator("#luna")).to_have_text(seven_days)
    expect(page.get_by_role("button", name="Ultimele 7 zile")).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(row(page, "ALFA SRL")).to_contain_text("100,00 lei")  # 7 days, not 120 lei
