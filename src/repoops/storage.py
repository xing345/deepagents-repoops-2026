from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(database_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a short-lived SQLite connection with sane concurrency defaults.

    ``sqlite3.Connection`` used as a context manager only commits or rolls
    back; it never closes the handle.  Wrapping it here guarantees the file
    descriptor is released, which matters on Windows where an open handle
    keeps the database file locked.

    WAL plus a busy timeout keep short parallel reads from failing with
    ``database is locked``; the timeout is a bounded wait rather than a retry
    loop, so callers still see errors when a writer holds the lock too long.
    """

    connection = sqlite3.connect(database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        with connection:
            yield connection
    finally:
        connection.close()