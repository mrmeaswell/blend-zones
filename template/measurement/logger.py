"""
Measurement logging — plain sqlite3, no ORM, matching the rest of the
blend-zone template's dependency-light approach. Import log_event() at
the point in your own tool's code where an action succeeds or fails
(a ticket stage change, an LTI launch, a generation call); import
log_manual_entry() from the /measurement/log form handler.

Template version: see VERSION in this folder. When forking this module
into a new tool, copy VERSION unchanged so drift from the canonical
blend-zone-template/measurement/ source is always visible.
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: str) -> None:
    """Create the measurement tables if they don't exist yet. Safe to call
    every app startup — CREATE TABLE IF NOT EXISTS is idempotent. If your
    tool already has its own SQLite file (e.g. Bay Log's schema.sql),
    point db_path at that same file rather than creating a second one."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


@contextmanager
def timed_call():
    """Usage:
        with timed_call() as t:
            result = do_the_actual_work()
        log_event(db_path, "bay-log", "lti_launch", success=True, latency_ms=t.ms)
    """
    class _Timer:
        ms = None
    t = _Timer()
    start = time.monotonic()
    try:
        yield t
    finally:
        t.ms = int((time.monotonic() - start) * 1000)


def log_event(db_path: str, tool_name: str, action: str, success: bool,
              backend: str | None = None, latency_ms: int | None = None,
              error_type: str | None = None) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO measurement_events (tool_name, action, backend, success, latency_ms, error_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tool_name, action, backend, 1 if success else 0, latency_ms, error_type),
        )


def log_manual_entry(db_path: str, tool_name: str, unit_label: str,
                      time_spent_min: float | None = None, baseline_min: float | None = None,
                      edit_type: str | None = None, notes: str | None = None,
                      logged_by: str | None = None) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO measurement_manual_log "
            "(tool_name, unit_label, time_spent_min, baseline_min, edit_type, notes, logged_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tool_name, unit_label, time_spent_min, baseline_min, edit_type, notes, logged_by),
        )


def get_summary(db_path: str, tool_name: str) -> dict:
    """Everything the dashboard route needs, in one call."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        totals = conn.execute(
            "SELECT COUNT(*) AS n, SUM(success) AS ok, AVG(latency_ms) AS avg_latency "
            "FROM measurement_events WHERE tool_name = ?", (tool_name,)
        ).fetchone()

        p95_latency = _percentile(
            [r["latency_ms"] for r in conn.execute(
                "SELECT latency_ms FROM measurement_events WHERE tool_name = ? AND latency_ms IS NOT NULL",
                (tool_name,)
            ) if r["latency_ms"] is not None], 95
        )

        errors_by_type = conn.execute(
            "SELECT error_type, COUNT(*) AS n FROM measurement_events "
            "WHERE tool_name = ? AND success = 0 AND error_type IS NOT NULL "
            "GROUP BY error_type ORDER BY n DESC", (tool_name,)
        ).fetchall()

        by_action = conn.execute(
            "SELECT action, COUNT(*) AS n, SUM(success) AS ok FROM measurement_events "
            "WHERE tool_name = ? GROUP BY action ORDER BY n DESC", (tool_name,)
        ).fetchall()

        recent_manual = conn.execute(
            "SELECT * FROM measurement_manual_log WHERE tool_name = ? "
            "ORDER BY logged_at DESC LIMIT 20", (tool_name,)
        ).fetchall()

        edit_rate = conn.execute(
            "SELECT edit_type, COUNT(*) AS n FROM measurement_manual_log "
            "WHERE tool_name = ? AND edit_type IS NOT NULL GROUP BY edit_type", (tool_name,)
        ).fetchall()

    n = totals["n"] or 0
    ok = totals["ok"] or 0
    return {
        "tool_name": tool_name,
        "total_events": n,
        "success_rate": round(100 * ok / n, 1) if n else None,
        # Compare to None, not truthiness — a genuinely fast 0ms average is a
        # real, valid data point and must not be reported the same as "no
        # events yet" (which is what a bare `if totals["avg_latency"]` does,
        # since 0 and 0.0 are falsy in Python).
        "avg_latency_ms": round(totals["avg_latency"]) if totals["avg_latency"] is not None else None,
        "p95_latency_ms": p95_latency,
        "errors_by_type": [dict(r) for r in errors_by_type],
        "by_action": [dict(r) for r in by_action],
        "recent_manual_entries": [dict(r) for r in recent_manual],
        "edit_type_breakdown": [dict(r) for r in edit_rate],
    }


def _percentile(values: list[int], pct: int) -> int | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return round(s[f] + (s[c] - s[f]) * (k - f))
