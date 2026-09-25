# Blend Zones

A blend zone is the handoff point where one department owns a real
operational workflow and another department (usually IT or CS) builds and
runs the tool behind it. This repo holds the reusable pattern and one worked
example.

```
template/              Blend-Zone Tool Template: brief, schema, UI shell,
                       Canvas LTI 1.3 scaffold, and a versioned measurement module
examples/bay-log/      Reference implementation: a stage-gated work-order
                       tracker for an automotive teaching bay (FastAPI + SQLite,
                       LTI 1.3, Cloudflare Access roles, Proxmox LXC deploy)
```

## Start here

1. Fill out `template/docs/project-brief.template.md` with the two
   departments, a named handoff pair, and the stage list.
2. Copy `template/` for a new tool, or fork `examples/bay-log/` and edit
   `config/workflow.json` if the workflow fits a stage-gated ticket model.
3. Copy each `.env.example` to `.env` (or `/etc/blendzone.env` on a server)
   and fill in your values. Generate LTI keys with the included
   `generate_keys.py`; keys, `.env` files and databases are gitignored.

Names, domains (`example.edu`, `example.com`) and addresses
(`192.0.2.x`) are placeholders.

## Copyright

Copyright (c) 2026 Blended Knowledge LLC. All rights reserved. No license is
granted; see `CITATION.cff` to cite this work.
