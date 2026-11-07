"""Tests for the PDF reader: text parsing first, then real PDF files built on the fly."""

import datetime

import pytest
from fake_invoice import (
    FAKE_BUYER_CUI,
    FAKE_SUPPLIER_CUI,
    build_pdf,
    find_unicode_font,
    sample_like_items,
)

from petrom_dashboard import pdf_reader
from petrom_dashboard.pdf_reader import Invoice, InvoiceError, parse_invoice_text, read_invoice

BUYER_TEXT = (
    "Cumpărător: TRANSPORT TEST S.R.L.\n"
    "Nr. Reg. Com./Anul:J2022000000000\n"
    "C.U.I./C.I.F.: RO 12345678\n"
)
FULL_TEXT = (
    "Aferentă facturii cu nr.: 109000000000001\n"
    "Data: 19.10.2026\n"
    "Data scadentă: 25.10.2026\n"
    "Semnătura și ștampila Total de plată: 1.234,56\n"
)


def reason_of(excinfo):
    return excinfo.value.motiv


# ---------- parse_invoice_text: the rules, on plain text ----------


def test_parse_reads_every_field():
    invoice = parse_invoice_text(BUYER_TEXT, FULL_TEXT)
    assert invoice == Invoice(
        cui="12345678",
        nume="TRANSPORT TEST S.R.L.",
        total_bani=123456,
        data=datetime.date(2026, 10, 19),
        numar="109000000000001",
    )


def test_parse_accepts_labels_without_diacritics():
    buyer = BUYER_TEXT.replace("Cumpărător", "Cumparator")
    full = FULL_TEXT.replace("plată", "plata").replace("Aferentă", "Aferenta")
    invoice = parse_invoice_text(buyer, full)
    assert invoice.cui == "12345678"
    assert invoice.total_bani == 123456


def test_parse_accepts_cedilla_letters():
    # Some tools write ş with a cedilla instead of ș with a comma, or ă as two
    # pieces (a + a separate breve mark).
    buyer = BUYER_TEXT.replace("ă", "ă")
    full = FULL_TEXT.replace("ș", "ş").replace("ă", "ă")
    assert parse_invoice_text(buyer, full).total_bani == 123456


def test_parse_takes_invoice_date_not_due_date():
    assert parse_invoice_text(BUYER_TEXT, FULL_TEXT).data == datetime.date(2026, 10, 19)


def test_parse_due_date_alone_is_not_an_invoice_date():
    full = FULL_TEXT.replace("Data: 19.10.2026\n", "")
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(BUYER_TEXT, full)
    assert reason_of(excinfo) == pdf_reader.NO_DATE


@pytest.mark.parametrize(
    "cui_line",
    [
        "C.U.I./C.I.F.: RO 12345678",
        "C.U.I./C.I.F.: RO12345678",
        "C.U.I.: 12345678",
        "CUI: RO 12345678",
    ],
)
def test_parse_cui_formats(cui_line):
    buyer = BUYER_TEXT.replace("C.U.I./C.I.F.: RO 12345678", cui_line)
    assert parse_invoice_text(buyer, FULL_TEXT).cui == "12345678"


def test_parse_ignores_a_furnizor_block_below_the_buyer():
    # Buyer has no CUI; the next CUI belongs to Furnizor and must not be taken.
    buyer = "Cumpărător: TRANSPORT TEST S.R.L.\nFurnizor: OMV Petrom\nC.U.I./C.I.F.: RO 11111118\n"
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(buyer, FULL_TEXT)
    assert reason_of(excinfo) == pdf_reader.NO_CUI


def test_parse_whole_lei_total():
    full = FULL_TEXT.replace("1.234,56", "100 lei")
    assert parse_invoice_text(BUYER_TEXT, full).total_bani == 10000


@pytest.mark.parametrize(
    ("buyer", "full", "reason"),
    [
        ("Nr. Reg. Com./Anul:J2022\nC.U.I.: RO 12345678\n", FULL_TEXT, "NO_BUYER_BLOCK"),
        ("Cumpărător:\nC.U.I./C.I.F.: RO 12345678\n", FULL_TEXT, "NO_NAME"),
        ("Cumpărător: TRANSPORT TEST S.R.L.\n", FULL_TEXT, "NO_CUI"),
        (BUYER_TEXT, FULL_TEXT.replace("Total de plată: 1.234,56", ""), "NO_TOTAL"),
        (BUYER_TEXT, FULL_TEXT.replace("1.234,56", "12.3456"), "BAD_TOTAL"),
        (BUYER_TEXT, FULL_TEXT.replace("19.10.2026", "31.02.2026"), "BAD_DATE"),
        (BUYER_TEXT, FULL_TEXT.replace("Aferentă facturii cu nr.: 109000000000001\n", ""),
         "NO_NUMBER"),
    ],
)
def test_parse_missing_or_bad_fields_give_a_romanian_reason(buyer, full, reason):
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(buyer, full)
    assert reason_of(excinfo) == getattr(pdf_reader, reason)


def test_parse_two_different_totals_is_refused():
    full = FULL_TEXT + "Total de plată: 50.00\n"
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(BUYER_TEXT, full)
    assert reason_of(excinfo) == pdf_reader.BAD_TOTAL


def test_parse_same_total_twice_is_fine():
    full = FULL_TEXT + "Total de plată: 1.234,56\n"
    assert parse_invoice_text(BUYER_TEXT, full).total_bani == 123456


def test_reasons_are_romanian_text():
    for name in ("PDF_DAMAGED", "NO_TEXT", "NO_BUYER_BLOCK", "NO_CUI", "NO_TOTAL"):
        assert isinstance(getattr(pdf_reader, name), str) and getattr(pdf_reader, name)


# ---------- read_invoice: real PDF files ----------


def test_read_two_column_pdf_takes_buyer_cui_not_supplier(tmp_path):
    pdf = build_pdf(tmp_path / "f.pdf", sample_like_items())
    invoice = read_invoice(pdf)
    assert invoice.cui == FAKE_BUYER_CUI
    assert invoice.cui != FAKE_SUPPLIER_CUI
    assert invoice.nume == "FIRMA TEST S.R.L."
    assert invoice.total_bani == 19989
    assert invoice.data == datetime.date(2026, 6, 5)
    assert invoice.numar == "109000000000001"


def test_read_pdf_with_romanian_letters(tmp_path):
    font = find_unicode_font()
    if font is None:
        pytest.skip("no font with Romanian letters on this machine")
    pdf = build_pdf(tmp_path / "f.pdf", sample_like_items(diacritics=True), font_file=font)
    invoice = read_invoice(pdf)
    assert invoice.cui == FAKE_BUYER_CUI
    assert invoice.total_bani == 19989
    assert invoice.data == datetime.date(2026, 6, 5)


def test_read_pdf_with_furnizor_above_buyer(tmp_path):
    # Stacked layout: Furnizor block first, Cumparator block under it, same x.
    items = [
        (30, 40, "Furnizor: OMV Petrom Marketing SRL"),
        (30, 50, f"C.U.I./C.I.F.: RO {FAKE_SUPPLIER_CUI}"),
        (30, 70, "Cumparator: FIRMA TEST S.R.L."),
        (30, 80, f"C.U.I./C.I.F.: RO {FAKE_BUYER_CUI}"),
        (30, 120, "Aferenta facturii cu nr.: 109000000000002"),
        (30, 130, "Data: 05.06.2026"),
        (30, 300, "Total de plata: 100"),
    ]
    invoice = read_invoice(build_pdf(tmp_path / "f.pdf", items))
    assert invoice.cui == FAKE_BUYER_CUI
    assert invoice.total_bani == 10000


def test_read_pdf_without_buyer_block(tmp_path):
    items = [(x, y, t) for x, y, t in sample_like_items() if not t.startswith("Cumparator")]
    with pytest.raises(InvoiceError) as excinfo:
        read_invoice(build_pdf(tmp_path / "f.pdf", items))
    assert reason_of(excinfo) == pdf_reader.NO_BUYER_BLOCK


def test_read_pdf_without_text(tmp_path):
    with pytest.raises(InvoiceError) as excinfo:
        read_invoice(build_pdf(tmp_path / "blank.pdf", []))
    assert reason_of(excinfo) == pdf_reader.NO_TEXT


def test_read_damaged_file(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(InvoiceError) as excinfo:
        read_invoice(bad)
    assert reason_of(excinfo) == pdf_reader.PDF_DAMAGED


def test_read_missing_file(tmp_path):
    with pytest.raises(InvoiceError) as excinfo:
        read_invoice(tmp_path / "gone.pdf")
    assert reason_of(excinfo) == pdf_reader.PDF_DAMAGED


def test_read_failure_is_logged_with_file_name(tmp_path, caplog):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(InvoiceError):
        read_invoice(bad)
    assert "bad.pdf" in caplog.text
    assert pdf_reader.PDF_DAMAGED in caplog.text


def test_read_accepts_str_path(tmp_path):
    pdf = build_pdf(tmp_path / "f.pdf", sample_like_items())
    assert read_invoice(str(pdf)).cui == FAKE_BUYER_CUI


# ---------- found in code review ----------


@pytest.mark.parametrize(
    "number_line",
    [
        "Factura numarul 109000000000001",
        "Factura numărul: 109000000000001",
        "Factura numar 109000000000001",
        "Factura nr.109000000000001",
        "Factura nr. din 05.06.2026\nAferentă facturii cu nr.: 109000000000001",
    ],
)
def test_parse_invoice_number_label_variants(number_line):
    full = FULL_TEXT.replace("Aferentă facturii cu nr.: 109000000000001", number_line)
    assert parse_invoice_text(BUYER_TEXT, full).numar == "109000000000001"


def test_parse_number_label_followed_by_a_word_is_not_a_number():
    full = FULL_TEXT.replace("Aferentă facturii cu nr.: 109000000000001", "Factura nr. din iunie")
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(BUYER_TEXT, full)
    assert reason_of(excinfo) == pdf_reader.NO_NUMBER


@pytest.mark.parametrize("colon", ["：", "﹕"])  # full-width and small colon
def test_parse_buyer_label_with_unusual_colon(colon):
    buyer = BUYER_TEXT.replace("Cumpărător:", f"Cumpărător{colon}")
    invoice = parse_invoice_text(buyer, FULL_TEXT)
    assert invoice.nume == "TRANSPORT TEST S.R.L."
    assert invoice.cui == "12345678"


def test_parse_cui_far_below_the_buyer_block_is_not_taken():
    # Buyer block without a CUI; a CUI many lines lower belongs to someone else.
    filler = "".join(f"rand de text {n}\n" for n in range(7))
    buyer = "Cumpărător: TRANSPORT TEST S.R.L.\nNr. Reg. Com./Anul:J2022\n" + filler
    buyer += "C.U.I.: RO 11111118\n"
    with pytest.raises(InvoiceError) as excinfo:
        parse_invoice_text(buyer, FULL_TEXT)
    assert reason_of(excinfo) == pdf_reader.NO_CUI


def test_read_pdf_footer_cui_is_not_taken_when_buyer_cui_missing(tmp_path):
    items = [item for item in sample_like_items() if FAKE_BUYER_CUI not in item[2]]
    items.append((390, 700, f"OMV Petrom S.R.L. C.U.I. RO {FAKE_SUPPLIER_CUI}"))
    with pytest.raises(InvoiceError) as excinfo:
        read_invoice(build_pdf(tmp_path / "f.pdf", items))
    assert reason_of(excinfo) == pdf_reader.NO_CUI
