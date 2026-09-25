"""Settings and blend-zone workflow definition loading."""

import json
import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("BZ_DB_PATH", BASE_DIR / "data" / "baylog.db"))
UPLOAD_DIR = Path(os.environ.get("BZ_UPLOAD_DIR", BASE_DIR / "data" / "uploads"))
SCHEMA_PATH = Path(os.environ.get("BZ_SCHEMA_PATH", BASE_DIR / "db" / "schema.sql"))
SEED_PATH = Path(os.environ.get("BZ_SEED_PATH", BASE_DIR / "db" / "seed.sql"))
WORKFLOW_PATH = Path(
    os.environ.get("BZ_WORKFLOW_PATH", BASE_DIR / "config" / "workflow.json")
)
STATIC_DIR = BASE_DIR / "app" / "static"

# When 0, the app runs open (useful on a closed lab network and for the
# first walkthrough). When 1, every write requires a valid session token
# issued by the LTI launch.
REQUIRE_AUTH = os.environ.get("BZ_REQUIRE_AUTH", "0") == "1"

# Lets you act as a role without an LTI launch. Off in production.
DEV_AUTH = os.environ.get("BZ_DEV_AUTH", "1") == "1"

# --- Cloudflare Access -------------------------------------------------
# The service is fronted by a Cloudflare Access application. When both of
# these are set, app/cf_access.py verifies the Cf-Access-Jwt-Assertion
# header and derives the actor's role from the verified email address.
# Leave them empty to disable Access identity entirely (local dev, tests).
#
#   BZ_CF_TEAM_DOMAIN  e.g. yourteam.cloudflareaccess.com
#   BZ_CF_ACCESS_AUD   the application's Audience (AUD) tag, from
#                      Zero Trust > Access > Applications > Overview
CF_TEAM_DOMAIN = os.environ.get("BZ_CF_TEAM_DOMAIN", "").strip()
CF_ACCESS_AUD = os.environ.get("BZ_CF_ACCESS_AUD", "").strip()

# Addresses that get the instructor role. Comma-separated. Use this for
# named individuals; use BZ_STAFF_DOMAIN to grant a whole domain.
STAFF_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("BZ_STAFF_EMAILS", "").split(",")
    if e.strip()
}

# Email suffix identifying college faculty/staff, e.g. "@example.edu".
# Everyone matching this gets the instructor role, which includes
# sign-off authority on estimates and QC. That is a broad grant at an
# institution where the suffix covers every employee — prefer
# BZ_STAFF_EMAILS while the list of approvers is small.
#
# The leading "@" is what keeps the two domains apart: an address like
# jdoe@student.example.edu does not end in "@example.edu", so students are never
# caught by the faculty rule. Do not drop it.
STAFF_EMAIL_DOMAIN = os.environ.get("BZ_STAFF_DOMAIN", "").strip().lower()

# Email suffix identifying an enrolled student, e.g. "@student.example.edu".
STUDENT_EMAIL_DOMAIN = os.environ.get("BZ_STUDENT_DOMAIN", "").strip().lower()

# Role given to a request with no session and no Access assertion — i.e.
# the shop-floor bay terminal on the lab LAN.
#
# This used to be hardcoded to "staff", which meant anyone who could
# reach the service could sign off a stage. Now that the service is
# reachable from the internet, the default is a role that cannot sign
# off. Set BZ_ANON_ROLE=staff deliberately if you want an unauthenticated
# kiosk to retain sign-off, and only on a network where that is safe.
ANON_ROLE = os.environ.get("BZ_ANON_ROLE", "viewer").strip() or "viewer"

# Origins allowed to call the API from a page served elsewhere. Empty by
# default, which disables CORS entirely — same-origin only, the normal
# deployment. Set to a comma-separated origin list (or "*") only when the
# frontend is genuinely hosted on another origin, e.g. a preview host.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("BZ_CORS_ORIGINS", "").split(",") if o.strip()
]

SESSION_COOKIE = "bz_session"
SESSION_TTL_HOURS = int(os.environ.get("BZ_SESSION_TTL_HOURS", "12"))

MAX_UPLOAD_BYTES = int(os.environ.get("BZ_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
}


@lru_cache(maxsize=1)
def workflow() -> dict:
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def stages() -> list[dict]:
    return workflow()["stages"]


def stage_map() -> dict[str, dict]:
    return {s["key"]: s for s in stages()}


def stage_keys() -> list[str]:
    return [s["key"] for s in stages()]


def next_stage(stage_key: str) -> str | None:
    keys = stage_keys()
    try:
        idx = keys.index(stage_key)
    except ValueError:
        return None
    return keys[idx + 1] if idx + 1 < len(keys) else None


def prev_stage(stage_key: str) -> str | None:
    keys = stage_keys()
    try:
        idx = keys.index(stage_key)
    except ValueError:
        return None
    return keys[idx - 1] if idx > 0 else None


def signoff_roles() -> set[str]:
    return set(workflow().get("roles", {}).get("signoff_roles", ["instructor", "staff"]))
