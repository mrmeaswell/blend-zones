# Measurement — Deployment Measurement Framework + Dashboard

Generalized from the Emile Deployment Measurement Framework. Two pieces:

- `deployment-measurement-framework.template.md` — the framework doc
  itself (phases, metric groups, review cadence). Fill in your tool's
  name and adapt the metric definitions where the generic wording
  doesn't quite fit.
- `logger.py` + `dashboard_blueprint.py` + `schema.sql` — a drop-in
  Flask blueprint that implements the auto-loggable metrics
  (Technical Reliability, Adoption/Usage) plus a manual-entry form for
  the two metrics that need a human to report them (time saved,
  edit/correction rate).

## Wiring into your tool's Flask app

```python
# app.py
from measurement.dashboard_blueprint import build_measurement_blueprint

app.register_blueprint(build_measurement_blueprint(
    db_path="tool.db",      # can be the same SQLite file your tool already uses
    tool_name="your-tool",  # e.g. "bay-log", "emile"
))
```

Then log events at the point in your own code where something succeeds
or fails — this is the one integration step per action worth logging,
not automatic.

### Example: Bay Log's LTI launch endpoint

```python
# lti/app.py, inside the /launch route
from measurement.logger import log_event, timed_call

with timed_call() as t:
    try:
        launch_data = message_launch.get_launch_data()
        success, error_type = True, None
    except Exception as e:
        success, error_type = False, type(e).__name__

log_event(
    db_path="tool.db",
    tool_name="bay-log",
    action="lti_launch",
    success=success,
    latency_ms=t.ms,
    error_type=error_type,
)
```

### Example: a ticket stage advance (Bay Log's workflow logic)

If the workflow logic lives client-side (as Bay Log's HTML/JS version
does) rather than in Flask, log from whatever server endpoint actually
persists the stage change instead — logging only makes sense at a point
your server can see, not inside client-only JavaScript.

## Visiting the dashboard

Once wired in: `https://your-tool-domain/measurement/dashboard`

Shows total events, success rate, latency (median/p95), errors by type,
usage by action, and a manual-entry form for time-saved/edit-rate
logging — plus the 20 most recent manual entries.

## What this does NOT do

- No student-outcome or grade data — this measures the tool, not a
  curriculum. Keep those in whatever program evaluation plan applies.
- No authentication on `/measurement/*` routes by default — put this
  behind the same auth layer as the rest of your tool (Cloudflare
  Access, Okta, etc.), don't expose it publicly as-is.
- Adoption metrics (active users, repeat-use rate) need real usage
  across more than one person to mean anything — expect empty/trivial
  numbers during Phase 0 solo use, per the framework's own phase gating.

## Version / keeping vendored copies in sync

This folder is meant to be copied into each tool that needs it (Emile,
Bay Log, whatever's next) rather than imported as a shared package —
it's a handful of dependency-light files, and every tool here is
deliberately built to run standalone (Emile ships as a portable Docker
container; blend-zone tools are SQLite-first, no-build-step). A shared
installable package would cut against both of those goals for the sake
of saving a few hundred lines of duplication.

To keep vendored copies from silently drifting:

- `blend-zone-template/measurement/` is the canonical source. Improve
  logging/dashboard logic here first, not in a fork.
- Every copy carries a `VERSION` file. When you pull an update from the
  canonical source into a tool's vendored copy, bump that tool's
  `VERSION` to match.
- If a tool's `VERSION` is behind canonical, that's your signal to diff
  and re-sync — not a silent, permanent fork.
