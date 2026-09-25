# Blend-Zone Tool Template

A starting point for the next tool built at a "blend zone" — where IT's
build/maintain capability meshes with another department's real operational
workflow. Bay Log (an automotive teaching bay) was the first one; this is the reusable
shape it was pulled out of.

## Before you build anything: fill out the brief

Start with `docs/project-brief.template.md`. Don't skip this — it's what
keeps the tool scoped to a real handoff point instead of sprawling into a
full department system. Every blend-zone tool needs:

- The two sides of the mesh (who owns the workflow, who owns the build)
- A named handoff pair, not a committee
- The stage list specific to that workflow
- The three clarity-summary tiers (1-line / 1-paragraph / full record)

## What's in this template

```
blend-zone-template/
├── README.md                          — this file
├── docs/
│   ├── project-brief.template.md      — fill this out first
│   └── instructor-guide.template.md   — end-user how-to, once the tool exists
├── db/
│   ├── schema.template.sql            — generic ticket/knowledge-base/resource schema
│   └── init-db.sh                     — one command to stand up a local SQLite DB
├── app/
│   └── index.template.html            — generic POS-style shell (no build step needed)
├── ai/
│   └── tutor-instructions.template.md — Copilot Studio Socratic-tutor pattern
└── lti/
    ├── app.py                         — pylti1p3 Flask starter (login/launch/jwks)
    ├── generate_keys.py               — creates the RSA keypair Canvas needs
    ├── lti_config.json                — fill in Client ID + Deployment ID from Canvas
    ├── requirements.txt
    └── README.md                      — setup + Canvas Developer Key wiring
measurement/
    ├── deployment-measurement-framework.template.md — phase-gated tool health framework
    ├── schema.sql                     — event + manual-log tables
    ├── logger.py                      — logging helpers (log_event, log_manual_entry)
    ├── dashboard_blueprint.py         — drop-in Flask blueprint, /measurement/dashboard
    └── README.md                      — wiring instructions + worked example
```

## How to fork this for a new blend zone

1. Copy the whole folder, rename it after the new tool.
2. Fill out `docs/project-brief.template.md` first — this drives everything else.
3. In `db/schema.template.sql`: replace the `stages` seed rows with your
   workflow's actual stages, rename `subjects` to whatever the tracked
   thing is (a device, a project, a request — not always a vehicle).
4. In `app/index.template.html`: update `STAGES` to match, and add
   whatever domain-specific fields each stage needs (the template ships
   with one generic notes field per stage as a placeholder).
5. If it needs a tutor/assistant layer, adapt `ai/tutor-instructions.template.md`.
6. Once the workflow is proven out as an artifact, move to real hosting
   (local machine first via SQLite, then wherever it needs to be reachable
   from — Canvas, Power Automate, etc.) — same sequence Bay Log followed.
7. If it needs to launch from inside Canvas, set up `lti/` — it's the
   pylti1p3 starter that actually speaks the LTI 1.3 protocol Canvas
   requires (registering a Developer Key in Canvas alone isn't enough;
   the tool itself has to answer the login/launch/JWK handshake).
8. Wire in `measurement/` once the tool has a real Flask app to attach
   it to — it tracks tool health (reliability, adoption, cost) starting
   from first real use, independent of any grant/proposal timeline.
