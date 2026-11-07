"""Start the dashboard: the launchers (start.bat / start.command) run this file.

It starts the web server on this computer only, then opens the dashboard in the browser.
"""

import logging
import socket
import sys
import threading
import webbrowser

from waitress.server import create_server

from petrom_dashboard import create_app

HOST = "127.0.0.1"  # this computer only: nobody else on the Wi-Fi can open the dashboard
PORT = 8765

logger = logging.getLogger(__name__)

ALREADY_RUNNING_MESSAGE = (
    "Dashboard-ul nu a putut porni: portul %s este ocupat. "
    "Probabil rulează deja: verifică browserul sau închide cealaltă fereastră."
)


def port_is_busy(host, port):
    """Knock on the port: True if something already answers there.

    Needed because on Windows the server can quietly share a busy port instead of failing.
    """
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:  # refused or timed out: nothing is listening
        return False


def open_browser_later(url):
    """Open the browser one second from now, once the server is ready to answer."""
    threading.Timer(1.0, webbrowser.open, args=[url]).start()


def main():
    """Start the server. Returns 0 when it stops normally, 1 if it could not start."""
    app = create_app()
    url = f"http://{HOST}:{PORT}/"
    if port_is_busy(HOST, PORT):
        logger.error("Could not start: something already listens on port %s", PORT)
        logger.error(ALREADY_RUNNING_MESSAGE, PORT)
        return 1
    try:
        # Backup check: create_server claims the port now, so a busy port fails here on Mac.
        server = create_server(app, host=HOST, port=PORT)
    except OSError:
        logger.exception("Could not start the server on port %s (already in use?)", PORT)
        logger.error(ALREADY_RUNNING_MESSAGE, PORT)
        return 1
    logger.info("Dashboard running at %s", url)
    open_browser_later(url)
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
