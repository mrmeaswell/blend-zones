"""Session handling and actor resolution.

An actor can be identified three ways, checked in this order:

1. A session token minted by the LTI launch (app/lti_app.py), stored in
   the app_sessions table so the Flask LTI sub-app and the FastAPI app
   share identity through the database rather than a shared cookie
   secret.
2. A Cloudflare Access assertion (app/cf_access.py), verified against
   the Zero Trust team JWKS. The role is derived from the verified email
   address, so the caller cannot choose it.
3. Nothing at all — the shop-floor bay terminal on the lab LAN, which
   gets config.ANON_ROLE.

The BZ_DEV_AUTH role override still exists for local development, but is
now consulted only when neither of the first two produced an actor.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from . import cf_access, config, db


@dataclass
class Actor:
    person_id: int | None
    name: str
    role: str
    course: str | None = None
    authenticated: bool = False

    def can_signoff(self) -> bool:
        return self.role in config.signoff_roles()


def anonymous() -> Actor:
    """The unauthenticated bay-terminal actor.

    Built per call rather than kept as a module constant so that changing
    BZ_ANON_ROLE doesn't depend on import order. The role is deliberately
    not "staff" by default — see config.ANON_ROLE for why.
    """
    return Actor(
        person_id=None,
        name="Bay terminal",
        role=config.ANON_ROLE,
        authenticated=False,
    )


# Retained for anything that imported the old constant.
ANONYMOUS = anonymous()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_session(person_id: int, role: str, course: str | None) -> str:
    token = secrets.token_urlsafe(32)
    expires = (_utcnow() + timedelta(hours=config.SESSION_TTL_HOURS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with db.tx() as conn:
        conn.execute("DELETE FROM app_sessions WHERE expires_at < datetime('now')")
        conn.execute(
            "INSERT INTO app_sessions (token, person_id, role, course, expires_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (token, person_id, role, course, expires),
        )
    return token


def upsert_person(name: str, role: str, email: str | None, lti_sub: str | None) -> int:
    """Find or create a person, returning their person_id.

    Matches on lti_sub when present (immutable per tool+user), then falls
    back to email. The email fallback matters for Cloudflare Access
    identity, which has no lti_sub: without it, every authenticated
    request would insert a fresh duplicate row.
    """
    with db.tx() as conn:
        row = None
        if lti_sub:
            row = conn.execute(
                "SELECT person_id FROM people WHERE lti_sub = ?", (lti_sub,)
            ).fetchone()
        if row is None and email:
            row = conn.execute(
                "SELECT person_id FROM people WHERE LOWER(email) = LOWER(?)",
                (email,),
            ).fetchone()

        if row:
            conn.execute(
                "UPDATE people SET name = ?, role = ?,"
                " email = COALESCE(?, email),"
                " lti_sub = COALESCE(?, lti_sub)"
                " WHERE person_id = ?",
                (name, role, email, lti_sub, row["person_id"]),
            )
            return int(row["person_id"])

        cur = conn.execute(
            "INSERT INTO people (name, role, email, lti_sub) VALUES (?, ?, ?, ?)",
            (name, role, email, lti_sub),
        )
        return int(cur.lastrowid)


def resolve_token(token: str) -> Actor | None:
    with db.ro() as conn:
        row = conn.execute(
            """
            SELECT s.person_id, s.role, s.course, p.name
            FROM app_sessions s JOIN people p ON p.person_id = s.person_id
            WHERE s.token = ? AND s.expires_at >= datetime('now')
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    return Actor(
        person_id=row["person_id"],
        name=row["name"],
        role=row["role"],
        course=row["course"],
        authenticated=True,
    )


def actor_from_access(request: Request) -> Actor | None:
    """Actor derived from a verified Cloudflare Access assertion."""
    identity = cf_access.identity_from_request(request)
    if identity is None:
        return None

    display = identity.email.split("@", 1)[0]
    person_id = upsert_person(
        name=display,
        role=identity.role,
        email=identity.email,
        lti_sub=None,
    )
    return Actor(
        person_id=person_id,
        name=display,
        role=identity.role,
        authenticated=True,
    )


def current_actor(request: Request) -> Actor:
    """FastAPI dependency.

    Order: LTI session, then Cloudflare Access assertion, then the dev
    role override, then the anonymous bay terminal.
    """
    token = request.cookies.get(config.SESSION_COOKIE) or request.headers.get(
        "x-bz-session"
    )
    if token:
        actor = resolve_token(token)
        if actor:
            return actor

    # Verified identity from the Access gate. This raises on a malformed
    # assertion or an address that isn't provisioned, so a deliberately
    # broken header can't be used to fall through to a weaker path.
    actor = actor_from_access(request)
    if actor:
        return actor

    if config.REQUIRE_AUTH:
        raise HTTPException(
            status_code=401,
            detail="No valid session. Launch this tool from Canvas.",
        )

    if config.DEV_AUTH:
        role = request.headers.get("x-bz-role") or request.query_params.get("as")
        if role in {"student", "instructor", "staff", "advisor"}:
            return Actor(
                person_id=None, name=f"Dev {role}", role=role, authenticated=False
            )

    return anonymous()


def require_signoff_role(actor: Actor) -> None:
    if not actor.can_signoff():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{actor.role}' cannot sign off. "
                f"Allowed: {', '.join(sorted(config.signoff_roles()))}."
            ),
        )
