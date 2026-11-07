"""The Setări logic (M7): folder checks and saving, manual backup, opening folders."""

import os
from pathlib import Path

import pytest
from db_helpers import open_db

from petrom_dashboard import automation, setari
from petrom_dashboard.db import init_db


@pytest.fixture()
def db_file(tmp_path):
    path = tmp_path / "petrom.db"
    init_db(path)
    return path


@pytest.fixture()
def desktop(tmp_path, monkeypatch):
    """A fake Desktop, so no test ever touches the real one."""
    path = tmp_path / "Desktop"
    monkeypatch.setattr(automation, "desktop_dir", lambda: path)
    return path


@pytest.fixture()
def app_dir(tmp_path):
    path = tmp_path / "app"
    path.mkdir()
    return path


def boxes(base, noi="A", procesate="B", erori="E"):
    return {"noi": str(base / noi), "procesate": str(base / procesate), "erori": str(base / erori)}


def by_key(results):
    return {r.cheie: r for r in results}


# --- clean_path ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "clean"),
    [
        ('"C:\\Users\\Ana\\Facturi"', "C:\\Users\\Ana\\Facturi"),  # Windows "Copy as path"
        ("'C:\\Users\\Ana\\Facturi'", "C:\\Users\\Ana\\Facturi"),
        ('  "C:\\Facturi"  ', "C:\\Facturi"),
        ("  /Users/ana/Facturi \n", "/Users/ana/Facturi"),
        ('"', '"'),  # a lone quote is not a pair: left for the checks to refuse
        ("", ""),
    ],
)
def test_clean_path_strips_spaces_and_one_pair_of_quotes(typed, clean):
    assert setari.clean_path(typed) == clean


# --- check_folders ---------------------------------------------------------------------


def test_existing_writable_folders_pass_and_noi_counts_its_pdfs(tmp_path, app_dir):
    for name in ("A", "B", "E"):
        (tmp_path / name).mkdir()
    (tmp_path / "A" / "f1.pdf").write_bytes(b"%PDF")
    (tmp_path / "A" / "F2.PDF").write_bytes(b"%PDF")
    (tmp_path / "A" / "note.txt").write_text("x")
    (tmp_path / "A" / "sub").mkdir()
    (tmp_path / "A" / "sub" / "old.pdf").write_bytes(b"%PDF")  # subfolders are not read

    results = by_key(setari.check_folders(boxes(tmp_path), app_dir))

    assert all(r.ok for r in results.values())
    assert results["noi"].mesaj == "Există · 2 PDF-uri de citit."
    assert results["procesate"].mesaj == "Există."
    assert results["noi"].exista is True


def test_missing_folder_passes_and_says_it_will_be_created(tmp_path, app_dir):
    results = by_key(setari.check_folders(boxes(tmp_path, noi="nou/A"), app_dir))

    assert results["noi"].ok is True
    assert results["noi"].exista is False
    assert results["noi"].mesaj == "Nu există încă: îl creez când apeși Salvează."
    assert not (tmp_path / "nou").exists()  # checking never creates anything


def test_check_returns_the_cleaned_path(tmp_path, app_dir):
    typed = boxes(tmp_path)
    typed["noi"] = f'  "{tmp_path / "A"}" '

    results = by_key(setari.check_folders(typed, app_dir))

    assert results["noi"].cale == str(tmp_path / "A")


def test_empty_box_is_refused(tmp_path, app_dir):
    typed = boxes(tmp_path)
    typed["erori"] = '  ""  '

    result = by_key(setari.check_folders(typed, app_dir))["erori"]

    assert (result.ok, result.mesaj) == (False, "Scrie calea folderului.")


def test_relative_path_is_refused(tmp_path, app_dir):
    typed = boxes(tmp_path)
    typed["noi"] = "Facturi-noi"

    result = by_key(setari.check_folders(typed, app_dir))["noi"]

    assert result.ok is False
    assert result.mesaj.startswith("Scrie calea completă")


@pytest.mark.parametrize("bad", ["<", ">", '"', "|", "?", "*"])
def test_characters_windows_refuses_are_refused(tmp_path, app_dir, bad):
    typed = boxes(tmp_path)
    typed["noi"] = str(tmp_path / f"Fac{bad}turi")

    result = by_key(setari.check_folders(typed, app_dir))["noi"]

    assert result.ok is False
    assert "caractere nepermise" in result.mesaj


def test_a_file_in_place_of_the_folder_is_refused(tmp_path, app_dir):
    (tmp_path / "A").write_text("not a folder")

    result = by_key(setari.check_folders(boxes(tmp_path), app_dir))["noi"]

    assert (result.ok, result.mesaj) == (False, "Aici e un fișier, nu un folder.")


def test_a_file_on_the_way_to_a_missing_folder_is_refused(tmp_path, app_dir):
    (tmp_path / "A").write_text("not a folder")

    result = by_key(setari.check_folders(boxes(tmp_path, noi="A/sub"), app_dir))["noi"]

    assert result.ok is False
    assert result.mesaj == "Nu pot crea folderul aici: o parte din cale e un fișier."


def test_missing_drive_is_refused(tmp_path, app_dir, monkeypatch):
    # No part of the path exists, as with a disk letter that isn't plugged in (D:\ on Windows).
    monkeypatch.setattr(setari, "_nearest_existing", lambda path: None)

    result = by_key(setari.check_folders(boxes(tmp_path), app_dir))["noi"]

    assert result.ok is False
    assert result.mesaj == "Nu găsesc discul sau folderul de început al căii."


def test_folder_the_app_cannot_write_in_is_refused(tmp_path, app_dir, monkeypatch):
    for name in ("A", "B", "E"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(setari, "_can_write", lambda folder: folder != tmp_path / "B")

    results = by_key(setari.check_folders(boxes(tmp_path), app_dir))

    assert results["procesate"].ok is False
    assert results["procesate"].mesaj == "Nu am voie să scriu în acest folder."
    assert results["noi"].ok is True


def test_can_write_really_writes_and_cleans_up(tmp_path):
    assert setari._can_write(tmp_path) is True
    assert list(tmp_path.iterdir()) == []


def test_two_boxes_on_the_same_folder_are_both_refused(tmp_path, app_dir):
    typed = boxes(tmp_path, procesate="A")
    typed["procesate"] = str(tmp_path / "x" / ".." / "A") + os.sep  # same folder, written oddly

    results = by_key(setari.check_folders(typed, app_dir))

    assert results["noi"].ok is False
    assert results["noi"].mesaj == "Același folder ca Facturi-procesate."
    assert results["procesate"].mesaj == "Același folder ca Facturi-noi."
    assert results["erori"].ok is True


def test_same_folder_comparison_ignores_case_on_windows(monkeypatch):
    monkeypatch.setattr(setari.os.path, "normcase", lambda p: p.lower())

    assert setari._same_key("/X/Facturi") == setari._same_key("/x/FACTURI")


def test_folder_inside_the_app_folder_is_refused(tmp_path, app_dir):
    typed = boxes(tmp_path)
    typed["erori"] = str(app_dir / "Facturi-erori")
    typed["procesate"] = str(app_dir)

    results = by_key(setari.check_folders(typed, app_dir))

    for key in ("erori", "procesate"):
        assert results[key].ok is False
        assert "folderul aplicației" in results[key].mesaj


def test_a_folder_next_to_the_app_with_a_longer_name_is_fine(tmp_path, app_dir):
    typed = boxes(tmp_path)
    typed["noi"] = str(tmp_path / "app-facturi")  # starts with "app" but is not inside it

    assert by_key(setari.check_folders(typed, app_dir))["noi"].ok is True


def test_nesting_among_the_three_is_allowed(tmp_path, app_dir):
    typed = boxes(tmp_path, procesate="A/procesate")

    assert all(r.ok for r in setari.check_folders(typed, app_dir))


# --- save_folders / reset_folders ------------------------------------------------------


def saved_rows(db_file):
    with open_db(db_file) as conn:
        return dict(conn.execute("SELECT cheie, valoare FROM setari").fetchall())


def test_save_creates_missing_folders_and_stores_the_paths(db_file, tmp_path, app_dir, desktop):
    (tmp_path / "A").mkdir()

    with open_db(db_file) as conn:
        result = setari.save_folders(conn, boxes(tmp_path, procesate="nou/B"), app_dir)

    assert (tmp_path / "nou" / "B").is_dir() and (tmp_path / "E").is_dir()
    assert result.mesaj == "Folderele au fost salvate."
    assert result.note == [
        f"Am creat folderul {tmp_path / 'nou' / 'B'}.",
        f"Am creat folderul {tmp_path / 'E'}.",
    ]
    assert saved_rows(db_file) == {
        "folder_noi": str(tmp_path / "A"),
        "folder_procesate": str(tmp_path / "nou" / "B"),
        "folder_erori": str(tmp_path / "E"),
    }
    with open_db(db_file) as conn:
        assert automation.get_folders(conn) == automation.Folders(
            tmp_path / "A", tmp_path / "nou" / "B", tmp_path / "E"
        )


def test_save_stores_the_cleaned_path(db_file, tmp_path, app_dir, desktop):
    typed = boxes(tmp_path)
    typed["noi"] = f' "{tmp_path / "A"}" '

    with open_db(db_file) as conn:
        setari.save_folders(conn, typed, app_dir)

    assert saved_rows(db_file)["folder_noi"] == str(tmp_path / "A")


def test_save_with_a_bad_box_saves_and_creates_nothing(db_file, tmp_path, app_dir, desktop):
    typed = boxes(tmp_path)
    typed["erori"] = "relativ"

    with open_db(db_file) as conn, pytest.raises(setari.SetariError) as err:
        setari.save_folders(conn, typed, app_dir)

    assert err.value.mesaj == "Nu am salvat nimic. Corectează folderele marcate cu ✗."
    assert by_key(err.value.rezultate)["erori"].ok is False
    assert by_key(err.value.rezultate)["noi"].ok is True
    assert saved_rows(db_file) == {}
    assert not (tmp_path / "A").exists()


def test_save_when_creating_a_folder_fails_saves_nothing(
    db_file, tmp_path, app_dir, desktop, monkeypatch
):
    real_mkdir = Path.mkdir

    def mkdir(self, *args, **kwargs):
        if self.name == "E":
            raise PermissionError("denied")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)

    with open_db(db_file) as conn, pytest.raises(setari.SetariError) as err:
        setari.save_folders(conn, boxes(tmp_path), app_dir)

    result = by_key(err.value.rezultate)["erori"]
    assert (result.ok, result.mesaj) == (False, "Nu am putut crea folderul.")
    assert saved_rows(db_file) == {}


def test_save_warns_when_the_old_noi_still_holds_pdfs(db_file, tmp_path, app_dir, desktop):
    old_noi = desktop / "Facturi-noi"
    old_noi.mkdir(parents=True)
    for name in ("a.pdf", "b.pdf", "c.PDF"):
        (old_noi / name).write_bytes(b"%PDF")

    with open_db(db_file) as conn:
        result = setari.save_folders(conn, boxes(tmp_path), app_dir)

    assert result.avertizari == [
        f"În vechiul folder {old_noi} au rămas 3 PDF-uri. Mută-le în folderul nou ca să fie citite."
    ]
    assert not any("vechiul folder" in note for note in result.note)


def test_save_does_not_warn_when_noi_stays_the_same(db_file, tmp_path, app_dir, desktop):
    old_noi = desktop / "Facturi-noi"
    old_noi.mkdir(parents=True)
    (old_noi / "a.pdf").write_bytes(b"%PDF")
    typed = boxes(tmp_path)
    typed["noi"] = str(old_noi)

    with open_db(db_file) as conn:
        result = setari.save_folders(conn, typed, app_dir)

    assert result.avertizari == []


def test_save_moves_no_files(db_file, tmp_path, app_dir, desktop):
    old_noi = desktop / "Facturi-noi"
    old_noi.mkdir(parents=True)
    (old_noi / "a.pdf").write_bytes(b"%PDF")

    with open_db(db_file) as conn:
        setari.save_folders(conn, boxes(tmp_path), app_dir)

    assert (old_noi / "a.pdf").exists()
    assert list((tmp_path / "A").iterdir()) == []


def test_reset_goes_back_to_the_desktop_and_warns_about_left_pdfs(
    db_file, tmp_path, app_dir, desktop
):
    with open_db(db_file) as conn:
        setari.save_folders(conn, boxes(tmp_path), app_dir)
    (tmp_path / "A" / "a.pdf").write_bytes(b"%PDF")

    with open_db(db_file) as conn:
        result = setari.reset_folders(conn)
        folders = automation.get_folders(conn)

    assert saved_rows(db_file) == {}
    assert folders.noi == desktop / "Facturi-noi"
    assert result.mesaj == "Folderele sunt din nou cele de pe Desktop."
    assert result.note == []
    assert result.avertizari == [
        f"În vechiul folder {tmp_path / 'A'} a rămas 1 PDF. Mută-l în folderul nou ca să fie citit."
    ]


def test_reset_keeps_other_settings(db_file, desktop):
    with open_db(db_file) as conn:
        conn.execute("INSERT INTO setari VALUES ('folder_noi', '/x')")
        conn.execute("INSERT INTO setari VALUES ('alta', 'y')")
        setari.reset_folders(conn)

    assert saved_rows(db_file) == {"alta": "y"}


# --- backups ---------------------------------------------------------------------------


def test_manual_backup_has_its_own_group(db_file, tmp_path):
    backups = tmp_path / "backups"
    for _ in range(3):
        automation.backup_database(db_file, backups)

    target = setari.manual_backup(db_file, backups)

    assert target.name.startswith("petrom-manual-2")
    assert len(list(backups.glob("petrom-[0-9]*.db"))) == 3  # run backups untouched


def test_manual_backups_keep_the_newest_30(db_file, tmp_path):
    backups = tmp_path / "backups"
    for _ in range(32):
        setari.manual_backup(db_file, backups)

    assert len(list(backups.glob("petrom-manual-*.db"))) == 30


def test_backup_summary_with_no_backups(tmp_path):
    assert setari.backup_summary(tmp_path / "backups") == "Încă nu există niciun backup."


def test_backup_summary_shows_the_newest_of_every_group_and_the_count(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    for name in (
        "petrom-20261105-090000-000001.db",
        "petrom-stergere-20261107-143210-000001.db",
        "petrom-manual-20261106-120000-000001.db",
    ):
        (backups / name).write_bytes(b"x")
    (backups / "notite.txt").write_text("not a backup")

    assert setari.backup_summary(backups) == "Ultimul backup: 07.11.2026 14:32 · 3 copii"


def test_backup_summary_uses_romanian_de_from_20(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    for i in range(20):
        (backups / f"petrom-20261105-0900{i:02d}-000001.db").write_bytes(b"x")

    assert setari.backup_summary(backups).endswith("· 20 de copii")


# --- opening folders -------------------------------------------------------------------


@pytest.fixture()
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(setari, "open_in_file_manager", calls.append)
    return calls


def test_open_a_saved_folder_creates_it_first(db_file, tmp_path, desktop, opened):
    with open_db(db_file) as conn:
        conn.execute("INSERT INTO setari VALUES ('folder_erori', ?)", (str(tmp_path / "E"),))
        setari.open_folder(conn, "erori", tmp_path / "data")

    assert opened == [tmp_path / "E"]
    assert (tmp_path / "E").is_dir()


def test_open_a_desktop_default_folder(db_file, tmp_path, desktop, opened):
    with open_db(db_file) as conn:
        setari.open_folder(conn, "noi", tmp_path / "data")

    assert opened == [desktop / "Facturi-noi"]


def test_open_backup_and_data_folders(db_file, tmp_path, desktop, opened):
    data = tmp_path / "data"
    with open_db(db_file) as conn:
        setari.open_folder(conn, "backup", data)
        setari.open_folder(conn, "date", data)

    assert opened == [data / "backups", data]
    assert (data / "backups").is_dir()


def test_open_an_unknown_name_is_refused(db_file, tmp_path, opened):
    with open_db(db_file) as conn, pytest.raises(KeyError):
        setari.open_folder(conn, "../../Windows", tmp_path)

    assert opened == []


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("darwin", ["open"]), ("linux", ["xdg-open"])],
)
def test_open_in_file_manager_uses_the_system_tool(monkeypatch, tmp_path, platform, expected):
    calls = []
    monkeypatch.setattr(setari.sys, "platform", platform)
    monkeypatch.setattr(setari.subprocess, "Popen", lambda args: calls.append(args))

    setari.open_in_file_manager(tmp_path)

    assert calls == [[*expected, str(tmp_path)]]


def test_open_in_file_manager_on_windows_uses_startfile(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(setari.sys, "platform", "win32")
    monkeypatch.setattr(setari.os, "startfile", calls.append, raising=False)

    setari.open_in_file_manager(tmp_path)

    assert calls == [str(tmp_path)]


# --- review round 1 -------------------------------------------------------------------


def test_a_link_into_the_app_folder_is_refused(tmp_path, app_dir):
    # A mapped drive, junction or symlink must not hide that the folder is inside the app.
    link = tmp_path / "scurtatura"
    link.symlink_to(app_dir, target_is_directory=True)
    typed = boxes(tmp_path)
    typed["procesate"] = str(link / "Facturi-procesate")

    result = by_key(setari.check_folders(typed, app_dir))["procesate"]

    assert result.ok is False
    assert "folderul aplicației" in result.mesaj


def test_an_app_folder_reached_through_a_link_still_guards(tmp_path, app_dir):
    link = tmp_path / "scurtatura"
    link.symlink_to(app_dir, target_is_directory=True)
    typed = boxes(tmp_path)
    typed["erori"] = str(app_dir / "Facturi-erori")

    result = by_key(setari.check_folders(typed, link))["erori"]

    assert result.ok is False


def test_two_boxes_on_one_folder_through_a_link_are_refused(tmp_path, app_dir):
    (tmp_path / "A").mkdir()
    (tmp_path / "scurtatura").symlink_to(tmp_path / "A", target_is_directory=True)
    typed = boxes(tmp_path)
    typed["procesate"] = str(tmp_path / "scurtatura")

    result = by_key(setari.check_folders(typed, app_dir))["procesate"]

    assert result.mesaj == "Același folder ca Facturi-noi."


def test_missing_folder_under_a_parent_the_app_cannot_create_in_is_refused(
    tmp_path, app_dir, monkeypatch
):
    (tmp_path / "blocat").mkdir()
    monkeypatch.setattr(setari, "_can_create_folder", lambda parent: parent != tmp_path / "blocat")

    results = by_key(setari.check_folders(boxes(tmp_path, noi="blocat/A"), app_dir))

    assert results["noi"].ok is False
    assert results["noi"].mesaj == "Nu am voie să creez un folder aici."
    assert results["procesate"].ok is True


def test_can_create_folder_really_tries_and_cleans_up(tmp_path):
    assert setari._can_create_folder(tmp_path) is True
    assert list(tmp_path.iterdir()) == []


def test_an_unreadable_path_is_refused_and_logged(tmp_path, app_dir, monkeypatch, caplog):
    real_is_dir = Path.is_dir

    def is_dir(self):
        if self == tmp_path / "A":
            raise PermissionError("network share offline")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    result = by_key(setari.check_folders(boxes(tmp_path), app_dir))["noi"]

    assert (result.ok, result.mesaj) == (False, "Nu pot citi această cale.")
    assert "Could not check folder path" in caplog.text


def test_pdfs_that_cannot_be_counted_still_say_it_exists(tmp_path, app_dir, monkeypatch, caplog):
    (tmp_path / "A").mkdir()

    def broken(folder):
        raise PermissionError("denied")

    monkeypatch.setattr(setari, "_count_pdfs", broken)

    result = by_key(setari.check_folders(boxes(tmp_path), app_dir))["noi"]

    assert (result.ok, result.mesaj) == (True, "Există.")
    assert "Could not count the PDFs" in caplog.text


def test_left_pdfs_that_cannot_be_counted_give_no_warning_and_are_logged(
    db_file, tmp_path, app_dir, desktop, monkeypatch, caplog
):
    (desktop / "Facturi-noi").mkdir(parents=True)

    def broken(folder):
        raise PermissionError("denied")

    monkeypatch.setattr(setari, "_count_pdfs", broken)

    with open_db(db_file) as conn:
        result = setari.save_folders(conn, boxes(tmp_path), app_dir)

    assert result.avertizari == []
    assert "Could not count the PDFs left in" in caplog.text


def test_backup_summary_skips_names_with_impossible_dates(tmp_path, caplog):
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "petrom-20261105-090000-000001.db").write_bytes(b"x")
    (backups / "petrom-20261340-250000-1.db").write_bytes(b"x")  # month 13, hour 25

    assert setari.backup_summary(backups) == "Ultimul backup: 05.11.2026 09:00 · 1 copie"
    assert "petrom-20261340-250000-1.db" in caplog.text


def test_backup_summary_when_the_folder_cannot_be_read(tmp_path, monkeypatch, caplog):
    backups = tmp_path / "backups"
    backups.mkdir()
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == backups:
            raise PermissionError("denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)

    assert setari.backup_summary(backups) == (
        "Nu am putut citi lista copiilor de siguranță (detalii în jurnal)."
    )
    assert "Could not read the backup folder" in caplog.text


# --- review round 2: an offline network share makes realpath raise on Windows ----------


@pytest.fixture()
def dead_share(monkeypatch):
    """realpath raises for any path containing "retea-moarta", as Windows does for some
    offline network shares (e.g. error 64, network name no longer available)."""
    real = os.path.realpath

    def realpath(path, *args, **kwargs):
        if "retea-moarta" in str(path):
            raise OSError(64, "The specified network name is no longer available")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(setari.os.path, "realpath", realpath)


def test_check_survives_a_path_realpath_cannot_follow(tmp_path, app_dir, dead_share, caplog):
    typed = boxes(tmp_path, erori="retea-moarta/E")

    results = by_key(setari.check_folders(typed, app_dir))

    assert results["noi"].ok is True
    assert "Could not follow links in" in caplog.text


def test_save_works_when_the_old_noi_is_on_a_dead_share(db_file, tmp_path, app_dir, dead_share):
    with open_db(db_file) as conn:
        conn.execute(
            "INSERT INTO setari VALUES ('folder_noi', ?)", (str(tmp_path / "retea-moarta"),)
        )
        result = setari.save_folders(conn, boxes(tmp_path), app_dir)

    assert result.mesaj == "Folderele au fost salvate."
    assert saved_rows(db_file)["folder_noi"] == str(tmp_path / "A")


def test_reset_works_when_the_old_noi_is_on_a_dead_share(db_file, tmp_path, desktop, dead_share):
    with open_db(db_file) as conn:
        conn.execute(
            "INSERT INTO setari VALUES ('folder_noi', ?)", (str(tmp_path / "retea-moarta"),)
        )
        result = setari.reset_folders(conn)

    assert result.mesaj == "Folderele sunt din nou cele de pe Desktop."
    assert saved_rows(db_file) == {}
