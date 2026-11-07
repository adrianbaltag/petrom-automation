# petrom-automation

Local Flask dashboard tracking each company's monthly invoice total against its monthly max,
fed by a button that reads Petrom PDF invoices. Built on Mac, run by a non-coder on Windows.

- Plan (all decisions, milestones): https://claude.ai/artifact/FBbmRUgMgKe7DNP6dzAwzy
- Milestones: `requirements.md` · progress: `tracking_log.md`

## Commands
- Tests: `.venv/bin/python -m pytest -q`
- Lint: `ruff check .` and `ruff check --select T201,LOG,G .`
- Run locally: `.venv/bin/python run.py` → http://127.0.0.1:8765/
- Install deps: `uv pip install --python .venv/bin/python -r requirements-dev.txt`
- Keep `requirements.txt` pip-installable: the Windows launcher uses plain pip, not uv.

## Rules for this project
- The GitHub repo is PUBLIC. Never commit PDFs, `.db`, logs, `data/`, `samples/`, `.env` or config
  with the Gmail app password. `tests/test_repo_hygiene.py` guards this.
- Money is whole bani (int) everywhere until display; display is Romanian: `1.234,56 lei`.
- UI text is Romanian; code, comments and logs are English (plus Romanian user-facing messages).
- Server binds 127.0.0.1 only.
- Data folder: `petrom_dashboard/paths.py` (Windows %LOCALAPPDATA%\PetromDashboard, Mac `data/`).
  Tests must set `PETROM_DATA_DIR` or use the `app` fixture, never the real folder.
- Invoices carry two CUIs: always take the one in the Cumparator block, never Furnizor.
- Must work on Windows: test path handling and anything OS-specific with Windows in mind.
