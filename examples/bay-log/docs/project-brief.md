# Bay Log — blend-zone brief

Filled from `blend-zone-template/docs/project-brief.template.md`. This is
the reference instance: the workflow the template was originally pulled
out of, now running as a service.

## The mesh

- **Department A (owns the workflow)**: Automotive. They own what the
  stages are and what "done" means at each one. The stage list below is
  their existing bay process, not a new one invented for the tool.
- **Department B (owns build/maintain)**: IT. Builds the service, runs
  the container, handles the Canvas integration and backups.

## Named handoff pair

One person per side, not a committee.

- From Automotive: _[to fill — the lead automotive instructor]_
- From IT: _[to fill]_

> This is the one section still open. The template is emphatic that a
> named pair is what keeps a blend-zone tool scoped, so it's worth
> filling before the tool goes in front of students.

## The workflow

Seven stages, seeded in `config/workflow.json` and enforced by the API:

1. **Intake** — vehicle checked in, customer complaint recorded
2. **Diagnosis** — student diagnoses the fault, records findings
3. **Estimate Approval** — estimate presented, sign-off before work starts
4. **In Bay** — repair work performed
5. **QC Inspection** — instructor inspects, photo evidence required
6. **Ready for Pickup** — work complete, customer notified
7. **Closed** — archived to the audit log

## What's required to advance each stage

Enforced server-side, not just hinted in the UI. An advance attempt that
fails returns the specific unmet requirements.

| Stage | Required to move forward |
|---|---|
| Intake | Customer complaint + mileage at intake |
| Diagnosis | Diagnostic findings |
| Estimate Approval | Estimated labor hours **+ sign-off** (instructor or staff) |
| In Bay | Work performed |
| QC Inspection | Inspection notes **+ sign-off + at least one photo** |
| Ready for Pickup | Customer notified |
| Closed | — (terminal; closing stamps `closed_at` and marks the ticket done) |

Instructors and staff can force past a gate; students cannot. A forced
advance is still recorded in the stage history, so the override is
visible rather than silent.

## Clarity summary tiers

All three are served by the API at
`GET /api/tickets/{id}/summary?tier=line|paragraph|full`.

- **1-line** (status board): `T-1002 — 2011 Ford F-150 XLT — QC
  Inspection — Student B — blocked: Inspection notes is required`.
  The Board tab groups these by stage — that's the shop-wall view.
- **1-paragraph** (stakeholder update): current stage with timestamps,
  reported issue, who's assigned, which stages are complete, who signed
  off on what, and what it's blocked on.
- **Full record** (audit log): the complete ticket — every stage entry
  and exit with the field values captured at the time, all sign-offs with
  names and timestamps, attachments, parts consumed, knowledge-base links.
  Nothing is overwritten on a stage change; reverting a ticket reopens the
  prior stage's record rather than discarding it.

## Open questions

- [x] **Where does this need to be reachable from?** Canvas, via LTI 1.3.
  The service answers the full login/launch/JWK handshake and resolves a
  launch into an app session, so a student clicking the tool in a course
  lands in the tool as themselves with their Canvas role mapped.
- [ ] **Does this become a named example in grant/proposal work?** Still
  open. It's a clean example of IT building infrastructure another
  department actually operates on, if that's useful framing.
- [x] **Photo/file capture needed? At which stages?** Yes. Available at
  every stage, required at QC Inspection. The upload input uses
  `capture="environment"` so a phone or tablet opens the rear camera
  directly. JPEG/PNG/WebP/HEIC/PDF, 15 MB cap.

## What changed moving from template to service

The template was three pieces run by hand — a SQLite schema, a
single-file HTML shell using artifact-local storage, and an LTI skeleton
that printed a name. As a service:

- The HTML shell talks to a real API; data lives in one shared database
  instead of one browser's local storage, so the instructor and the
  student see the same board.
- Stage requirements moved from a comment in the template
  (`REQUIRED_TO_ADVANCE`, unenforced) to server-side gates that actually
  block, with role-gated sign-off and override.
- The LTI launch resolves identity into a person row and a session, and
  redirects into the tool.
- Stages and their fields are read from `config/workflow.json` at
  runtime, so forking for the next blend zone is a config edit plus a
  restart — no frontend or backend changes.
