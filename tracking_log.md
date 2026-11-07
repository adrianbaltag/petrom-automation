# Tracking log

## Now working on
Nothing in progress. M4 done.

## Next up
M5 — CRUD: add, edit name and monthly max, archive/restore, invoice list with delete.

Notes for M5:
- Refuse a max of 0 or below on input. Until then `dashboard.month_rows` shows it as "Max nesetat" and logs
  a warning.
- Add the "Adaugă firmă" button back to the top bar (hidden in M4 on purpose: no buttons that do nothing).
- Max for a month = latest `limite` row in or before that month (read-time lookup, no copied rows).
  Editing June's max therefore also changes July if July has no row of its own. Check this matches the
  plan's "changing June never changes May" when building the edit form.
- The page reads `GET /date` (JSON rows) on load and after each run; reuse it after add/edit.

Decisions from M4 (2026-11-07, user approved):
- % is rounded down (999,99 of 1.000 shows 99%, never 100% without PESTE LIMITĂ).
- Orange/red rows carry a text label ("Peste 50%" / "Peste 75%") so colour is never alone.
- "Max nesetat" rows are always last when sorting by % or max, in both directions.
- Buttons for later milestones are hidden, not disabled. Month picker and filters come in M6.
- Playwright (pytest-playwright 0.10.0, playwright 1.64.1) is dev-only; run
  `.venv/bin/python -m playwright install chromium` once on a new machine.

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
2026-11-07 — M4 done: `dashboard.month_rows` (month total, max carried forward, exact-bani colour levels,
% rounded down), `money.format_lei`, `GET /date`, and the page (sort, search, rows per page fitted to the
window, pager with "…", Romanian clock, month switch at midnight, full screen, Rulează button with result
box). 222 tests green incl. 10 Playwright tests. code-reviewer PASS after 3 rounds (user approved round 3).
Accessibility pass: stronger control borders, table label, pager announces itself. User checked on screen.

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
