"""Bay Log — blend-zone tool service (FastAPI).

Routes:
  GET    /api/health                        liveness + readiness
  GET    /api/config                        workflow definition for the frontend
  GET    /api/me                            current actor
  GET    /api/board                         1-line clarity tier (status board)
  GET    /api/tickets                       list, filterable
  POST   /api/tickets                       create subject + ticket at first stage
  GET    /api/tickets/{id}                  full record
  PATCH  /api/tickets/{id}                  assignment / priority / title
  PUT    /api/tickets/{id}/stage-data       save current stage field values
  POST   /api/tickets/{id}/advance          gate-checked move to next stage
  POST   /api/tickets/{id}/revert           move back one stage
  POST   /api/tickets/{id}/signoff          role-gated sign-off
  POST   /api/tickets/{id}/attachments      photo/file upload
  GET    /api/attachments/{aid}             download
  GET    /api/tickets/{id}/summary          clarity tiers: line|paragraph|full
  GET/POST /api/kb, /api/resources, /api/people
"""

import json
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db
from .auth import Actor, current_actor, require_signoff_role

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="Bay Log — Blend-Zone Tool Service",
    version="1.0.0",
    description=(
        "Workflow service for a blend zone: where one department owns the "
        "operational process and IT owns build/maintain."
    ),
    lifespan=lifespan,
)

# Off unless BZ_CORS_ORIGINS is set. Credentials are deliberately not
# allowed: identity travels in the x-bz-session header, not a cookie, so
# there is no reason to open cookie-bearing cross-origin requests.
if config.CORS_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _stage_or_404(stage_key: str) -> dict:
    stage = config.stage_map().get(stage_key)
    if not stage:
        raise HTTPException(404, f"Unknown stage '{stage_key}'")
    return stage


def _ticket_row(conn: sqlite3.Connection, ticket_id: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT t.*, s.label AS subject_label, s.attributes AS subject_attributes,
               p.name AS assigned_name, p.role AS assigned_role
        FROM tickets t
        JOIN subjects s ON s.subject_id = t.subject_id
        LEFT JOIN people p ON p.person_id = t.assigned_person_id
        WHERE t.ticket_id = ?
        """,
        (ticket_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return row


def _parse_notes(raw: str | None) -> dict:
    """Stage field values live as JSON in ticket_stage_log.notes."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"notes": raw}
    except (json.JSONDecodeError, TypeError):
        return {"notes": raw}


def _open_log(conn: sqlite3.Connection, ticket_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM ticket_stage_log
        WHERE ticket_id = ? AND exited_at IS NULL
        ORDER BY log_id DESC LIMIT 1
        """,
        (ticket_id,),
    ).fetchone()


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _gate_check(conn: sqlite3.Connection, ticket_id: str, stage_key: str) -> list[str]:
    """Returns the list of unmet requirements for leaving `stage_key`."""
    stage = _stage_or_404(stage_key)
    requires = stage.get("requires") or {}
    problems: list[str] = []

    log = _open_log(conn, ticket_id)
    data = _parse_notes(log["notes"] if log else None)

    field_labels = {f["key"]: f["label"] for f in stage.get("fields", [])}
    for key in requires.get("fields", []):
        if _is_blank(data.get(key)):
            problems.append(f"{field_labels.get(key, key)} is required")

    if requires.get("signoff"):
        row = conn.execute(
            "SELECT 1 FROM stage_signoffs WHERE ticket_id = ? AND stage_key = ?",
            (ticket_id, stage_key),
        ).fetchone()
        if not row:
            problems.append(f"{stage['label']} needs a sign-off")

    needed = int(requires.get("attachments", 0) or 0)
    if needed:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM attachments WHERE ticket_id = ? AND stage_key = ?",
            (ticket_id, stage_key),
        ).fetchone()["n"]
        if n < needed:
            problems.append(
                f"{stage['label']} needs {needed} attachment(s); {n} uploaded"
            )

    return problems


def _touch(conn: sqlite3.Connection, ticket_id: str) -> None:
    conn.execute(
        "UPDATE tickets SET updated_at = datetime('now') WHERE ticket_id = ?",
        (ticket_id,),
    )


# ----------------------------------------------------------------------
# Meta
# ----------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    try:
        with db.ro() as conn:
            conn.execute("SELECT 1 FROM stages LIMIT 1").fetchone()
        return {"status": "ok", "database": "ok", "tool": config.workflow()["tool_name"]}
    except Exception as exc:  # pragma: no cover
        return JSONResponse(
            status_code=503, content={"status": "error", "detail": str(exc)}
        )


@app.get("/api/config")
def get_config() -> dict:
    wf = config.workflow()
    return {
        "tool_name": wf["tool_name"],
        "department_a": wf["department_a"],
        "department_b": wf["department_b"],
        "subject_label": wf["subject_label"],
        "new_item_label": wf["new_item_label"],
        "subject_fields": wf["subject_fields"],
        "stages": wf["stages"],
        "signoff_roles": sorted(config.signoff_roles()),
        "require_auth": config.REQUIRE_AUTH,
    }


@app.get("/api/me")
def me(actor: Actor = Depends(current_actor)) -> dict:
    return {
        "person_id": actor.person_id,
        "name": actor.name,
        "role": actor.role,
        "course": actor.course,
        "authenticated": actor.authenticated,
        "can_signoff": actor.can_signoff(),
    }


# ----------------------------------------------------------------------
# Tickets
# ----------------------------------------------------------------------


class TicketCreate(BaseModel):
    subject_label: str = Field(min_length=1, max_length=200)
    subject_attributes: dict[str, Any] = Field(default_factory=dict)
    title: str | None = Field(default=None, max_length=300)
    priority: str = "normal"
    assigned_person_id: int | None = None
    stage_data: dict[str, Any] = Field(default_factory=dict)


class TicketPatch(BaseModel):
    title: str | None = None
    priority: str | None = None
    assigned_person_id: int | None = None


class StageData(BaseModel):
    data: dict[str, Any]


class SignoffIn(BaseModel):
    name: str | None = None


class AdvanceIn(BaseModel):
    force: bool = False


@app.get("/api/board")
def board() -> list[dict]:
    with db.ro() as conn:
        rows = conn.execute(
            "SELECT * FROM v_status_board ORDER BY stage_order, updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/tickets")
def list_tickets(stage: str | None = None, done: int | None = None) -> list[dict]:
    sql = [
        """
        SELECT t.ticket_id, t.stage_key, t.title, t.priority, t.done,
               t.created_at, t.updated_at, t.closed_at,
               s.label AS subject_label, s.attributes AS subject_attributes,
               p.name AS assigned_name
        FROM tickets t
        JOIN subjects s ON s.subject_id = t.subject_id
        LEFT JOIN people p ON p.person_id = t.assigned_person_id
        """
    ]
    where, params = [], []
    if stage:
        where.append("t.stage_key = ?")
        params.append(stage)
    if done is not None:
        where.append("t.done = ?")
        params.append(done)
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY t.updated_at DESC")

    with db.ro() as conn:
        rows = conn.execute(" ".join(sql), params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["subject_attributes"] = _parse_notes(r["subject_attributes"])
            log = _open_log(conn, r["ticket_id"])
            item["stage_data"] = _parse_notes(log["notes"] if log else None)
            item["blockers"] = _gate_check(conn, r["ticket_id"], r["stage_key"])
            out.append(item)
    return out


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate, actor: Actor = Depends(current_actor)) -> dict:
    first_stage = config.stage_keys()[0]
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO subjects (owner_id, label, attributes) VALUES (?, ?, ?)",
            (
                None,
                payload.subject_label.strip(),
                json.dumps(payload.subject_attributes),
            ),
        )
        subject_id = int(cur.lastrowid)
        ticket_id = db.next_ticket_id(conn)

        conn.execute(
            """
            INSERT INTO tickets
                (ticket_id, subject_id, assigned_person_id, stage_key, title,
                 intake_notes, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                subject_id,
                payload.assigned_person_id or actor.person_id,
                first_stage,
                (payload.title or "").strip() or None,
                payload.stage_data.get("complaint") or payload.stage_data.get("notes"),
                payload.priority if payload.priority in {"low", "normal", "rush"} else "normal",
            ),
        )
        conn.execute(
            """
            INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_id, first_stage, json.dumps(payload.stage_data), actor.person_id),
        )
    return get_ticket(ticket_id)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    with db.ro() as conn:
        row = _ticket_row(conn, ticket_id)
        history = conn.execute(
            """
            SELECT l.log_id, l.stage_key, l.notes, l.entered_at, l.exited_at,
                   p.name AS entered_by_name
            FROM ticket_stage_log l
            LEFT JOIN people p ON p.person_id = l.entered_by
            WHERE l.ticket_id = ? ORDER BY l.log_id
            """,
            (ticket_id,),
        ).fetchall()
        signoffs = conn.execute(
            """
            SELECT sg.stage_key, sg.signed_off_at,
                   COALESCE(p.name, sg.signed_off_name) AS signed_off_by
            FROM stage_signoffs sg
            LEFT JOIN people p ON p.person_id = sg.signed_off_by
            WHERE sg.ticket_id = ?
            """,
            (ticket_id,),
        ).fetchall()
        attachments = conn.execute(
            """
            SELECT attachment_id, stage_key, original_name, content_type,
                   size_bytes, taken_at
            FROM attachments WHERE ticket_id = ? ORDER BY attachment_id
            """,
            (ticket_id,),
        ).fetchall()
        resources = conn.execute(
            """
            SELECT r.resource_id, r.name, r.category, r.identifier, tr.quantity, tr.used_at
            FROM ticket_resources tr JOIN resources r ON r.resource_id = tr.resource_id
            WHERE tr.ticket_id = ?
            """,
            (ticket_id,),
        ).fetchall()
        kb = conn.execute(
            """
            SELECT k.entry_id, k.category, k.trigger_or_symptom, k.common_resolution
            FROM ticket_knowledge_links tk
            JOIN knowledge_base k ON k.entry_id = tk.entry_id
            WHERE tk.ticket_id = ?
            """,
            (ticket_id,),
        ).fetchall()
        blockers = _gate_check(conn, ticket_id, row["stage_key"])
        open_log = _open_log(conn, ticket_id)

    return {
        "ticket_id": row["ticket_id"],
        "stage_key": row["stage_key"],
        "stage_label": config.stage_map()[row["stage_key"]]["label"],
        "next_stage": config.next_stage(row["stage_key"]),
        "prev_stage": config.prev_stage(row["stage_key"]),
        "title": row["title"],
        "priority": row["priority"],
        "done": bool(row["done"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "closed_at": row["closed_at"],
        "subject": {
            "subject_id": row["subject_id"],
            "label": row["subject_label"],
            "attributes": _parse_notes(row["subject_attributes"]),
        },
        "assigned_to": row["assigned_name"],
        "stage_data": _parse_notes(open_log["notes"] if open_log else None),
        "blockers": blockers,
        "can_advance": not blockers and config.next_stage(row["stage_key"]) is not None,
        "history": [
            {
                "log_id": h["log_id"],
                "stage_key": h["stage_key"],
                "stage_label": config.stage_map()
                .get(h["stage_key"], {})
                .get("label", h["stage_key"]),
                "data": _parse_notes(h["notes"]),
                "entered_at": h["entered_at"],
                "exited_at": h["exited_at"],
                "entered_by": h["entered_by_name"],
            }
            for h in history
        ],
        "signoffs": [dict(s) for s in signoffs],
        "attachments": [dict(a) for a in attachments],
        "resources": [dict(r) for r in resources],
        "knowledge_links": [dict(k) for k in kb],
    }


@app.patch("/api/tickets/{ticket_id}")
def patch_ticket(ticket_id: str, payload: TicketPatch) -> dict:
    sets, params = [], []
    if payload.title is not None:
        sets.append("title = ?")
        params.append(payload.title.strip() or None)
    if payload.priority is not None:
        if payload.priority not in {"low", "normal", "rush"}:
            raise HTTPException(422, "priority must be low, normal, or rush")
        sets.append("priority = ?")
        params.append(payload.priority)
    if payload.assigned_person_id is not None:
        sets.append("assigned_person_id = ?")
        params.append(payload.assigned_person_id)
    if not sets:
        return get_ticket(ticket_id)

    with db.tx() as conn:
        _ticket_row(conn, ticket_id)
        params.append(ticket_id)
        conn.execute(
            f"UPDATE tickets SET {', '.join(sets)}, updated_at = datetime('now')"
            " WHERE ticket_id = ?",
            params,
        )
    return get_ticket(ticket_id)


@app.put("/api/tickets/{ticket_id}/stage-data")
def save_stage_data(
    ticket_id: str, payload: StageData, actor: Actor = Depends(current_actor)
) -> dict:
    """Merges values into the currently open stage log row."""
    with db.tx() as conn:
        row = _ticket_row(conn, ticket_id)
        if row["done"]:
            raise HTTPException(409, "Ticket is closed")
        log = _open_log(conn, ticket_id)
        if not log:
            cur = conn.execute(
                "INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by)"
                " VALUES (?, ?, ?, ?)",
                (ticket_id, row["stage_key"], json.dumps(payload.data), actor.person_id),
            )
            log_id = int(cur.lastrowid)
        else:
            merged = _parse_notes(log["notes"])
            merged.update(payload.data)
            log_id = log["log_id"]
            conn.execute(
                "UPDATE ticket_stage_log SET notes = ? WHERE log_id = ?",
                (json.dumps(merged), log_id),
            )
        _touch(conn, ticket_id)
    return get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/advance")
def advance(
    ticket_id: str,
    payload: AdvanceIn | None = None,
    actor: Actor = Depends(current_actor),
) -> dict:
    force = bool(payload and payload.force)
    with db.tx() as conn:
        row = _ticket_row(conn, ticket_id)
        current = row["stage_key"]
        nxt = config.next_stage(current)
        if nxt is None:
            raise HTTPException(409, f"{config.stage_map()[current]['label']} is the final stage")

        problems = _gate_check(conn, ticket_id, current)
        if problems and not force:
            raise HTTPException(
                status_code=422,
                detail={"message": "Stage requirements not met", "blockers": problems},
            )
        if force and not actor.can_signoff():
            raise HTTPException(403, "Only instructors/staff may override a stage gate")

        conn.execute(
            "UPDATE ticket_stage_log SET exited_at = datetime('now')"
            " WHERE ticket_id = ? AND exited_at IS NULL",
            (ticket_id,),
        )
        conn.execute(
            "INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by)"
            " VALUES (?, ?, '{}', ?)",
            (ticket_id, nxt, actor.person_id),
        )
        terminal = bool(config.stage_map()[nxt].get("terminal"))
        conn.execute(
            """
            UPDATE tickets SET stage_key = ?, updated_at = datetime('now'),
                   done = ?, closed_at = CASE WHEN ? THEN datetime('now') ELSE closed_at END
            WHERE ticket_id = ?
            """,
            (nxt, 1 if terminal else 0, 1 if terminal else 0, ticket_id),
        )
    return get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/revert")
def revert(ticket_id: str, actor: Actor = Depends(current_actor)) -> dict:
    with db.tx() as conn:
        row = _ticket_row(conn, ticket_id)
        prev = config.prev_stage(row["stage_key"])
        if prev is None:
            raise HTTPException(409, "Already at the first stage")
        conn.execute(
            "UPDATE ticket_stage_log SET exited_at = datetime('now')"
            " WHERE ticket_id = ? AND exited_at IS NULL",
            (ticket_id,),
        )
        # Reopen the most recent record for the previous stage so prior
        # work isn't lost when a ticket bounces back.
        old = conn.execute(
            """
            SELECT notes FROM ticket_stage_log
            WHERE ticket_id = ? AND stage_key = ? ORDER BY log_id DESC LIMIT 1
            """,
            (ticket_id, prev),
        ).fetchone()
        conn.execute(
            "INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by)"
            " VALUES (?, ?, ?, ?)",
            (ticket_id, prev, old["notes"] if old else "{}", actor.person_id),
        )
        conn.execute(
            "UPDATE tickets SET stage_key = ?, done = 0, closed_at = NULL,"
            " updated_at = datetime('now') WHERE ticket_id = ?",
            (prev, ticket_id),
        )
    return get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/signoff")
def signoff(
    ticket_id: str,
    payload: SignoffIn | None = None,
    actor: Actor = Depends(current_actor),
) -> dict:
    require_signoff_role(actor)
    with db.tx() as conn:
        row = _ticket_row(conn, ticket_id)
        conn.execute(
            """
            INSERT INTO stage_signoffs (ticket_id, stage_key, signed_off_by, signed_off_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticket_id, stage_key) DO UPDATE SET
                signed_off_by = excluded.signed_off_by,
                signed_off_name = excluded.signed_off_name,
                signed_off_at = datetime('now')
            """,
            (
                ticket_id,
                row["stage_key"],
                actor.person_id,
                (payload.name if payload and payload.name else actor.name),
            ),
        )
        _touch(conn, ticket_id)
    return get_ticket(ticket_id)


# ----------------------------------------------------------------------
# Attachments
# ----------------------------------------------------------------------


@app.post("/api/tickets/{ticket_id}/attachments", status_code=201)
async def upload_attachment(
    ticket_id: str,
    file: UploadFile = File(...),
    actor: Actor = Depends(current_actor),
) -> dict:
    if file.content_type not in config.ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            415,
            f"Unsupported type {file.content_type}. Allowed: "
            + ", ".join(sorted(config.ALLOWED_UPLOAD_TYPES)),
        )
    blob = await file.read()
    if len(blob) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    if not blob:
        raise HTTPException(422, "Empty file")

    with db.ro() as conn:
        row = _ticket_row(conn, ticket_id)
        stage_key = row["stage_key"]

    safe_ext = Path(file.filename or "upload").suffix.lower()[:10]
    if not re.fullmatch(r"\.[a-z0-9]{1,9}", safe_ext or ""):
        safe_ext = ""
    dest_dir = config.UPLOAD_DIR / ticket_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stage_key}-{secrets.token_hex(8)}{safe_ext}"
    dest.write_bytes(blob)

    with db.tx() as conn:
        cur = conn.execute(
            """
            INSERT INTO attachments
                (ticket_id, stage_key, file_path, original_name, content_type, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                stage_key,
                str(dest),
                file.filename,
                file.content_type,
                len(blob),
            ),
        )
        _touch(conn, ticket_id)
        attachment_id = int(cur.lastrowid)

    return {"attachment_id": attachment_id, "stage_key": stage_key, "size_bytes": len(blob)}


@app.get("/api/attachments/{attachment_id}")
def download_attachment(attachment_id: int):
    with db.ro() as conn:
        row = conn.execute(
            "SELECT file_path, original_name, content_type FROM attachments"
            " WHERE attachment_id = ?",
            (attachment_id,),
        ).fetchone()
    if not row or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Attachment not found")
    return FileResponse(
        row["file_path"],
        media_type=row["content_type"] or "application/octet-stream",
        filename=row["original_name"] or f"attachment-{attachment_id}",
    )


# ----------------------------------------------------------------------
# Clarity summary tiers
# ----------------------------------------------------------------------


@app.get("/api/tickets/{ticket_id}/summary")
def summary(ticket_id: str, tier: str = "line") -> dict:
    if tier not in {"line", "paragraph", "full"}:
        raise HTTPException(422, "tier must be line, paragraph, or full")
    t = get_ticket(ticket_id)

    if tier == "line":
        text = (
            f"{t['ticket_id']} — {t['subject']['label']} — {t['stage_label']}"
            f" — {t['assigned_to'] or 'unassigned'}"
        )
        if t["blockers"]:
            text += f" — blocked: {t['blockers'][0]}"
        return {"tier": tier, "text": text}

    if tier == "paragraph":
        parts = [
            f"{t['ticket_id']} ({t['subject']['label']}) is at "
            f"{t['stage_label']}, opened {t['created_at']} and last updated "
            f"{t['updated_at']}."
        ]
        if t["title"]:
            parts.append(f"Reported issue: {t['title']}.")
        if t["assigned_to"]:
            parts.append(f"Assigned to {t['assigned_to']}.")
        done_stages = [
            h["stage_label"] for h in t["history"] if h["exited_at"]
        ]
        if done_stages:
            parts.append("Completed stages: " + ", ".join(dict.fromkeys(done_stages)) + ".")
        if t["signoffs"]:
            parts.append(
                "Sign-offs: "
                + ", ".join(
                    f"{config.stage_map().get(s['stage_key'], {}).get('label', s['stage_key'])}"
                    f" by {s['signed_off_by']}"
                    for s in t["signoffs"]
                )
                + "."
            )
        parts.append(
            "Blocked on: " + "; ".join(t["blockers"]) + "."
            if t["blockers"]
            else "No outstanding requirements at the current stage."
        )
        return {"tier": tier, "text": " ".join(parts)}

    return {"tier": tier, "record": t}


# ----------------------------------------------------------------------
# Knowledge base / resources / people
# ----------------------------------------------------------------------


class KBEntry(BaseModel):
    category: str
    trigger_or_symptom: str
    likely_causes: str | None = None
    diagnostic_steps: str | None = None
    common_resolution: str | None = None
    notes: str | None = None


class ResourceIn(BaseModel):
    name: str
    category: str | None = None
    identifier: str | None = None
    notes: str | None = None


class PersonIn(BaseModel):
    name: str
    role: str = "student"
    email: str | None = None


class LinkKB(BaseModel):
    entry_id: int


class UseResource(BaseModel):
    resource_id: int
    quantity: int = 1


@app.get("/api/kb")
def list_kb(q: str | None = None, category: str | None = None) -> list[dict]:
    sql = ["SELECT * FROM knowledge_base"]
    where, params = [], []
    if category:
        where.append("category = ?")
        params.append(category)
    if q:
        where.append(
            "(trigger_or_symptom LIKE ? OR likely_causes LIKE ?"
            " OR common_resolution LIKE ?)"
        )
        params += [f"%{q}%"] * 3
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY category, entry_id")
    with db.ro() as conn:
        return [dict(r) for r in conn.execute(" ".join(sql), params).fetchall()]


@app.post("/api/kb", status_code=201)
def create_kb(payload: KBEntry) -> dict:
    with db.tx() as conn:
        cur = conn.execute(
            """
            INSERT INTO knowledge_base
                (category, trigger_or_symptom, likely_causes, diagnostic_steps,
                 common_resolution, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.category,
                payload.trigger_or_symptom,
                payload.likely_causes,
                payload.diagnostic_steps,
                payload.common_resolution,
                payload.notes,
            ),
        )
        return {"entry_id": int(cur.lastrowid)}


@app.post("/api/tickets/{ticket_id}/kb-links", status_code=201)
def link_kb(ticket_id: str, payload: LinkKB) -> dict:
    with db.tx() as conn:
        _ticket_row(conn, ticket_id)
        conn.execute(
            "INSERT OR IGNORE INTO ticket_knowledge_links (ticket_id, entry_id)"
            " VALUES (?, ?)",
            (ticket_id, payload.entry_id),
        )
    return get_ticket(ticket_id)


@app.get("/api/resources")
def list_resources() -> list[dict]:
    with db.ro() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
        ]


@app.post("/api/resources", status_code=201)
def create_resource(payload: ResourceIn) -> dict:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO resources (name, category, identifier, notes)"
            " VALUES (?, ?, ?, ?)",
            (payload.name, payload.category, payload.identifier, payload.notes),
        )
        return {"resource_id": int(cur.lastrowid)}


@app.post("/api/tickets/{ticket_id}/resources", status_code=201)
def use_resource(ticket_id: str, payload: UseResource) -> dict:
    with db.tx() as conn:
        _ticket_row(conn, ticket_id)
        conn.execute(
            """
            INSERT INTO ticket_resources (ticket_id, resource_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(ticket_id, resource_id) DO UPDATE SET
                quantity = excluded.quantity, used_at = datetime('now')
            """,
            (ticket_id, payload.resource_id, max(1, payload.quantity)),
        )
        _touch(conn, ticket_id)
    return get_ticket(ticket_id)


@app.get("/api/people")
def list_people(role: str | None = None) -> list[dict]:
    with db.ro() as conn:
        if role:
            rows = conn.execute(
                "SELECT person_id, name, role, email FROM people WHERE role = ?"
                " ORDER BY name",
                (role,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT person_id, name, role, email FROM people ORDER BY role, name"
            ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/people", status_code=201)
def create_person(payload: PersonIn) -> dict:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO people (name, role, email) VALUES (?, ?, ?)",
            (payload.name, payload.role, payload.email),
        )
        return {"person_id": int(cur.lastrowid)}


# ----------------------------------------------------------------------
# Frontend (mounted last so /api/* wins)
# ----------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Serves the terminal shell. A `?session=` token from the LTI launch is
    promoted to an HttpOnly cookie and stripped from the URL."""
    token = request.query_params.get("session")
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    resp = HTMLResponse(html)
    if token:
        resp.set_cookie(
            config.SESSION_COOKIE,
            token,
            httponly=True,
            samesite="none",
            secure=True,
            max_age=config.SESSION_TTL_HOURS * 3600,
        )
    return resp


app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
