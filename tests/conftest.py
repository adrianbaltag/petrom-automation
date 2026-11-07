"""Shared test setup: every test gets its own empty data folder, never the real one."""

import logging

import pytest

from petrom_dashboard import create_app


@pytest.fixture(autouse=True)
def restore_root_logger():
    """create_app() sets up logging; put the root logger back after each test."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture()
def data_dir(tmp_path):
    return tmp_path / "PetromDashboard"


@pytest.fixture()
def app(data_dir):
    return create_app({"TESTING": True, "DATA_DIR": data_dir})


@pytest.fixture()
def client(app):
    return app.test_client()
