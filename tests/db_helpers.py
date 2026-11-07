"""Test helper: open the database and always close it again.

sqlite3's own `with conn:` only commits; it never closes. On Windows an open database
file stays locked, so tests close every connection they open.
"""

from contextlib import contextmanager

from petrom_dashboard.db import connect


@contextmanager
def open_db(db_file):
    """Open the database, commit if the block succeeds, and always close it."""
    conn = connect(db_file)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
