"""Tests for setup_logging. Copy this file into a project along with setup_logging.py."""

import logging

import pytest

from petrom_dashboard.setup_logging import setup_logging


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Put the root logger back after each test, so tests can't affect each other."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_writes_messages_to_the_file(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_file)
    logging.getLogger("demo").info("hello")

    assert "hello" in log_file.read_text(encoding="utf-8")


def test_line_shows_level_and_logger_name(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_file)
    logging.getLogger("demo").warning("careful")

    line = log_file.read_text(encoding="utf-8")
    assert "WARNING" in line
    assert "demo" in line


def test_also_writes_to_the_terminal(tmp_path, capsys):
    setup_logging(tmp_path / "app.log")

    logging.getLogger("demo").info("hello")

    assert "hello" in capsys.readouterr().err


def test_creates_a_missing_folder(tmp_path):
    log_file = tmp_path / "new" / "folder" / "app.log"

    setup_logging(log_file)
    logging.getLogger("demo").info("hello")

    assert log_file.exists()


def test_calling_twice_does_not_double_lines(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_file)
    setup_logging(log_file)
    logging.getLogger("demo").info("hello")

    assert log_file.read_text(encoding="utf-8").count("hello") == 1


def test_level_drops_lower_messages(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_file, level=logging.WARNING)
    logging.getLogger("demo").info("too quiet")
    logging.getLogger("demo").warning("loud enough")

    text = log_file.read_text(encoding="utf-8")
    assert "too quiet" not in text
    assert "loud enough" in text


def test_rotates_and_keeps_only_the_set_number_of_old_files(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(log_file, max_bytes=200, backup_count=2)
    for number in range(100):
        logging.getLogger("demo").info("message %d", number)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["app.log", "app.log.1", "app.log.2"]


def test_accepts_a_plain_string_path(tmp_path):
    log_file = tmp_path / "app.log"

    setup_logging(str(log_file))
    logging.getLogger("demo").info("hello")

    assert log_file.exists()
