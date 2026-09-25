# Bay Log — instructor and student guide

No install. Open the tool's address in a browser, or click it in Canvas.
It's built for a shop tablet: big touch targets, no menus buried in
menus.

## The four tabs

**Orders** — every open repair order. Tap one to work it.
**New RO** — check a vehicle in.
**Board** — the shop-wall view: every ticket grouped by stage.
**Knowledge** — the shop's reference notes.

## Checking a vehicle in

**New RO** → year, make, model, plate, VIN, customer name → the two
intake fields (the customer's complaint, and mileage on arrival) →
optionally assign a student → **Create Repair Order**.

You get a ticket number (`T-1004` and up) and the vehicle lands in
Intake. You don't have to fill the intake fields at creation, but the
ticket won't leave Intake until they're filled.

## Working a ticket

Open it. You see the current stage, the fields that stage wants, who's
assigned, and a **Requirements** strip showing what's still missing
before it can advance.

Fill the fields → **Save**. Save as often as you like; nothing advances
until you say so.

When the requirement strip is clear, **Advance** moves it to the next
stage. If something's missing, Advance tells you exactly what — it
doesn't fail silently.

**Revert** sends a ticket back a stage. The earlier stage's notes are
still there; reverting reopens that record rather than wiping it.

## Sign-offs

Two stages need an instructor or staff sign-off:

- **Estimate Approval** — before any work starts
- **QC Inspection** — before the vehicle goes back to the customer

On those stages there's a **Sign Off** button. Students see it but can't
use it; the server refuses. Sign-offs are recorded with your name and the
timestamp, and they stay in the record permanently.

## Photos

**Add Photo** on any ticket. On a phone or tablet it opens the camera
directly. QC Inspection requires at least one photo before the ticket can
advance — the point being that the inspection has evidence attached, not
just a checkbox.

JPEG, PNG, WebP, HEIC, and PDF. 15 MB per file.

## Parts and knowledge base

**Parts** on the ticket records what was consumed, with quantity. Stock
counts decrement as you go.

**Knowledge** is the shop's reference notes — torque specs, TSBs,
procedures, common faults. Search it from the Knowledge tab. From inside
a ticket you can **link** a knowledge entry, which is how a diagnosis
gets tied to the reference that supported it. Good for grading: you can
see what the student actually consulted.

## The three ways to read a ticket

Same data, three levels of detail, depending on who's asking:

- **One line** — what the Board shows. Ticket, vehicle, stage, who's on
  it, what it's blocked on. This is the glance-and-move-on view.
- **One paragraph** — the ticket's Summary button. Where it is, how long
  it's been there, what's done, who signed what, what's blocking. This is
  the version to paste into an email.
- **Full record** — the whole audit trail. Every stage entry and exit
  with the values recorded at the time, every sign-off, attachments,
  parts, linked references. This is the version for a grade dispute or an
  accreditation question.

## Roles

- **Student** — creates and works tickets, fills fields, uploads photos,
  advances stages when requirements are met. Cannot sign off. Cannot
  override a gate.
- **Instructor / Staff** — everything above, plus sign-offs and
  overriding a blocked stage. An override is recorded in the history, so
  it's visible later.

Launched from Canvas, your role comes from your Canvas role
automatically.

## If something looks wrong

Reload the page first — the tool reads from the server on load, and a
stale tab is the most common cause of "that's not what I saved."

If a ticket won't advance and the requirement strip looks satisfied,
check that you hit **Save** before **Advance**. Unsaved field edits
aren't counted.

Anything else, it's a service question rather than a workflow one — see
the runbook, or ask whoever runs the container.
