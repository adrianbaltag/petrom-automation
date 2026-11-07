# Tracking log

## Now working on
Nothing in progress. M1 done.

## Next up
M2 — PDF reader. Needs the sample PDF in `samples/` first (folder is gitignored).

Notes for M3 from the M1 review:
- `run.py` calls `create_app()` before the port check. If `create_app()` ever starts background work, move the port check before it.
- Two copies started within milliseconds could both pass the port check on Windows. M3's run lock is the backstop.

## Last update
2026-11-06 — M1 done: Flask skeleton, SQLite schema (whole-bani checks), logging, Romanian empty page,
launcher entry `run.py` (127.0.0.1 only, detects an already-running copy). Data folder: Windows
%LOCALAPPDATA%\PetromDashboard, Mac project `data/`. 34 tests green, code review PASS after 3 rounds,
user saw the page open.
