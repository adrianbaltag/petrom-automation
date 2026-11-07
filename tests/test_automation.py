"""Tests for the automation run: each building block first, then whole runs on fake folders."""

import codecs
import sqlite3
import sys
from pathlib import Path

import pytest
from db_helpers import open_db
from fake_invoice import FAKE_BUYER_CUI, make_invoice_pdf

from petrom_dashboard import automation
from petrom_dashboard.automation import (
    ALREADY_PROCESSED,
    AlreadyRunning,
    BackupError,
    Folders,
    RunLock,
    RunSummary,
    backup_database,
    desktop_dir,
    fingerprint,
    get_folders,
    run_automation,
    unique_destination,
)
from petrom_dashboard.db import connect, init_db
from petrom_dashboard.pdf_reader import PDF_DAMAGED

# ---------- small building blocks ----------


def test_fingerprint_same_bytes_same_value(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")

    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_different_bytes_different_value(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"one")
    b.write_bytes(b"two")

    assert fingerprint(a) != fingerprint(b)


def test_unique_destination_keeps_a_free_name(tmp_path):
    assert unique_destination(tmp_path, "factura.pdf") == tmp_path / "factura.pdf"


def test_unique_destination_adds_2_then_3(tmp_path):
    (tmp_path / "factura.pdf").write_bytes(b"x")
    assert unique_destination(tmp_path, "factura.pdf") == tmp_path / "factura (2).pdf"

    (tmp_path / "factura (2).pdf").write_bytes(b"x")
    assert unique_destination(tmp_path, "factura.pdf") == tmp_path / "factura (3).pdf"


def test_backup_copies_the_data(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    with open_db(db_file) as conn:
        conn.execute("INSERT INTO firme (cui, nume) VALUES ('46133455', 'ALFA SRL')")

    backup = backup_database(db_file, tmp_path / "backups")

    assert backup.parent == tmp_path / "backups"
    assert backup.name.startswith("petrom-") and backup.suffix == ".db"
    copy = sqlite3.connect(backup)
    try:
        assert copy.execute("SELECT nume FROM firme").fetchone()[0] == "ALFA SRL"
    finally:
        copy.close()


def test_backup_keeps_only_the_newest_30(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    backups = tmp_path / "backups"
    backups.mkdir()
    old_names = [f"petrom-2020010{i // 10}-0000{i % 10:02d}-000000.db" for i in range(35)]
    for name in old_names:
        (backups / name).write_bytes(b"old")
    (backups / "notes.txt").write_text("not a backup")

    newest = backup_database(db_file, backups)

    kept = sorted(p.name for p in backups.glob("petrom-*.db"))
    assert len(kept) == 30
    assert newest.name in kept
    assert sorted(old_names)[0] not in kept  # the oldest went first
    assert (backups / "notes.txt").exists()  # other files are never touched


def test_lock_refuses_a_second_run(tmp_path):
    lock_file = tmp_path / "rulare.lock"
    with RunLock(lock_file):
        with pytest.raises(AlreadyRunning):
            with RunLock(lock_file):
                pass


def test_lock_can_be_taken_again_after_release(tmp_path):
    lock_file = tmp_path / "rulare.lock"
    with RunLock(lock_file):
        pass
    with RunLock(lock_file):
        pass


def test_desktop_on_mac_is_home_desktop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert desktop_dir() == Path.home() / "Desktop"


def test_desktop_on_windows_asks_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(automation, "_windows_desktop", lambda: tmp_path / "OneDrive" / "Desktop")
    assert desktop_dir() == tmp_path / "OneDrive" / "Desktop"


def test_desktop_on_windows_falls_back_when_windows_says_no(monkeypatch):
    def broken():
        raise OSError("no known folder")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(automation, "_windows_desktop", broken)
    assert desktop_dir() == Path.home() / "Desktop"


def test_folders_default_to_the_desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "desktop_dir", lambda: tmp_path / "Desktop")
    db_file = tmp_path / "petrom.db"
    init_db(db_file)

    with open_db(db_file) as conn:
        folders = get_folders(conn)

    assert folders == Folders(
        noi=tmp_path / "Desktop" / "Facturi-noi",
        procesate=tmp_path / "Desktop" / "Facturi-procesate",
        erori=tmp_path / "Desktop" / "Facturi-erori",
    )


def test_folders_come_from_settings_when_set(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    with open_db(db_file) as conn:
        conn.execute("INSERT INTO setari VALUES ('folder_noi', ?)", (str(tmp_path / "A"),))
        conn.execute("INSERT INTO setari VALUES ('folder_procesate', ?)", (str(tmp_path / "B"),))
        conn.execute("INSERT INTO setari VALUES ('folder_erori', ?)", (str(tmp_path / "E"),))
        folders = get_folders(conn)

    assert folders == Folders(tmp_path / "A", tmp_path / "B", tmp_path / "E")


# ---------- the summary text ----------


def summary(total, adaugate=0, erori=0, mutate=0):
    s = RunSummary()
    s.total = total
    s.adaugate = [f"a{i}.pdf" for i in range(adaugate)]
    s.erori = [(f"e{i}.pdf", "motiv") for i in range(erori)]
    s.mutate = [f"m{i}.pdf" for i in range(mutate)]
    return s


def test_summary_message_plural():
    assert summary(10, 9, 1).mesaj() == "10 PDF-uri: 9 adăugate, 1 eroare"


def test_summary_message_singular():
    assert summary(1, 1, 0).mesaj() == "1 PDF: 1 adăugată, 0 erori"


def test_summary_message_uses_de_from_20():
    assert summary(20, 20, 0).mesaj() == "20 de PDF-uri: 20 de adăugate, 0 erori"
    assert summary(102, 101, 1).mesaj() == "102 PDF-uri: 101 adăugate, 1 eroare"


def test_summary_message_mentions_tidied_files():
    assert summary(2, 1, 0, 1).mesaj() == "2 PDF-uri: 1 adăugată, 0 erori, 1 mutată (salvată deja)"


def test_summary_message_when_folder_is_empty():
    assert summary(0).mesaj() == "Niciun PDF nou în Facturi-noi."


# ---------- whole runs on a fake folder ----------


@pytest.fixture()
def setup(tmp_path):
    """A fresh database plus the three folders, all inside tmp_path."""
    db_file = tmp_path / "data" / "petrom.db"
    init_db(db_file)
    folders = Folders(tmp_path / "noi", tmp_path / "procesate", tmp_path / "erori")
    folders.noi.mkdir()

    def run():
        return run_automation(db_file, folders, tmp_path / "data")

    return db_file, folders, run


def rows(db_file, sql, params=()):
    conn = connect(db_file)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def test_run_saves_a_good_invoice_and_moves_it_to_its_month(setup):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "factura.pdf", total="1.234,56", data="05.06.2026")

    result = run()

    assert result.adaugate == ["factura.pdf"]
    assert result.erori == []
    assert (folders.procesate / "2026-06" / "factura.pdf").exists()
    assert not (folders.noi / "factura.pdf").exists()
    [factura] = rows(db_file, "SELECT * FROM facturi")
    assert factura["total_bani"] == 123456
    assert factura["data_factura"] == "2026-06-05"
    assert factura["numar"] == "109000000000001"
    assert factura["fisier"] == "factura.pdf"
    assert factura["mutat"] == 1


def test_run_creates_an_unknown_company_without_a_max(setup):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf", cui="22222226", nume="NOUA SRL")

    run()

    [firma] = rows(db_file, "SELECT * FROM firme")
    assert (firma["cui"], firma["nume"], firma["arhivat"]) == ("22222226", "NOUA SRL", 0)
    assert rows(db_file, "SELECT * FROM limite") == []


def test_run_uses_an_existing_company(setup):
    db_file, folders, run = setup
    with open_db(db_file) as conn:
        conn.execute(
            "INSERT INTO firme (id, cui, nume) VALUES (7, ?, 'NUME VECHI')", (FAKE_BUYER_CUI,)
        )
    make_invoice_pdf(folders.noi / "f.pdf", nume="NUME NOU")

    run()

    assert rows(db_file, "SELECT id, nume FROM firme") == [{"id": 7, "nume": "NUME VECHI"}]
    assert rows(db_file, "SELECT firma_id FROM facturi") == [{"firma_id": 7}]


def test_run_restores_an_archived_company(setup):
    db_file, folders, run = setup
    with open_db(db_file) as conn:
        conn.execute(
            "INSERT INTO firme (cui, nume, arhivat) VALUES (?, 'ARHIVATA SRL', 1)",
            (FAKE_BUYER_CUI,),
        )
    make_invoice_pdf(folders.noi / "f.pdf")

    result = run()

    assert rows(db_file, "SELECT arhivat FROM firme") == [{"arhivat": 0}]
    assert any("ARHIVATA SRL" in note and "restaurat" in note for note in result.note)


def test_run_sends_a_damaged_pdf_to_errors_with_its_reason(setup):
    db_file, folders, run = setup
    (folders.noi / "stricat.pdf").write_bytes(b"this is not a pdf")

    result = run()

    assert result.erori == [("stricat.pdf", PDF_DAMAGED)]
    assert (folders.erori / "stricat.pdf").exists()
    assert rows(db_file, "SELECT * FROM facturi") == []
    motive = (folders.erori / "motive.txt").read_text(encoding="utf-8-sig")
    assert "stricat.pdf" in motive and PDF_DAMAGED in motive


def test_run_refuses_the_same_file_twice(setup):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf")
    original = folders.noi / "f.pdf"
    content = original.read_bytes()
    run()

    (folders.noi / "copie.pdf").write_bytes(content)
    result = run()

    assert result.erori == [("copie.pdf", ALREADY_PROCESSED)]
    assert (folders.erori / "copie.pdf").exists()
    assert len(rows(db_file, "SELECT * FROM facturi")) == 1


def test_run_refuses_a_different_file_with_the_same_invoice_number(setup):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf", numar="109063201010976")
    run()

    make_invoice_pdf(folders.noi / "alta.pdf", numar="109063201010976", total="5.00")
    result = run()

    assert result.erori == [("alta.pdf", ALREADY_PROCESSED)]
    assert len(rows(db_file, "SELECT * FROM facturi")) == 1


def test_run_adds_2_when_the_name_is_taken(setup):
    _, folders, run = setup
    (folders.procesate / "2026-06").mkdir(parents=True)
    (folders.procesate / "2026-06" / "f.pdf").write_bytes(b"older file")
    make_invoice_pdf(folders.noi / "f.pdf")

    run()

    assert (folders.procesate / "2026-06" / "f (2).pdf").exists()
    assert (folders.procesate / "2026-06" / "f.pdf").read_bytes() == b"older file"


def test_run_when_the_move_fails_keeps_the_money_and_tidies_up_next_time(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "deschis.pdf")
    real_move = automation._move

    def move_fails_for_processed(src, folder):
        if Path(folder).is_relative_to(folders.procesate):
            raise PermissionError("file is open in another program")
        return real_move(src, folder)

    monkeypatch.setattr(automation, "_move", move_fails_for_processed)
    first = run()

    assert first.adaugate == ["deschis.pdf"]
    assert any("deschis.pdf" in note and "nu am putut-o muta" in note for note in first.note)
    assert (folders.noi / "deschis.pdf").exists()
    assert rows(db_file, "SELECT mutat FROM facturi") == [{"mutat": 0}]

    monkeypatch.setattr(automation, "_move", real_move)
    second = run()

    assert second.erori == [] and second.adaugate == []
    assert second.mutate == ["deschis.pdf"]
    assert (folders.procesate / "2026-06" / "deschis.pdf").exists()
    assert rows(db_file, "SELECT mutat FROM facturi") == [{"mutat": 1}]
    assert not (folders.erori / "deschis.pdf").exists()


def test_run_only_reads_pdfs_in_the_top_folder(setup):
    _, folders, run = setup
    make_invoice_pdf(folders.noi / "MARE.PDF")
    (folders.noi / "poza.jpg").write_bytes(b"jpg")
    (folders.noi / "sub").mkdir()
    make_invoice_pdf(folders.noi / "sub" / "ascuns.pdf", numar="109000000000002")

    result = run()

    assert result.total == 1
    assert result.adaugate == ["MARE.PDF"]
    assert (folders.noi / "poza.jpg").exists()
    assert (folders.noi / "sub" / "ascuns.pdf").exists()


def test_run_creates_missing_folders(tmp_path):
    db_file = tmp_path / "data" / "petrom.db"
    init_db(db_file)
    folders = Folders(
        tmp_path / "x" / "noi", tmp_path / "x" / "procesate", tmp_path / "x" / "erori"
    )

    result = run_automation(db_file, folders, tmp_path / "data")

    assert folders.noi.is_dir() and folders.procesate.is_dir() and folders.erori.is_dir()
    assert result.total == 0


def test_run_makes_a_backup_first(setup, tmp_path):
    _, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf")
    run()
    assert len(list((tmp_path / "data" / "backups").glob("petrom-*.db"))) == 1


def test_run_skips_the_backup_when_there_are_no_pdfs(setup, tmp_path):
    _, _, run = setup
    run()
    assert list((tmp_path / "data" / "backups").glob("petrom-*.db")) == []


def test_run_stops_before_touching_files_when_the_backup_fails(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf")

    def broken_backup(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(automation, "backup_database", broken_backup)
    with pytest.raises(BackupError):
        run()

    assert (folders.noi / "f.pdf").exists()
    assert rows(db_file, "SELECT * FROM facturi") == []


def test_run_refuses_while_another_run_holds_the_lock(setup, tmp_path):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf")

    with RunLock(tmp_path / "data" / automation.LOCK_FILE_NAME):
        with pytest.raises(AlreadyRunning):
            run()

    assert (folders.noi / "f.pdf").exists()
    assert rows(db_file, "SELECT * FROM facturi") == []


def test_motive_txt_grows_one_line_per_error_with_one_bom(setup):
    _, folders, run = setup
    (folders.noi / "a.pdf").write_bytes(b"bad")
    run()
    (folders.noi / "b.pdf").write_bytes(b"bad too")
    run()

    raw = (folders.erori / "motive.txt").read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    assert raw.count(codecs.BOM_UTF8) == 1
    lines = raw.decode("utf-8-sig").splitlines()
    assert len(lines) == 2
    assert "a.pdf" in lines[0] and "b.pdf" in lines[1]


def test_motive_txt_uses_the_final_name_after_a_clash(setup):
    _, folders, run = setup
    folders.erori.mkdir()
    (folders.erori / "a.pdf").write_bytes(b"older")
    (folders.noi / "a.pdf").write_bytes(b"bad")

    run()

    assert (folders.erori / "a (2).pdf").exists()
    assert "a (2).pdf" in (folders.erori / "motive.txt").read_text(encoding="utf-8-sig")


def test_run_stops_when_a_folder_cannot_be_created(tmp_path):
    db_file = tmp_path / "data" / "petrom.db"
    init_db(db_file)
    (tmp_path / "blocat").write_text("a file where a folder should be")
    folders = Folders(tmp_path / "blocat" / "noi", tmp_path / "procesate", tmp_path / "erori")

    with pytest.raises(automation.RunError) as excinfo:
        run_automation(db_file, folders, tmp_path / "data")

    assert "noi" in excinfo.value.mesaj


def test_one_crashing_file_does_not_stop_the_others(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "a_crapa.pdf", numar="109000000000001")
    make_invoice_pdf(folders.noi / "b_bun.pdf", numar="109000000000002")
    real_read = automation.read_invoice

    def read_crashes_on_a(path):
        if path.name == "a_crapa.pdf":
            raise RuntimeError("bug in the reader")
        return real_read(path)

    monkeypatch.setattr(automation, "read_invoice", read_crashes_on_a)
    result = run()

    assert result.erori == [("a_crapa.pdf", automation.UNEXPECTED)]
    assert result.adaugate == ["b_bun.pdf"]
    assert (folders.noi / "a_crapa.pdf").exists()  # left in place for the next run


# ---------- review round 1 ----------


def move_fails_into(monkeypatch, blocked_folder):
    """Make every move into blocked_folder (or below it) fail, like a file open on Windows."""
    real_move = automation._move

    def move(src, folder):
        if Path(folder).is_relative_to(blocked_folder):
            raise PermissionError("file is open in another program")
        return real_move(src, folder)

    monkeypatch.setattr(automation, "_move", move)
    return real_move


def test_saved_file_that_still_cannot_be_moved_counts_as_an_error(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "deschis.pdf")
    move_fails_into(monkeypatch, folders.procesate)
    run()

    second = run()  # still open in the viewer

    assert second.erori == [("deschis.pdf", automation.STILL_NOT_MOVED)]
    assert second.mesaj() == "1 PDF: 0 adăugate, 1 eroare"
    assert (folders.noi / "deschis.pdf").exists()
    assert rows(db_file, "SELECT mutat FROM facturi") == [{"mutat": 0}]
    motive = (folders.erori / "motive.txt").read_text(encoding="utf-8-sig")
    assert "deschis.pdf" in motive and automation.STILL_NOT_MOVED in motive


def test_file_that_cannot_go_to_errors_stays_and_gets_a_reason_line(setup, monkeypatch):
    _, folders, run = setup
    (folders.noi / "stricat.pdf").write_bytes(b"bad")
    move_fails_into(monkeypatch, folders.erori)

    result = run()

    assert result.erori == [("stricat.pdf", PDF_DAMAGED)]
    assert any("stricat.pdf" in n and automation.ERRORS_MOVE_FAILED in n for n in result.note)
    assert (folders.noi / "stricat.pdf").exists()
    motive = (folders.erori / "motive.txt").read_text(encoding="utf-8-sig")
    assert "stricat.pdf" in motive and automation.ERRORS_MOVE_FAILED in motive


def test_unexpected_crash_gets_a_reason_line(setup, monkeypatch):
    _, folders, run = setup
    make_invoice_pdf(folders.noi / "crapa.pdf")

    def crash(path):
        raise RuntimeError("bug in the reader")

    monkeypatch.setattr(automation, "read_invoice", crash)
    run()

    motive = (folders.erori / "motive.txt").read_text(encoding="utf-8-sig")
    assert "crapa.pdf" in motive and automation.UNEXPECTED in motive


def test_same_number_while_the_first_is_still_not_moved_finishes_the_move(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "original.pdf", numar="109063201010976")
    real_move = move_fails_into(monkeypatch, folders.procesate)
    run()
    (folders.noi / "original.pdf").unlink()  # she deleted the stuck copy...
    make_invoice_pdf(folders.noi / "redescarcat.pdf", numar="109063201010976", total="1")
    monkeypatch.setattr(automation, "_move", real_move)  # ...and downloaded it again

    result = run()

    assert result.mutate == ["redescarcat.pdf"]
    assert result.adaugate == [] and result.erori == []
    assert (folders.procesate / "2026-06" / "redescarcat.pdf").exists()
    assert rows(db_file, "SELECT total_bani, mutat FROM facturi") == [
        {"total_bani": 19989, "mutat": 1}
    ]


def test_run_finishes_when_motive_txt_cannot_be_written(setup, caplog):
    _, folders, run = setup
    folders.erori.mkdir()
    (folders.erori / "motive.txt").mkdir()  # a folder where the file should be
    (folders.noi / "stricat.pdf").write_bytes(b"bad")

    result = run()

    assert result.erori == [("stricat.pdf", PDF_DAMAGED)]
    assert (folders.erori / "stricat.pdf").exists()
    assert any("motive.txt" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")


# ---------- /code-review round 3 ----------


def open_file_on_windows(monkeypatch, locked_path):
    """Act like Windows with locked_path open in Acrobat: it can't be renamed or deleted."""
    import os

    real_rename, real_unlink = os.rename, os.unlink

    def rename(src, dst, *args, **kwargs):
        if Path(src) == locked_path:
            raise PermissionError("used by another process")
        return real_rename(src, dst, *args, **kwargs)

    def unlink(path, *args, **kwargs):
        if Path(path) == locked_path:
            raise PermissionError("used by another process")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "rename", rename)
    monkeypatch.setattr(os, "unlink", unlink)


def test_move_of_an_open_file_leaves_no_copy_behind(tmp_path, monkeypatch):
    src = tmp_path / "deschis.pdf"
    src.write_bytes(b"pdf")
    open_file_on_windows(monkeypatch, src)

    with pytest.raises(OSError):
        automation._move(src, tmp_path / "dest")

    assert src.exists()
    assert list((tmp_path / "dest").iterdir()) == []


def test_move_to_another_drive_copies_then_deletes(tmp_path, monkeypatch):
    import errno
    import os

    src = tmp_path / "f.pdf"
    src.write_bytes(b"pdf")

    def rename_across_drives(*args, **kwargs):
        raise OSError(errno.EXDEV, "different drive")

    monkeypatch.setattr(os, "rename", rename_across_drives)
    dest = automation._move(src, tmp_path / "dest")

    assert dest.read_bytes() == b"pdf"
    assert not src.exists()


def test_move_to_another_drive_of_an_open_file_removes_the_copy(tmp_path, monkeypatch):
    import errno
    import os

    src = tmp_path / "deschis.pdf"
    src.write_bytes(b"pdf")
    open_file_on_windows(monkeypatch, src)

    def rename_across_drives(*args, **kwargs):
        raise OSError(errno.EXDEV, "different drive")

    monkeypatch.setattr(os, "rename", rename_across_drives)
    with pytest.raises(OSError):
        automation._move(src, tmp_path / "dest")

    assert src.exists()
    assert list((tmp_path / "dest").iterdir()) == []


def test_run_with_an_open_pdf_leaves_no_copy_in_processed(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "deschis.pdf")
    open_file_on_windows(monkeypatch, folders.noi / "deschis.pdf")

    result = run()

    assert result.adaugate == ["deschis.pdf"]
    assert list((folders.procesate / "2026-06").glob("*.pdf")) == []
    assert rows(db_file, "SELECT mutat FROM facturi") == [{"mutat": 0}]


def test_database_keeps_the_final_name_after_a_clash(setup):
    db_file, folders, run = setup
    (folders.procesate / "2026-06").mkdir(parents=True)
    (folders.procesate / "2026-06" / "f.pdf").write_bytes(b"older file")
    make_invoice_pdf(folders.noi / "f.pdf")

    run()

    assert rows(db_file, "SELECT fisier FROM facturi") == [{"fisier": "f (2).pdf"}]


def test_folders_ask_for_the_desktop_only_once(tmp_path, monkeypatch):
    calls = []

    def fake_desktop():
        calls.append(1)
        return tmp_path / "Desktop"

    monkeypatch.setattr(automation, "desktop_dir", fake_desktop)
    db_file = tmp_path / "petrom.db"
    init_db(db_file)

    with open_db(db_file) as conn:
        get_folders(conn)

    assert len(calls) == 1


def test_marking_failure_after_a_good_move_is_not_reported_as_an_error(setup, monkeypatch):
    db_file, folders, run = setup
    make_invoice_pdf(folders.noi / "f.pdf")

    def database_locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(automation, "_mark_moved", database_locked)
    result = run()

    assert result.adaugate == ["f.pdf"]
    assert result.erori == []
    assert (folders.procesate / "2026-06" / "f.pdf").exists()
    assert len(rows(db_file, "SELECT * FROM facturi")) == 1
    assert not (folders.erori / "motive.txt").exists()


def test_move_to_another_drive_removes_a_half_written_copy(tmp_path, monkeypatch):
    import errno
    import os
    import shutil

    src = tmp_path / "f.pdf"
    src.write_bytes(b"pdf")

    def rename_across_drives(*args, **kwargs):
        raise OSError(errno.EXDEV, "different drive")

    def copy_fails_halfway(source, dest, *args, **kwargs):
        Path(dest).write_bytes(b"pd")  # part of the file got written...
        raise OSError(errno.ENOSPC, "disk full")  # ...then the copy failed

    monkeypatch.setattr(os, "rename", rename_across_drives)
    monkeypatch.setattr(shutil, "copy2", copy_fails_halfway)
    with pytest.raises(OSError):
        automation._move(src, tmp_path / "dest")

    assert src.exists()
    assert list((tmp_path / "dest").iterdir()) == []


def test_delete_backups_and_run_backups_are_kept_apart(tmp_path):
    db_file = tmp_path / "petrom.db"
    init_db(db_file)
    backups = tmp_path / "backups"
    backups.mkdir()
    runs = [f"petrom-202001{i // 10:02d}-0000{i % 10:02d}-000000.db" for i in range(30)]
    deletes = [f"petrom-stergere-202001{i // 10:02d}-0000{i % 10:02d}-000000.db" for i in range(35)]
    for name in runs + deletes:
        (backups / name).write_bytes(b"old")

    newest = backup_database(db_file, backups, prefix="petrom-stergere")

    assert newest.name.startswith("petrom-stergere-")
    assert len(list(backups.glob("petrom-stergere-*.db"))) == 30
    assert all((backups / name).exists() for name in runs)  # run backups untouched

    newest_run = backup_database(db_file, backups)  # a run backup: must not touch deletes
    assert len(list(backups.glob("petrom-stergere-*.db"))) == 30
    # ...and the delete backups must not push out run backups: 31 runs -> newest 30 kept.
    kept_runs = sorted(p.name for p in backups.glob("petrom-[0-9]*.db"))
    assert len(kept_runs) == 30
    assert newest_run.exists()
    assert kept_runs[0] == sorted(runs)[1]  # only the oldest run backup went
