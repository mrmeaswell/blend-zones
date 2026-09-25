-- Generic event/usage logging for the Deployment Measurement Framework.
-- Drop into any blend-zone tool's existing SQLite database, or run
-- standalone via init_db() in logger.py.

CREATE TABLE IF NOT EXISTS measurement_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT NOT NULL,       -- e.g. 'bay-log', 'emile'
    action      TEXT NOT NULL,       -- e.g. 'ticket_advance', 'lti_launch', 'generate_quiz'
    backend     TEXT,                -- e.g. 'ollama', 'hosted', 'n/a' — nullable for non-LLM tools
    success     INTEGER NOT NULL,    -- 1 or 0
    latency_ms  INTEGER,
    error_type  TEXT,                -- populated only when success = 0
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_tool_time ON measurement_events(tool_name, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_success ON measurement_events(success);

-- Manual entries for metrics that can't be auto-logged (time saved,
-- edit/correction rate). One row per person's self-report on one unit
-- of work.
CREATE TABLE IF NOT EXISTS measurement_manual_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name       TEXT NOT NULL,
    unit_label      TEXT NOT NULL,   -- e.g. 'WO-1042', 'quiz_a1b2c3'
    time_spent_min  REAL,
    baseline_min    REAL,            -- manual/paper baseline for the same unit, if known
    edit_type       TEXT,            -- 'none' | 'cosmetic' | 'substantive'
    notes           TEXT,
    logged_by       TEXT,
    logged_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_manual_tool_time ON measurement_manual_log(tool_name, logged_at);
