# Tracking log

## Now working on
Nothing in progress. M6 done.

## Next up
M7 — Setări: folders, archived companies, backups, Despre.

Notes for M7:
- Until Setări sets folders, Rulează uses folders on the real Desktop: keep screen checks on fake data
  away from it (M6 skipped Rulează in the screen check for this reason).
- Deferred from M6 (user chose "edit window shows this month"): the Editează window's invoice list and
  a new max always use the CURRENT month, even when a past month is picked. Revisit only if she asks.

Decisions from M6 (2026-11-07, user approved):
- The server works out the dates (`dashboard.period_from_args`); the page sends `?luna=`, `?zile=7|30`
  or `?de=&pana=`. "7 zile" = today plus the 6 days before. Totals by invoice date, both edges included.
- Month list = Romanian month names, newest first, back to the oldest invoice's month (archived
  companies' invoices count).
- Calendar = two date boxes + Aplică: De la ≤ Până la, no future dates, no length limit; refused ranges
  get a Romanian message (400) and the table keeps the previous filter and page.
- Range views: Firmă, CUI, Suma perioadei only, biggest first, grey note; no max, %, colours.
- The filter stays after Rulează or an edit. Midnight: Luna curentă and 7/30 zile move forward; a picked
  month or range stays. Reopening the page = Luna curentă. Only active companies in every view.
- Bug fixed: the edit window's max box now always starts from THIS month's max (`edit_max_inputs`);
  before, editing only the name while a past month was shown silently saved that month's max.

Decisions from M5 (2026-11-07, user approved):
- "✎ Editează" button next to each name (white in light mode, dark in dark mode; only ✎ on a phone),
  not a clickable row.
- A max change applies to this month and later; earlier months keep theirs; last edit in a month wins.
- CUI: RO, any spaces and leading zeros removed, check digit verified on manual add. One shared rule
  (`cui.clean_cui`) for the PDF reader and the form; the reader does NOT check the digit.
- Max optional when adding; once set it can be changed but never emptied. 0 or below refused.
- Same names allowed (CUI is the identity). Active duplicate CUI refused with the reason; archived one
  offers Restaurează, which uses the typed max and keeps the old name.
- Archive asks first; "Firme arhivate (N)" link under the table restores (moves to Setări in M7).
- Invoice delete: this month's list, asks first, backup first (own group `petrom-stergere-*`, 30 kept,
  never pushes out run backups), DB row only, PDF stays.
- Success messages are green (`--status-success`), also for automation runs with no errors.
- Open: at 1280px wide the top bar wraps "Ecran complet" onto a second line (fine, user may revisit).

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
2026-11-07 — M6 done: filter row (Luna curentă, Ultimele 7 / 30 de zile, Luna list, De la / Până la),
`period_from_args`, `range_rows`, `month_choices`, `edit_max_inputs`, `/date` filters. 395 tests green incl.
35 Playwright tests. code-reviewer PASS after 3 rounds (user approved round 3). User checked 7 steps on
screen with fake data. `ruff format` still wants to reformat two older files (test_firme_e2e.py,
test_pdf_reader.py), untouched in M6.

2026-11-07 — M5 done: `firme.py` (add, edit, archive, restore, month invoices, delete), `firme_routes.py`
(7 JSON routes behind the origin guard), `cui.py` (shared CUI cleanup), add/edit/archived/confirm windows
(`firme.js`), green success box, focus kept for keyboard users. 330 tests green incl. 24 Playwright tests.
code-reviewer PASS after 5 rounds (user approved rounds 3–4) plus a /code-review pass. User checked all
8 steps on screen with fake data.

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
