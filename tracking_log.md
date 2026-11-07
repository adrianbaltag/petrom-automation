# Tracking log

## Now working on
Nothing in progress. M2 done.

## Next up
M3 — Automation run.

Notes for M3:
- Add an invoice-number column (`numar`, UNIQUE) to `facturi` and block duplicates by it as well as by
  the file fingerprint (decided 2026-11-06: a re-downloaded copy of a receipt can have a different hash).
- `read_invoice(path)` returns `Invoice(cui, nume, total_bani, data, numar)` or raises `InvoiceError`;
  use `err.motiv` (Romanian) as the Facturi-erori reason. It already logs every refusal.
- `read_invoice` closes the PDF before returning, so the file can be moved on Windows right after.
- The buyer-block limits (gap of 2 line heights, max 6 lines) were tuned on ONE real sample. Add more
  real PDFs to `samples/` (each with a `.json` of expected values) when person B sends them.

Notes from the M1 review:
- `run.py` calls `create_app()` before the port check. If `create_app()` ever starts background work, move the port check before it.
- Two copies started within milliseconds could both pass the port check on Windows. M3's run lock is the backstop.

## Last update
2026-11-06 — M2 done: `money.parse_amount` (agreed rule: 1–2 digits after the last separator = decimals,
3 = thousands, whole lei allowed, anything unclear refused) and `pdf_reader.read_invoice` (buyer CUI from
the right-hand Cumpărător column only, name, total, invoice date, invoice number; labels with or without
diacritics; Romanian reasons). Fake two-column PDFs built with fpdf2 during tests; real sample checked
against a gitignored JSON (user confirmed the values). 116 tests green, code review PASS after 2 rounds.
