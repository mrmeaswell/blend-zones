#!/usr/bin/env python3
"""Build a static preview bundle of the Bay Log frontend.

The normal deployment serves index.html from the app itself, same-origin.
This produces a copy that can be hosted anywhere and pointed at the API on
another origin -- useful for showing the tool to someone who cannot reach
the container's private lab address.

Two rewrites happen:

1. window.BZ_API_BASE is injected, so the UI prefixes every API path with
   it. A relative prefix (the preview host's "port/8080" style proxy) stays
   same-origin and needs nothing else. A full origin
   ("https://baylog.example.edu") is cross-origin and additionally needs
   that origin listed in the API's BZ_CORS_ORIGINS.
2. window.sessionStorage is replaced with null. Preview iframes forbid
   storage APIs; the app's store wrapper already falls back to memory when
   access throws, so nulling it out makes the preview memory-only rather
   than broken.

Usage:
    python scripts/build-preview.py <api-base> [out-dir]
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "index.html"
ANCHOR = "<script>\n(function () {"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    api_base = sys.argv[1].rstrip("/")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT.parent / "preview"

    html = SRC.read_text()
    if html.count(ANCHOR) != 1:
        print(f"error: expected exactly one script anchor in {SRC}")
        return 1

    html = html.replace(
        ANCHOR,
        f'<script>window.BZ_API_BASE = "{api_base}";</script>\n'
        "<script>\n(function () {",
        1,
    )

    # Let the store wrapper's try/except take over.
    storage_hits = html.count("window.sessionStorage")
    html = html.replace("window.sessionStorage", "null")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "index.html").write_text(html)

    print(f"wrote {out / 'index.html'}")
    print(f"  api base:        {api_base}")
    print(f"  storage nulled:  {storage_hits} reference(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
