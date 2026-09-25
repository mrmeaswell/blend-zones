"""Identity from the Cloudflare Access gate in front of this service.

baylog.example.com sits behind a Cloudflare Access application, so every
request that arrives through the tunnel has already been authenticated by
Cloudflare against an identity provider (one-time PIN today, Entra ID
later). Cloudflare forwards two things:

    Cf-Access-Authenticated-User-Email   plain header, convenient
    Cf-Access-Jwt-Assertion              signed JWT, trustworthy

We validate the JWT rather than reading the plain header. The header is
fine when the origin is genuinely only reachable through the tunnel, but
verifying the signature means a misconfigured nginx, a second ingress
route, or someone on the lab LAN can't simply set a header and become an
instructor.

Two checks matter and are easy to get wrong:

  * ``audience`` must be this application's AUD tag. Without it, a token
    minted for any *other* Access application on the same Cloudflare
    account would validate here.
  * ``issuer`` must be the team domain, which is what ties the token to
    this Zero Trust account.

If BZ_CF_TEAM_DOMAIN / BZ_CF_ACCESS_AUD are unset, Access identity is
simply inactive and the service behaves as it did before — that keeps
local development and the test suite working with no Cloudflare at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request

from . import config

log = logging.getLogger("blendzone.cf_access")

ASSERTION_HEADER = "cf-access-jwt-assertion"
EMAIL_HEADER = "cf-access-authenticated-user-email"


def enabled() -> bool:
    """True when we have enough configuration to verify an assertion."""
    return bool(config.CF_TEAM_DOMAIN and config.CF_ACCESS_AUD)


@dataclass(frozen=True)
class AccessIdentity:
    """A Cloudflare-verified identity. ``role`` is derived, never claimed."""

    email: str
    subject: str
    role: str


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    # PyJWKClient keeps its own key cache, so Cloudflare's JWKS endpoint is
    # not refetched per request.
    return jwt.PyJWKClient(
        f"https://{config.CF_TEAM_DOMAIN}/cdn-cgi/access/certs",
        cache_keys=True,
    )


def role_for_email(email: str) -> str | None:
    """Map a verified address to a role, or None if we don't recognise it.

    Returning None rather than a default is deliberate: if the Access
    policy is later widened, unknown addresses should be refused here
    instead of silently inheriting whatever the fallback role happens to
    be. This function is the real authorization boundary — Cloudflare
    decides who gets through the door, this decides who they are.

    Order matters. The student check runs last, but the two domain rules
    cannot overlap anyway because both are anchored on "@":
    jdoe@student.example.edu does not end in "@example.edu".
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None

    if email in config.STAFF_EMAILS:
        return "instructor"

    staff_domain = config.STAFF_EMAIL_DOMAIN
    if staff_domain and email.endswith(staff_domain):
        return "instructor"

    student_domain = config.STUDENT_EMAIL_DOMAIN
    if student_domain and email.endswith(student_domain):
        return "student"

    return None


def identity_from_request(request: Request) -> AccessIdentity | None:
    """Verified Access identity, or None when the request didn't come
    through the Access gate (direct LAN access, tests, local dev).

    Raises 401/403 only when an assertion *is* present but unusable — a
    bad assertion is an error worth surfacing, whereas no assertion just
    means this code path doesn't apply.
    """
    token = request.headers.get(ASSERTION_HEADER)
    if not token:
        return None

    if not enabled():
        # An assertion arrived but we can't check it. Refusing to trust it
        # is the safe move; falling back to the plain email header here
        # would accept anything a client cared to send.
        log.warning(
            "Access assertion received but BZ_CF_TEAM_DOMAIN / "
            "BZ_CF_ACCESS_AUD are unset; ignoring it."
        )
        return None

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.CF_ACCESS_AUD,
            issuer=f"https://{config.CF_TEAM_DOMAIN}",
        )
    except jwt.PyJWTError as exc:
        log.warning("Rejected Access assertion: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Cloudflare Access assertion failed verification.",
        ) from exc

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Access assertion carried no email claim.",
        )

    role = role_for_email(email)
    if role is None:
        # Authenticated by Cloudflare, but not provisioned for this tool.
        raise HTTPException(
            status_code=403,
            detail=f"{email} is not provisioned for Bay Log.",
        )

    return AccessIdentity(email=email, subject=claims.get("sub", ""), role=role)
