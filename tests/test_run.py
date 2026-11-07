import errno
import socket

import pytest

import run


class FakeServer:
    def __init__(self):
        self.ran = False

    def run(self):
        self.ran = True


@pytest.fixture()
def calls(monkeypatch, tmp_path):
    """Fake server, browser and port check, so main() never touches the real port 8765."""
    monkeypatch.setenv("PETROM_DATA_DIR", str(tmp_path))
    recorded = {"server": FakeServer()}

    def fake_create_server(app, host, port):
        recorded.update(host=host, port=port)
        return recorded["server"]

    monkeypatch.setattr(run, "create_server", fake_create_server)
    monkeypatch.setattr(run, "open_browser_later", lambda url: recorded.update(url=url))
    monkeypatch.setattr(run, "port_is_busy", lambda host, port: False)
    return recorded


def log_text(tmp_path):
    return (tmp_path / "logs" / "petrom.log").read_text(encoding="utf-8")


def test_server_listens_only_on_this_computer(calls):
    exit_code = run.main()

    assert exit_code == 0
    assert calls["host"] == "127.0.0.1"
    assert calls["url"] == f"http://127.0.0.1:{calls['port']}/"
    assert calls["server"].ran


def test_port_in_use_is_logged_and_browser_stays_closed(monkeypatch, tmp_path, calls):
    def port_taken(app, host, port):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(run, "create_server", port_taken)

    exit_code = run.main()

    assert exit_code == 1
    assert "url" not in calls
    assert "8765" in log_text(tmp_path)
    assert "ERROR" in log_text(tmp_path)


def test_running_copy_detected_before_server_starts(monkeypatch, tmp_path, calls):
    """Windows lets a second server share a busy port, so main() must check first."""
    monkeypatch.setattr(run, "port_is_busy", lambda host, port: True)

    exit_code = run.main()

    assert exit_code == 1
    assert "host" not in calls  # create_server was never called
    assert "url" not in calls
    assert "ERROR" in log_text(tmp_path)


def test_port_is_busy_when_something_listens():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))  # 0 = let the system pick a free port
        listener.listen()
        port = listener.getsockname()[1]

        assert run.port_is_busy("127.0.0.1", port)


def test_port_is_free_when_nothing_listens():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # the socket is closed now, so nothing listens on that port

    assert not run.port_is_busy("127.0.0.1", port)
