"""Browser tests: the app on a real local web server with a temporary data folder."""

import threading

import pytest
from werkzeug.serving import make_server

from petrom_dashboard import create_app


@pytest.fixture()
def server_app(data_dir):
    return create_app({"TESTING": True, "DATA_DIR": data_dir})


@pytest.fixture()
def live_url(server_app):
    """Serve the app on a free port of 127.0.0.1 while the test runs."""
    server = make_server("127.0.0.1", 0, server_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
