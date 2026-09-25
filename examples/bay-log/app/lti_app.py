"""LTI 1.3 tool provider, mounted into the FastAPI service at /lti.

Evolved from blend-zone-template/lti/app.py. The material change: /launch
no longer prints the user's name. It resolves the launch into a person
row, mints an app session, and redirects into the tool — which is what
makes Canvas launch actually land somewhere useful.

Canvas Developer Key URLs (note the /lti prefix):
  OpenID Connect Initiation URL:  https://<host>/lti/login
  Target Link URI:                https://<host>/lti/launch
  Public JWK URL:                 https://<host>/lti/jwks
"""

import json
import os
from pathlib import Path

from flask import Flask, redirect, request
from flask_caching import Cache
from pylti1p3.contrib.flask import (
    FlaskCacheDataStorage,
    FlaskMessageLaunch,
    FlaskOIDCLogin,
    FlaskRequest,
)
from pylti1p3.tool_config import ToolConfJsonFile

from . import auth, config

BASE_DIR = Path(__file__).resolve().parent.parent
TOOL_CONF_FILE = os.environ.get("BZ_LTI_CONFIG", str(BASE_DIR / "config" / "lti_config.json"))

flask_app = Flask(__name__)
flask_app.secret_key = os.environ.get("BZ_SECRET_KEY", "change-me-in-production")
flask_app.config["CACHE_TYPE"] = "FileSystemCache"
flask_app.config["CACHE_DIR"] = str(config.DB_PATH.parent / "lti_cache")
flask_app.config["CACHE_DEFAULT_TIMEOUT"] = 600
cache = Cache(flask_app)

# Canvas role URNs -> the roles this app understands
ROLE_MAP = {
    "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor": "instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor": "instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper": "instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator": "staff",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#TeachingAssistant": "staff",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor": "advisor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner": "student",
}


def _tool_conf() -> ToolConfJsonFile:
    return ToolConfJsonFile(TOOL_CONF_FILE)


def _storage():
    return FlaskCacheDataStorage(cache)


def _map_role(roles: list[str]) -> str:
    """Most privileged role wins."""
    mapped = {ROLE_MAP.get(r) for r in roles} - {None}
    for candidate in ("instructor", "staff", "advisor", "student"):
        if candidate in mapped:
            return candidate
    return "student"


@flask_app.get("/health")
def lti_health():
    """Confirms the LTI config parses and keys are present, without
    exposing anything sensitive."""
    try:
        conf = _tool_conf()
        jwks = conf.get_jwks()
        n = len(jwks.get("keys", []))
        return {"status": "ok" if n else "no-keys", "jwk_count": n}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}, 503


@flask_app.route("/login", methods=["GET", "POST"])
def login():
    """Step 1: Canvas redirects the browser here (OIDC initiation)."""
    flask_request = FlaskRequest()
    target_link_uri = flask_request.get_param("target_link_uri")
    if not target_link_uri:
        return 'Missing "target_link_uri" param', 400

    oidc_login = FlaskOIDCLogin(
        flask_request, _tool_conf(), launch_data_storage=_storage()
    )
    return oidc_login.enable_check_cookies().redirect(target_link_uri)


@flask_app.route("/launch", methods=["POST"])
def launch():
    """Step 2: Canvas POSTs a signed JWT. Validate it, resolve identity,
    mint a session, and hand off into the tool."""
    message_launch = FlaskMessageLaunch(
        FlaskRequest(), _tool_conf(), launch_data_storage=_storage()
    )
    data = message_launch.get_launch_data()

    sub = data.get("sub")
    name = data.get("name") or data.get("email") or "Canvas user"
    email = data.get("email")
    roles = data.get("https://purl.imsglobal.org/spec/lti/claim/roles", []) or []
    context = data.get("https://purl.imsglobal.org/spec/lti/claim/context", {}) or {}
    course = context.get("title")

    role = _map_role(roles)
    person_id = auth.upsert_person(name=name, role=role, email=email, lti_sub=sub)
    token = auth.create_session(person_id=person_id, role=role, course=course)

    # The tool reads ?session= once, then stores it as an HttpOnly cookie.
    return redirect(f"/?session={token}", code=302)


@flask_app.route("/jwks", methods=["GET"])
def jwks():
    """Canvas fetches this to verify the tool's signature."""
    return json.dumps(_tool_conf().get_jwks()), 200, {"Content-Type": "application/json"}
