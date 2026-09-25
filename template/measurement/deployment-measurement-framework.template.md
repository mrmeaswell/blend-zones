# [Tool Name] Deployment Measurement Framework

Generalized from the Emile Deployment Measurement Framework. Measures a
blend-zone tool *as a tool* — reliability, adoption, cost, quality — as
it moves from a single builder's use toward wider departmental or
cross-college deployment. This is deliberately separate from any
curriculum, student-outcome, or grant-required evaluation plan: a tool
can be healthy long before any outcome data exists downstream of it, and
this framework should start collecting data from first real use,
independent of any grant or proposal timeline.

*Bay Log example callouts (in italics) show what each line looks like
for a real blend-zone tool — replace them with your own tool's specifics.*

---

## 1. Deployment Phases

| Phase | Description | Primary question this framework answers |
|---|---|---|
| Phase 0 — Builder use | The tool serves its own builder/department only | Does it actually work and save time for the person who built it? |
| Phase 1 — Pilot | A second user or the named handoff-pair's department uses it for real work | Does it hold up outside the builder's own hands? |
| Phase 2 — Embedded | Used routinely as part of the department's actual workflow | Is it reliable and cost-sustainable at repeated use? |
| Phase 3 — Scaled | Used beyond the original department, or offered to other colleges | Does usage and quality justify investment beyond the original blend zone? |

*Bay Log: Phase 0 was the builder testing solo. Phase 1 begins once
Automotive instructors and students start logging real work orders.*

Track each metric group starting in whichever phase you're actually in —
don't wait for Phase 2 to start logging Phase 0 data.

---

## 2. Output Quality

Whether the tool's output is actually good, independent of who used it.

- **Structural fidelity rate** — % of outputs that follow the intended
  structure/workflow without manual correction.
  *Bay Log: % of work orders that reach Pickup without a stage rollback.*
- **Human-edit/correction rate** — % of outputs requiring substantive
  correction before use (distinguish *substantive* — content/logic
  changes — from *cosmetic*). A high substantive rate signals a
  tool/template problem, not a user problem.
- **Export/handoff success rate** — % of exports, launches, or handoffs
  (LTI launches, file exports, API calls to another system) that
  complete cleanly without manual repair.
  *Bay Log: % of Canvas LTI launches that complete without a validation
  error.*
- **Review/approval acceptance rate** — where the tool produces
  something a human signs off on, % accepted unmodified.

## 3. Technical Reliability

- **API/uptime availability** — % of requests that complete
  successfully, tracked per backend/dependency where relevant.
- **Latency** — median and p95 time from request to completed action.
- **Error rate by failure type** — categorized (timeout, backend
  unavailable, validation failure, export failure) so recurring issues
  are visible, not just a single error count.

## 4. Adoption & Usage

- **Active users** — distinct people using the tool per month
  (meaningful starting Phase 1).
- **Throughput per period** — raw usage volume, segmented by
  course/department/workflow if more than one exists.
- **Repeat-use rate** — % of users who use it again within 30 days of
  their first use (signals real adoption vs. one-time curiosity).
- **Coverage breadth** — how many distinct courses/departments/workflows
  the tool has touched vs. the total it could plausibly serve.

## 5. Efficiency & Cost

- **Time-to-complete per unit of work** — benchmarked against the manual
  baseline it replaces.
  *Bay Log: ticket creation-to-close time vs. a paper work-order baseline.*
- **Hours saved (estimated)** — (baseline time − tool-assisted time) ×
  volume. This is the strongest ROI number for any funding conversation.
- **Cost per unit processed** — infrastructure/API cost ÷ volume, if
  running against metered infrastructure (LLM API calls, hosted compute).
- **Infrastructure cost per active user** — relevant once past Phase 0,
  to catch a tool that works but doesn't scale affordably.

## 6. Governance & Compliance

Whatever policy commitments the tool makes (data handling, AI-authorship
disclosure, access control) should be checked, not assumed.

- **Disclosure/compliance completion rate** — % of outputs or
  interactions that carry the correct disclosure/attribution/compliance
  marker before distribution or use.
- **Policy exceptions logged** — any case where the tool was used
  outside its stated policy, tracked as an incident, not silently
  corrected.

## 7. Review Cadence

- **Monthly (informal):** quick look at usage, correction rate, and any
  recurring error types — 15 minutes, to catch drift early.
- **Quarterly (structured):** a full pass through all six metric groups,
  written down even briefly, so phase transitions are backed by data.
- **Phase-gate review:** before advancing a phase (inviting more users,
  embedding into a formal deliverable), review adoption, reliability,
  and cost explicitly — these numbers justify wider exposure or reveal
  it's premature.

---

## 8. What's deliberately excluded

- Student pass rates, grades, or learning-outcome scores — those belong
  to a curriculum evaluation plan, not to the tool itself.
- Anything already covered by a grant-required third-party evaluator
  budget line — this framework runs independently and at zero
  incremental cost, tracking tool health, not program outcomes.
