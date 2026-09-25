-- ============================================================
-- Bay Log — Blend-Zone Tool Service Schema
-- Derived from blend-zone-template/db/schema.template.sql,
-- seeded for the Automotive bay workflow.
--
-- SQLite. Source of truth for the service's data model: the API
-- reads this file's shape directly (no ORM), so editing this file
-- plus config/workflow.json is how you fork for a new blend zone.
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ------------------------------------------------------------
-- STAGES — data-driven so the workflow isn't hardcoded.
-- Seeded with the Automotive bay workflow.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stages (
    stage_key   TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    short       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    is_terminal INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO stages (stage_key, label, short, sort_order, is_terminal) VALUES
('intake',            'Intake',            'IN', 1, 0),
('diagnosis',         'Diagnosis',         'DX', 2, 0),
('estimate_approval', 'Estimate Approval', 'EA', 3, 0),
('in_bay',            'In Bay',            'BAY',4, 0),
('qc_inspection',     'QC Inspection',     'QC', 5, 0),
('ready',             'Ready for Pickup',  'RDY',6, 0),
('closed',            'Closed',            'CLS',7, 1);

-- ------------------------------------------------------------
-- PEOPLE — both sides of the blend zone
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS people (
    person_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,              -- student | instructor | staff | advisor
    email       TEXT,
    lti_sub     TEXT UNIQUE,                -- LTI 1.3 'sub' claim, set on first launch
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_people_role ON people(role);

-- ------------------------------------------------------------
-- SUBJECTS — the tracked thing. For Bay Log: a vehicle.
-- Domain-specific fields live in `attributes` (JSON) so a new
-- blend zone doesn't need a migration.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subjects (
    subject_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER REFERENCES people(person_id),
    label       TEXT NOT NULL,              -- '2014 Honda Civic'
    attributes  TEXT NOT NULL DEFAULT '{}', -- {"vin":"...","plate":"...","mileage":123456}
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- TICKETS — the workflow core (a repair order in Bay Log)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id           TEXT PRIMARY KEY,   -- 'T-1001'
    subject_id          INTEGER NOT NULL REFERENCES subjects(subject_id),
    assigned_person_id  INTEGER REFERENCES people(person_id),
    stage_key           TEXT NOT NULL REFERENCES stages(stage_key),
    title               TEXT,               -- short complaint line
    intake_notes        TEXT,
    priority            TEXT NOT NULL DEFAULT 'normal',  -- low | normal | rush
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at           TEXT,
    done                INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tickets_subject ON tickets(subject_id);
CREATE INDEX IF NOT EXISTS idx_tickets_stage   ON tickets(stage_key);
CREATE INDEX IF NOT EXISTS idx_tickets_done    ON tickets(done);

-- Full history of stage transitions. One open row (exited_at IS NULL)
-- per ticket at any time = the current stage's working record.
CREATE TABLE IF NOT EXISTS ticket_stage_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    stage_key   TEXT NOT NULL REFERENCES stages(stage_key),
    notes       TEXT,
    entered_by  INTEGER REFERENCES people(person_id),
    entered_at  TEXT NOT NULL DEFAULT (datetime('now')),
    exited_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_stage_log_ticket ON ticket_stage_log(ticket_id);
CREATE INDEX IF NOT EXISTS idx_stage_log_open   ON ticket_stage_log(ticket_id, exited_at);

-- Explicit sign-off for stages that require one (estimate approval, QC)
CREATE TABLE IF NOT EXISTS stage_signoffs (
    ticket_id       TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    stage_key       TEXT NOT NULL REFERENCES stages(stage_key),
    signed_off_by   INTEGER REFERENCES people(person_id),
    signed_off_name TEXT,
    signed_off_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticket_id, stage_key)
);

-- File/photo attachments, referenced by path rather than stored inline
CREATE TABLE IF NOT EXISTS attachments (
    attachment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    stage_key       TEXT NOT NULL REFERENCES stages(stage_key),
    file_path       TEXT NOT NULL,
    original_name   TEXT,
    content_type    TEXT,
    size_bytes      INTEGER,
    taken_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_attachments_ticket ON attachments(ticket_id);

-- ------------------------------------------------------------
-- KNOWLEDGE BASE — what a tutor/assistant layer draws on, and
-- the dataset that accumulates via ticket_knowledge_links
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_base (
    entry_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category            TEXT NOT NULL,
    trigger_or_symptom  TEXT NOT NULL,
    likely_causes       TEXT,
    diagnostic_steps    TEXT,
    common_resolution   TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(category);

CREATE TABLE IF NOT EXISTS ticket_knowledge_links (
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    entry_id    INTEGER NOT NULL REFERENCES knowledge_base(entry_id) ON DELETE CASCADE,
    PRIMARY KEY (ticket_id, entry_id)
);

-- ------------------------------------------------------------
-- RESOURCE CATALOG — generalized "parts"
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS resources (
    resource_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT,
    identifier      TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS ticket_resources (
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    resource_id INTEGER NOT NULL REFERENCES resources(resource_id),
    quantity    INTEGER NOT NULL DEFAULT 1,
    used_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticket_id, resource_id)
);

-- ------------------------------------------------------------
-- SESSIONS — issued by the LTI launch, consumed by the web app
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_sessions (
    token       TEXT PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES people(person_id),
    role        TEXT NOT NULL,
    course      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON app_sessions(expires_at);

-- ------------------------------------------------------------
-- Convenience view: the 1-line clarity tier (status board)
-- ------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_status_board AS
SELECT
    t.ticket_id,
    s.label            AS subject,
    st.label           AS stage,
    st.sort_order      AS stage_order,
    t.title,
    t.priority,
    COALESCE(p.name, 'unassigned') AS assigned_to,
    t.updated_at
FROM tickets t
JOIN subjects s  ON s.subject_id = t.subject_id
JOIN stages   st ON st.stage_key = t.stage_key
LEFT JOIN people p ON p.person_id = t.assigned_person_id
WHERE t.done = 0;
