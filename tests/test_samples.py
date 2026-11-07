"""Check the reader against REAL Petrom PDFs kept in samples/ (gitignored, never committed).

For each samples/<name>.pdf there must be a samples/<name>.json with the expected
values, for example:
    {"cui": "...", "nume": "...", "total_bani": 19989,
     "data": "2026-10-19", "numar": "..."}
Real company data stays in those two gitignored files, never in this test.
On a machine without samples (a fresh clone), these tests are skipped.
"""

import datetime
import json
from pathlib import Path

import pytest

from petrom_dashboard.pdf_reader import read_invoice

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLE_PDFS = sorted(SAMPLES.glob("*.pdf")) if SAMPLES.is_dir() else []


@pytest.mark.skipif(not SAMPLE_PDFS, reason="no real sample PDFs in samples/")
@pytest.mark.parametrize("pdf", SAMPLE_PDFS, ids=lambda p: p.name)
def test_real_sample(pdf):
    expected_file = pdf.with_suffix(".json")
    assert expected_file.exists(), f"add {expected_file.name} with the expected values"
    expected = json.loads(expected_file.read_text(encoding="utf-8"))

    invoice = read_invoice(pdf)

    assert invoice.cui == expected["cui"]
    assert invoice.nume == expected["nume"]
    assert invoice.total_bani == expected["total_bani"]
    assert invoice.data == datetime.date.fromisoformat(expected["data"])
    assert invoice.numar == expected["numar"]
