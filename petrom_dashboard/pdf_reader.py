"""Read one Petrom PDF invoice: buyer CUI, buyer name, total, invoice date and number.

The real PDF has two columns side by side: Furnizor (supplier) on the left and
Cumpărător (buyer) on the right. Plain text extraction glues the two columns
together line by line, so we cut the page and read only the buyer's part:
everything to the right of and below the "Cumpărător:" label. That way the
supplier's CUI can never be picked up.

Every problem raises InvoiceError with a Romanian reason (`motiv`) that the
automation shows next to the file in Facturi-erori.
"""

import datetime
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from petrom_dashboard.cui import clean_cui
from petrom_dashboard.money import AmountError, parse_amount

logger = logging.getLogger(__name__)

# Romanian reasons shown to the user.
PDF_DAMAGED = "Fișier PDF deteriorat sau imposibil de citit"
NO_TEXT = "PDF fără text (poate e scanat)"
NO_BUYER_BLOCK = "Lipsește blocul Cumpărător"
NO_NAME = "Lipsește numele cumpărătorului"
NO_CUI = "Lipsește CUI-ul cumpărătorului"
NO_TOTAL = "Lipsește «Total de plată»"
BAD_TOTAL = "«Total de plată» neclar"
NO_DATE = "Lipsește data facturii"
BAD_DATE = "Data facturii nu e validă"
NO_NUMBER = "Lipsește numărul facturii"

# Limits of the buyer block, so a CUI lower on the page is never taken as the buyer's.
# In the sample the CUI is 2 lines under the label and lines are ~4pt apart.
MAX_BUYER_LINES = 6
BLOCK_GAP_FACTOR = 2

# All patterns run on text with the diacritics removed (see _plain), so
# "Cumpărător" and "Cumparator" both match.
_BUYER_LABEL = re.compile(r"^\s*cumparator\s*:", re.IGNORECASE)
_FURNIZOR = re.compile(r"furnizor", re.IGNORECASE)
_CUI_OR_CIF = r"(?:C\.?\s*U\.?\s*I\.?|C\.?\s*I\.?\s*F\.?)"
_CUI = re.compile(
    rf"\b{_CUI_OR_CIF}(?:\s*/\s*{_CUI_OR_CIF})?\s*:?\s*(?:RO)?\s*(\d{{2,10}})\b",
    re.IGNORECASE,
)
_TOTAL = re.compile(r"total\s+de\s+plata\s*:?[ \t]*([^\n]*)", re.IGNORECASE)
# "Data:" only. "Data scadentă:" (due date) has a word before the colon, so it never matches.
_DATE = re.compile(r"\bdata\s*:\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", re.IGNORECASE)
# The label must end on a word boundary ("numarul", not "numar" + "ul"), and the
# number must hold at least one digit ("nr. din ..." is not a number).
_NUMBER = re.compile(
    r"factur\w*\s+(?:cu\s+)?(?:numarul|numar|nr)\b\.?\s*:?\s*([A-Z0-9-]*\d[A-Z0-9-]*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Invoice:
    cui: str  # digits only, without "RO": "46133455"
    nume: str  # buyer name as printed
    total_bani: int  # "Total de plată" in whole bani
    data: datetime.date  # invoice date ("Data:")
    numar: str  # invoice number, used to spot the same invoice twice


class InvoiceError(Exception):
    """The PDF can't be used. `motiv` is the Romanian reason for the user."""

    def __init__(self, motiv, detail=""):
        super().__init__(motiv)
        self.motiv = motiv
        self.detail = detail  # technical detail for the log only


def read_invoice(path):
    """Read a Petrom PDF and return an Invoice. Raise InvoiceError if anything is missing."""
    path = Path(path)
    try:
        buyer_text, full_text = _extract_texts(path)
        return parse_invoice_text(buyer_text, full_text)
    except InvoiceError as err:
        logger.warning("Invoice %s refused: %s %s", path.name, err.motiv, err.detail)
        raise


def parse_invoice_text(buyer_text, full_text):
    """Find the invoice fields in already extracted text.

    buyer_text: only the buyer's part of the page, starting with "Cumpărător:".
    full_text:  the whole document, for the total, date and invoice number.
    """
    cui, nume = _parse_buyer(buyer_text)
    plain = _plain(full_text)
    return Invoice(
        cui=cui,
        nume=nume,
        total_bani=_parse_total(plain),
        data=_parse_date(plain),
        numar=_parse_number(plain),
    )


def _extract_texts(path):
    """Return (buyer column text, whole document text). Damaged file -> InvoiceError."""
    try:
        with pdfplumber.open(path) as pdf:
            page_texts = [page.extract_text() or "" for page in pdf.pages]
            if not any(text.strip() for text in page_texts):
                raise InvoiceError(NO_TEXT)
            buyer_text = ""
            for page in pdf.pages:
                buyer_text = _buyer_column_text(page)
                if buyer_text:
                    break
    except InvoiceError:
        raise
    except Exception as exc:  # pdfplumber/pdfminer raise many different errors on bad files
        raise InvoiceError(PDF_DAMAGED, detail=f"{type(exc).__name__}: {exc}") from exc
    return buyer_text, "\n".join(page_texts)


def _buyer_column_text(page):
    """The buyer block: lines right of and below 'Cumpărător:', up to the first big gap.

    Returns '' if the page has no buyer label. The block ends where the empty
    space before the next line is more than BLOCK_GAP_FACTOR line heights, so
    text lower in the same column (body, total, footer) is never part of it.
    """
    label = next(
        (w for w in page.extract_words() if _plain(w["text"]).rstrip(":").lower() == "cumparator"),
        None,
    )
    if label is None:
        return ""
    box = (max(label["x0"] - 2, 0), max(label["top"] - 2, 0), page.width, page.height)
    lines = page.within_bbox(box).extract_text_lines()
    block = lines[:1]
    for previous, line in zip(lines, lines[1:]):
        line_height = previous["bottom"] - previous["top"]
        if line["top"] - previous["bottom"] > BLOCK_GAP_FACTOR * line_height:
            break
        block.append(line)
    return "\n".join(line["text"] for line in block)


def _parse_buyer(buyer_text):
    """Return (cui, name) from the buyer block."""
    # NFKC keeps "ă" as one letter but turns odd colons (full-width "：") into ":",
    # the same way _plain does, so the label check and the name cut agree.
    lines = unicodedata.normalize("NFKC", buyer_text).splitlines()
    start = next((i for i, line in enumerate(lines) if _BUYER_LABEL.match(_plain(line))), None)
    if start is None:
        raise InvoiceError(NO_BUYER_BLOCK)

    parts = lines[start].split(":", 1)
    if len(parts) != 2:
        raise InvoiceError(NO_BUYER_BLOCK, detail="buyer label without a colon")
    nume = " ".join(parts[1].split())
    if not nume:
        raise InvoiceError(NO_NAME)

    # The buyer block is at most MAX_BUYER_LINES lines after the label, and ends
    # earlier where a Furnizor block starts (stacked layouts).
    block = []
    for line in lines[start + 1 : start + 1 + MAX_BUYER_LINES]:
        plain_line = _plain(line)
        if _FURNIZOR.search(plain_line):
            break
        block.append(plain_line)
    match = _CUI.search("\n".join(block))
    if match is None:
        raise InvoiceError(NO_CUI)
    cui = clean_cui(match.group(1))  # same rule as the Adaugă firmă form
    if len(cui) < 2:
        raise InvoiceError(NO_CUI, detail=f"CUI {match.group(1)!r} is only zeros")
    return cui, nume


def _parse_total(plain):
    found = _TOTAL.findall(plain)
    if not found:
        raise InvoiceError(NO_TOTAL)
    try:
        values = {parse_amount(text) for text in found}
    except AmountError as exc:
        raise InvoiceError(BAD_TOTAL, detail=str(exc)) from exc
    if len(values) != 1:
        raise InvoiceError(BAD_TOTAL, detail=f"different totals: {sorted(values)}")
    return values.pop()


def _parse_date(plain):
    match = _DATE.search(plain)
    if match is None:
        raise InvoiceError(NO_DATE)
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError as exc:
        raise InvoiceError(BAD_DATE, detail=match.group(0)) from exc


def _parse_number(plain):
    match = _NUMBER.search(plain)
    if match is None:
        raise InvoiceError(NO_NUMBER)
    return match.group(1)


def _plain(text):
    """Remove diacritics: 'Cumpărător' -> 'Cumparator', 'ș'/'ş' -> 's'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
