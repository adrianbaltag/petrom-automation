# Tracking log

## Now working on
Nothing in progress. M3 done.

## Next up
M4 — Dashboard table.

Notes for M4:
- The button calls `POST /ruleaza`. It returns JSON: `ok`, `mesaj` (headline), `total`, `adaugate`,
  `erori` (list of `fisier` + `motiv`), `mutate`, `note`. 409 = "Automatizarea rulează deja.",
  403 = refused by the other-website guard, 500 = backup/folder failure or crash (`mesaj` explains).
- Every POST from the page must come from the dashboard itself (Origin check in `create_app`).
- Grey out the button while the request runs (the server lock is the backstop).

Open items from M3 (decided 2026-11-06):
- Before the first release (M9) or with the first schema change after it: add database upgrade code
  (e.g. `PRAGMA user_version`). `init_db` only creates missing tables, it never adds columns.
- M9 Windows check: open a PDF in a viewer, run, and confirm no copy is left in Facturi-procesate and the
  summary says "salvată, dar nu am putut-o muta". Also confirm the Desktop lookup finds the OneDrive Desktop.
- M7: when folders can be changed, test folders on another drive (copy-then-delete path).
- The buyer-block limits in `pdf_reader` were tuned on ONE real sample. Add more real PDFs to `samples/`
  (each with a `.json` of expected values) when person B sends them.

Notes from the M1 review:
- `run.py` calls `create_app()` before the port check. If `create_app()` ever starts background work, move the port check before it.
- Two copies started within milliseconds could both pass the port check on Windows. M3's run lock is the backstop.

## Last update
2026-11-06 — M3 done: `automation.run_automation` (OS run lock, backup only when there are PDFs, folders
created on the real Desktop, duplicates by fingerprint or invoice number with the `mutat` flag, save then
move to `Facturi-procesate\YYYY-MM`, `(2)` on clashes, Facturi-erori + `motive.txt`, Romanian summary),
`POST /ruleaza`, and a guard refusing other websites/host names. 177 tests green incl. e2e on a fake
folder. code-reviewer PASS after 4 rounds (user approved rounds 3 and 4) plus a /code-review pass.

2026-11-06 — M2 done: `money.parse_amount` (agreed rule: 1–2 digits after the last separator = decimals,
3 = thousands, whole lei allowed, anything unclear refused) and `pdf_reader.read_invoice` (buyer CUI from
the right-hand Cumpărător column only, name, total, invoice date, invoice number; labels with or without
diacritics; Romanian reasons). Fake two-column PDFs built with fpdf2 during tests; real sample checked
against a gitignored JSON (user confirmed the values). 116 tests green, code review PASS after 2 rounds.
