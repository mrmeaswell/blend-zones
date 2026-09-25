"""SQLite access layer.

Deliberately no ORM: db/schema.sql is the source of truth for the data
model, which is what makes this template forkable by editing SQL + JSON
rather than Python classes.
"""

import sqlite3
from contextlib import contextmanager

from . import config


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def tx():
    """Transactional connection: commits on success, rolls back on error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def ro():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Idempotent: applies schema.sql, then seed.sql if the DB is empty."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with tx() as conn:
        conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))

        # Keep the stages table in sync with config/workflow.json so the
        # two can't drift apart.
        for idx, stage in enumerate(config.stages(), start=1):
            conn.execute(
                """
                INSERT INTO stages (stage_key, label, short, sort_order, is_terminal)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stage_key) DO UPDATE SET
                    label=excluded.label,
                    short=excluded.short,
                    sort_order=excluded.sort_order,
                    is_terminal=excluded.is_terminal
                """,
                (
                    stage["key"],
                    stage["label"],
                    stage.get("short", stage["key"][:3].upper()),
                    idx,
                    1 if stage.get("terminal") else 0,
                ),
            )

        empty = conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"] == 0
        if empty and config.SEED_PATH.exists():
            conn.executescript(config.SEED_PATH.read_text(encoding="utf-8"))


def next_ticket_id(conn: sqlite3.Connection) -> str:
    wf = config.workflow()
    prefix = wf.get("ticket_prefix", "T-")
    start = int(wf.get("ticket_start", 1001))
    row = conn.execute(
        """
        SELECT MAX(CAST(SUBSTR(ticket_id, ?) AS INTEGER)) AS mx
        FROM tickets WHERE ticket_id LIKE ?
        """,
        (len(prefix) + 1, f"{prefix}%"),
    ).fetchone()
    current = row["mx"] if row and row["mx"] is not None else start - 1
    return f"{prefix}{max(current + 1, start)}"
