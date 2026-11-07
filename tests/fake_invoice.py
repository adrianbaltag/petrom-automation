"""Build fake Petrom-like PDFs during tests (PDFs are never committed: the repo is public).

The layout copies the real sample: two columns side by side, Furnizor on the
left (x=30) and Cumparator on the right (x=390), on an A4 page measured in
points. All data here is made up.
"""

from pathlib import Path

from fpdf import FPDF

# A font with Romanian letters (ă, ș, ț). Core PDF fonts can't draw them.
UNICODE_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),  # Mac
    Path("C:/Windows/Fonts/arial.ttf"),  # Windows
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),  # Linux
]

FAKE_BUYER_CUI = "12345678"
FAKE_SUPPLIER_CUI = "11111118"  # decoy: must never be picked


def find_unicode_font():
    """Return a TTF path with Romanian letters, or None if this machine has none."""
    return next((path for path in UNICODE_FONT_CANDIDATES if path.exists()), None)


def sample_like_items(diacritics=False):
    """Text pieces (x, y, text) laid out like the real Petrom 'Nota de informare'."""
    cumparator = "Cumpărător" if diacritics else "Cumparator"
    plata = "plată" if diacritics else "plata"
    scadenta = "scadentă" if diacritics else "scadenta"
    aferenta = "Aferentă" if diacritics else "Aferenta"
    return [
        # Left column: supplier (Furnizor). Its CUI sits on the SAME line as the buyer's.
        (30, 40, "Furnizor: OMV Petrom Marketing SRL"),
        (30, 50, "Nr. Reg. Com./Anul: J1998000000000"),
        (30, 60, f"C.U.I./C.I.F.: RO {FAKE_SUPPLIER_CUI}"),
        (30, 70, "Adresa: Strada Test, nr. 1"),
        # Right column: buyer (Cumparator).
        (390, 40, f"{cumparator}: FIRMA TEST S.R.L."),
        (390, 50, "Nr. Reg. Com./Anul:J2022000000000"),
        (390, 60, f"C.U.I./C.I.F.: RO {FAKE_BUYER_CUI}"),
        # Middle: invoice number and date (value far to the right, like the sample).
        (243, 114, "Nota de informare"),
        (232, 141, f"{aferenta} facturii cu nr.: 109000000000001"),
        (232, 151, "Data:"),
        (344, 151, "05.06.2026"),
        # Body text that reaches into the right column, below the buyer block.
        (32, 172, "Factura va fi transmisa prin RO e-Factura, conform OUG"),
        (400, 172, "120/2021"),
        (30, 300, f"Data {scadenta}: 20.06.2026"),
        (300, 343, "Semnatura si stampila"),
        (422, 343, f"Total de {plata}: 199.89"),
    ]


def build_pdf(path, items, font_file=None):
    """Write a one-page PDF with each (x, y, text) placed at x, y (points, y = baseline)."""
    pdf = FPDF(unit="pt", format="A4")
    pdf.add_page()
    if font_file:
        pdf.add_font("testfont", "", str(font_file))
        pdf.set_font("testfont", size=8)
    else:
        pdf.set_font("Helvetica", size=8)
    for x, y, text in items:
        pdf.text(x, y, text)
    pdf.output(str(path))
    return path


def make_invoice_pdf(
    path,
    cui=FAKE_BUYER_CUI,
    nume="FIRMA TEST S.R.L.",
    numar="109000000000001",
    total="199.89",
    data="05.06.2026",
):
    """Write a sample-like invoice PDF with the given buyer, number, total and date."""
    swaps = {
        f"C.U.I./C.I.F.: RO {FAKE_BUYER_CUI}": f"C.U.I./C.I.F.: RO {cui}",
        "Cumparator: FIRMA TEST S.R.L.": f"Cumparator: {nume}",
        "Aferenta facturii cu nr.: 109000000000001": f"Aferenta facturii cu nr.: {numar}",
        "05.06.2026": data,
        "Total de plata: 199.89": f"Total de plata: {total}",
    }
    items = []
    for x, y, text in sample_like_items():
        if x == 30 and "C.U.I." in text:  # the supplier's CUI line stays as it is
            items.append((x, y, text))
            continue
        items.append((x, y, swaps.get(text, text)))
    return build_pdf(Path(path), items)
