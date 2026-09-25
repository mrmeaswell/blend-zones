# Bay Log

A stage-gated work-order tracker for the Automotive teaching bay,
running as a native LXC container service on Proxmox. Canvas LTI 1.3
launch, photo capture, role-gated sign-offs, and a full audit trail.

This is the reference implementation of the *blend-zone template* — the
pattern where one department owns a workflow and another builds the tool
that runs it. Fork it for the next blend zone by editing one config file.

```
Canvas ──LTI 1.3──┐
                  ▼
      nginx :80 ──► uvicorn 127.0.0.1:8080 ──► SQLite (WAL)
                    FastAPI + Flask (LTI)      /var/lib/blendzone
```

No Docker. A Python venv, a systemd unit, and nginx in an unprivileged
Debian 12 container.

## Quick start (local)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/generate_keys.py
.venv/bin/uvicorn app.asgi:app --port 8080
```

Open <http://localhost:8080>. The database initializes and seeds itself on
first run — three vehicles mid-workflow, five people, ten parts, five
knowledge-base entries. Append `?as=instructor` to the URL to act as an
instructor while `BZ_DEV_AUTH=1`.

```bash
.venv/bin/python tests/test_workflow.py    # 51 checks
```

## Deploy to Proxmox

From the Proxmox host shell:

```bash
REPO_URL=<this-repo> scripts/provision-ct.sh
```

Creates an unprivileged Debian 12 CT (default CTID 301, hostname
`baylog`), installs the service, and prints the URL. Every setting is an
env override — `CTID`, `CT_STORAGE`, `CT_MEMORY_MB`, `CT_IP`, and the
rest. See the [runbook](docs/runbook.md).

Re-running `bootstrap.sh` inside the CT is the deploy path for code
changes. It never touches the database, uploads, env file, or LTI keys.

## The workflow

Intake → Diagnosis → Estimate Approval → In Bay → QC Inspection → Ready
for Pickup → Closed.

Each stage declares its fields and what's required to leave it.
Requirements are enforced server-side: Estimate Approval needs a
sign-off, QC Inspection needs a sign-off *and* a photo. Students can
advance tickets but not sign off and not override a gate; instructors and
staff can, and the override lands in the history.

## Forking for another blend zone

`config/workflow.json` is the whole workflow definition — stages, their
fields, gate requirements, subject fields, sign-off roles. The frontend
renders its inputs from `/api/config` and the backend reads its gates
from the same file, so a new blend zone is:

1. Edit `config/workflow.json` (rename stages, change fields, set gates)
2. Edit `db/seed.sql` for the new domain's reference data
3. Restart

No frontend or backend changes. Stage field values are stored as JSON, so
adding a field needs no migration.

## Layout

| Path | |
|---|---|
| `app/main.py` | FastAPI — routes, stage gates, the three summary tiers |
| `app/lti_app.py` | Flask LTI 1.3 provider, mounted at `/lti` |
| `app/asgi.py` | Entrypoint (`app.asgi:app`); tolerates unconfigured Canvas |
| `app/db.py` | sqlite3 layer, no ORM |
| `app/static/index.html` | Single-file touch UI, vanilla JS |
| `config/workflow.json` | **The blend-zone definition** |
| `config/lti_config.json` | Canvas registration |
| `db/schema.sql`, `db/seed.sql` | Schema and Bay Log seed data |
| `deploy/` | systemd unit + nginx site |
| `scripts/provision-ct.sh` | Runs on the Proxmox host — creates the CT |
| `scripts/bootstrap.sh` | Runs in the CT — installs and starts the service |
| `docs/` | Runbook, instructor guide, project brief |

## Docs

- [Runbook](docs/runbook.md) — deploy, TLS, Canvas key wiring, backups, troubleshooting
- [Instructor guide](docs/instructor-guide.md) — how to actually use it
- [Project brief](docs/project-brief.md) — the filled-in blend-zone brief
- [config/README.md](config/README.md) — two pylti1p3 gotchas worth knowing

## Before students use it

The defaults are walkthrough-friendly, not production-safe. In
`/etc/blendzone.env`:

- `BZ_DEV_AUTH=0` — removes the `?as=<role>` override
- `BZ_REQUIRE_AUTH=1` — requires a real Canvas launch

And put TLS in front of it; Canvas won't launch an LTI tool over plain
HTTP. Both covered in the runbook.

## Showing the UI from outside the lab network

The container lives on your private network, so `192.0.2.10` is not
reachable from a normal browser. Two ways around that:

- **Proper answer** — put a Cloudflare Tunnel hostname in front of it. This
  is what Canvas will need anyway, since LTI launches require HTTPS.
  Covered in the runbook.
- **Quick look** — build a static copy of the frontend pointed at an API
  reachable from wherever you are:

  ```
  python scripts/build-preview.py <api-base> [out-dir]
  ```

  `<api-base>` is prefixed to every API path. It accepts a full origin
  (`https://baylog.example.edu`, which also needs that origin in
  `BZ_CORS_ORIGINS`) or a same-origin path prefix (`port/8080`), which
  needs no CORS at all. The build also disables session storage, since
  sandboxed iframes forbid it — the role selector falls back to memory.

`BZ_CORS_ORIGINS` is empty by default, so cross-origin requests are
refused unless you deliberately opt in.
