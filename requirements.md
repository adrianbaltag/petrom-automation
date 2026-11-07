# Petrom Dashboard — milestones (part B)

Full plan: https://claude.ai/artifact/FBbmRUgMgKe7DNP6dzAwzy

- [x] M1 — Skeleton: git repo, Flask app, SQLite schema, setup_logging(), empty dashboard page · Done when: pytest green and the page opens in the browser (user check)
- [x] M2 — PDF reader: buyer CUI, name, total, invoice date, number parser · Done when: unit tests pass on the sample PDF and fake PDFs
- [x] M3 — Automation run: backup, fingerprint, save-then-move, month subfolders, Facturi-erori, lock, summary · Done when: end-to-end test on a fake folder passes
- [x] M4 — Dashboard table: monthly view, colours, %, sort, search, auto-fit pagination, clock, full screen · Done when: Playwright test passes and user checks it on screen
- [x] M5 — CRUD: add, edit name and monthly max, archive/restore, invoice list with delete · Done when: tests pass and Playwright creates a company
- [ ] M6 — Filters: 7 days, 30 days, calendar, month picker · Done when: date-range unit tests pass and user checks it
- [ ] M7 — Setări: folders, archived companies, backups, Despre · Done when: tests pass and user checks it
- [ ] M8 — Email alerts: spool, sender, rate limit, crash alert · Done when: tests pass with a fake mail server and user receives a real test email
- [ ] M9 — Release: start.bat, start.command, make_release.py, Romanian guide, first GitHub Release · Done when: user runs the zip from GitHub on his Windows laptop end to end, including double-clicking the launcher twice (second copy must show the "rulează deja" message, not start)
