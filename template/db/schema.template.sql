-- ============================================================
-- [TOOL NAME] — Blend-Zone Tool Database Template
-- Generalized from Bay Log's schema. Covers: workflow tickets,
-- a knowledge base, and a resource catalog.
-- Written for SQLite (single local file, no server needed).
-- Notes on PostgreSQL/MySQL differences are marked [PG]/[MySQL].
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- STAGES — data-driven, so the workflow isn't hardcoded.
-- Replace these rows with the real workflow from the project brief.
-- ------------------------------------------------------------

CREATE TABLE stages (
    stage_key   TEXT PRIMARY KEY,      -- e.g. 'intake'
    label       TEXT NOT NULL,         -- e.g. 'Intake'
    sort_order  INTEGER NOT NULL
);

-- Example seed (replace with your own workflow's stages):
INSERT INTO stages (stage_key, label, sort_order) VALUES
('intake', 'Intake', 1),
('in_progress', 'In Progress', 2),
('review', 'Review', 3),
('done', 'Done', 4);

-- ------------------------------------------------------------
-- PEOPLE — generic for both departments in the blend zone
-- ------------------------------------------------------------

CREATE TABLE people (
    person_id   INTEGER PRIMARY KEY AUTOINCREMENT,  -- [PG] SERIAL PRIMARY KEY
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,   -- e.g. 'student', 'instructor', 'staff'
    email       TEXT
);

-- ------------------------------------------------------------
-- SUBJECTS — the thing being tracked. Rename this table (and the
-- attributes it needs) to whatever fits: vehicle, device, request,
-- project. `attributes` holds anything domain-specific as JSON so
-- you don't need a schema change for every new tool.
-- ------------------------------------------------------------

CREATE TABLE subjects (
    subject_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER REFERENCES people(person_id),
    label       TEXT NOT NULL,      -- e.g. '2014 Honda Civic', 'Rack A3'
    attributes  TEXT                -- JSON blob, e.g. '{"vin": "...", "color": "..."}'
);

-- ------------------------------------------------------------
-- TICKETS — the workflow core
-- ------------------------------------------------------------

CREATE TABLE tickets (
    ticket_id           TEXT PRIMARY KEY,   -- e.g. 'T-1001'
    subject_id          INTEGER NOT NULL REFERENCES subjects(subject_id),
    assigned_person_id  INTEGER REFERENCES people(person_id),
    stage_key           TEXT NOT NULL REFERENCES stages(stage_key),
    intake_notes        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),  -- [PG] TIMESTAMP DEFAULT now()
    closed_at           TEXT,
    done                INTEGER NOT NULL DEFAULT 0  -- [PG]/[MySQL] BOOLEAN DEFAULT false
);

CREATE INDEX idx_tickets_subject ON tickets(subject_id);
CREATE INDEX idx_tickets_stage ON tickets(stage_key);

-- Full history of stage transitions and notes at each one
CREATE TABLE ticket_stage_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id),
    stage_key   TEXT NOT NULL REFERENCES stages(stage_key),
    notes       TEXT,
    entered_at  TEXT NOT NULL DEFAULT (datetime('now')),
    exited_at   TEXT
);

CREATE INDEX idx_stage_log_ticket ON ticket_stage_log(ticket_id);

-- Any stage that needs a person's explicit sign-off (QC, approval, etc.)
CREATE TABLE stage_signoffs (
    ticket_id       TEXT NOT NULL REFERENCES tickets(ticket_id),
    stage_key       TEXT NOT NULL REFERENCES stages(stage_key),
    signed_off_by   INTEGER REFERENCES people(person_id),
    signed_off_at   TEXT,
    PRIMARY KEY (ticket_id, stage_key)
);

-- File/photo attachments, referenced by path rather than stored inline
CREATE TABLE attachments (
    attachment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       TEXT NOT NULL REFERENCES tickets(ticket_id),
    stage_key       TEXT NOT NULL REFERENCES stages(stage_key),
    file_path       TEXT NOT NULL,
    taken_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_attachments_ticket ON attachments(ticket_id);

-- ------------------------------------------------------------
-- KNOWLEDGE BASE — for any tutor/assistant layer to draw on,
-- and to build a real dataset over time via ticket_knowledge_links
-- ------------------------------------------------------------

CREATE TABLE knowledge_base (
    entry_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category            TEXT NOT NULL,
    trigger_or_symptom  TEXT NOT NULL,
    likely_causes       TEXT,
    diagnostic_steps    TEXT,
    common_resolution   TEXT,
    notes               TEXT
);

CREATE INDEX idx_kb_category ON knowledge_base(category);

CREATE TABLE ticket_knowledge_links (
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id),
    entry_id    INTEGER NOT NULL REFERENCES knowledge_base(entry_id),
    PRIMARY KEY (ticket_id, entry_id)
);

-- ------------------------------------------------------------
-- RESOURCE CATALOG — generalized "parts"; could be parts, supplies,
-- licenses, or anything consumed/used per ticket
-- ------------------------------------------------------------

CREATE TABLE resources (
    resource_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT,
    identifier      TEXT,      -- part number, SKU, license key label, etc.
    notes           TEXT
);

CREATE TABLE ticket_resources (
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id),
    resource_id INTEGER NOT NULL REFERENCES resources(resource_id),
    quantity    INTEGER NOT NULL DEFAULT 1,
    used_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticket_id, resource_id)
);

-- ============================================================
-- Run: sqlite3 tool.db < schema.template.sql
-- Or use init-db.sh alongside this file.
-- ============================================================
