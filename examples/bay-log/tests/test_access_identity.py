"""Cloudflare Access identity: signature, audience, and role mapping.

Runs entirely offline. We generate an RSA keypair here, sign our own
assertions with it, and point app.cf_access at a stub JWKS client, so the
test never touches Cloudflare. Run with:

    .venv/bin/python -m tests.test_access_identity
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="baylog-access-test-"))

TEAM = "yourteam.cloudflareaccess.com"
AUD = "a" * 64
OTHER_AUD = "b" * 64
STAFF = "instructor@example.edu"
STAFF_DOMAIN = "@example.edu"
STUDENT_DOMAIN = "@student.example.edu"

# config.py reads the environment at import time, so this has to happen
# before app.* is imported.
os.environ["BZ_DB_PATH"] = str(TMP / "test.db")
os.environ["BZ_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["BZ_DEV_AUTH"] = "0"
os.environ["BZ_REQUIRE_AUTH"] = "0"
os.environ["BZ_CF_TEAM_DOMAIN"] = TEAM
os.environ["BZ_CF_ACCESS_AUD"] = AUD
os.environ["BZ_STAFF_EMAILS"] = STAFF
os.environ["BZ_STAFF_DOMAIN"] = STAFF_DOMAIN
os.environ["BZ_STUDENT_DOMAIN"] = STUDENT_DOMAIN
sys.path.insert(0, str(BASE))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import cf_access, db  # noqa: E402
from app.main import app  # noqa: E402

PASS, FAIL = [], []


def check(label: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(label)
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  -- {detail}" if detail and not condition else ""))


PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()
WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubSigningKey:
    key = PUBLIC_KEY


class _StubJWKClient:
    def get_signing_key_from_jwt(self, token):  # noqa: ANN001
        return _StubSigningKey()


# Replace the real JWKS fetch. cf_access._jwk_client is lru_cached, so
# rebinding the name is enough and nothing reaches the network.
cf_access._jwk_client = _StubJWKClient  # type: ignore[assignment]


def assertion(
    email: str,
    *,
    aud: str = AUD,
    issuer: str = f"https://{TEAM}",
    key=PRIVATE_KEY,
    expired: bool = False,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "aud": [aud],
            "iss": issuer,
            "email": email,
            "sub": f"sub-{email}",
            "iat": now - 60,
            "exp": now - 30 if expired else now + 3600,
        },
        key,
        algorithm="RS256",
    )


def hdr(email: str, **kw) -> dict:
    return {"Cf-Access-Jwt-Assertion": assertion(email, **kw)}


def main() -> int:
    db.init_db()
    client = TestClient(app)

    # --- role mapping ---------------------------------------------------
    r = client.get("/api/me", headers=hdr(STAFF))
    body = r.json() if r.status_code == 200 else {}
    check(
        "staff address is mapped to instructor",
        r.status_code == 200 and body.get("role") == "instructor",
        f"{r.status_code} {r.text[:200]}",
    )
    check(
        "staff actor is marked authenticated",
        bool(body.get("authenticated")),
        str(body),
    )

    student = f"jdoe{STUDENT_DOMAIN}"
    r = client.get("/api/me", headers=hdr(student))
    body = r.json() if r.status_code == 200 else {}
    check(
        "student domain is mapped to student",
        r.status_code == 200 and body.get("role") == "student",
        f"{r.status_code} {r.text[:200]}",
    )
    check(
        "student cannot sign off",
        body.get("can_signoff") is False,
        str(body),
    )

    # --- the two college domains must not bleed into each other ---------
    faculty = f"jsmith{STAFF_DOMAIN}"
    r = client.get("/api/me", headers=hdr(faculty))
    body = r.json() if r.status_code == 200 else {}
    check(
        "faculty domain is mapped to instructor",
        r.status_code == 200 and body.get("role") == "instructor",
        f"{r.status_code} {r.text[:200]}",
    )
    check(
        "faculty can sign off",
        body.get("can_signoff") is True,
        str(body),
    )

    # The leading "@" on BZ_STAFF_DOMAIN is what stops a student address,
    # which also ends in "example.edu", from being read as faculty.
    r = client.get("/api/me", headers=hdr(f"jdoe{STUDENT_DOMAIN}"))
    body = r.json() if r.status_code == 200 else {}
    check(
        "student address is NOT promoted by the faculty domain rule",
        r.status_code == 200 and body.get("role") == "student",
        f"{r.status_code} {r.text[:200]}",
    )

    # Cloudflare's "emails ending in" rule displays without the "@", so a
    # lookalike domain can get through the gate. The app must still
    # refuse it — this is the check that makes the app, not Cloudflare,
    # the authorization boundary.
    for lookalike in (
        "attacker@notexample.edu",
        "attacker@evil-example.edu",
        "attacker@example.edu.example.com",
        "attacker@fakestudent.example.edu",
    ):
        r = client.get("/api/me", headers=hdr(lookalike))
        check(
            f"lookalike domain refused: {lookalike}",
            r.status_code == 403,
            f"{r.status_code} {r.text[:200]}",
        )

    # --- assertions that must be refused --------------------------------
    r = client.get("/api/me", headers=hdr("someone@gmail.com"))
    check(
        "unprovisioned address is refused (403)",
        r.status_code == 403,
        f"{r.status_code} {r.text[:200]}",
    )

    r = client.get("/api/me", headers=hdr(STAFF, aud=OTHER_AUD))
    check(
        "token for another Access app is refused (401)",
        r.status_code == 401,
        f"{r.status_code} {r.text[:200]}",
    )

    r = client.get("/api/me", headers=hdr(STAFF, issuer="https://evil.example.com"))
    check(
        "token from another issuer is refused (401)",
        r.status_code == 401,
        f"{r.status_code} {r.text[:200]}",
    )

    r = client.get("/api/me", headers=hdr(STAFF, key=WRONG_KEY))
    check(
        "token signed by an unknown key is refused (401)",
        r.status_code == 401,
        f"{r.status_code} {r.text[:200]}",
    )

    r = client.get("/api/me", headers=hdr(STAFF, expired=True))
    check(
        "expired token is refused (401)",
        r.status_code == 401,
        f"{r.status_code} {r.text[:200]}",
    )

    r = client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": "not-a-jwt"})
    check(
        "garbage assertion is refused (401)",
        r.status_code == 401,
        f"{r.status_code} {r.text[:200]}",
    )

    # The plain header must not be trusted on its own.
    r = client.get(
        "/api/me", headers={"Cf-Access-Authenticated-User-Email": STAFF}
    )
    body = r.json() if r.status_code == 200 else {}
    check(
        "unsigned Cf-Access email header grants nothing",
        r.status_code == 200 and body.get("role") != "instructor",
        f"{r.status_code} {r.text[:200]}",
    )

    # --- anonymous fallback ---------------------------------------------
    r = client.get("/api/me")
    body = r.json() if r.status_code == 200 else {}
    check(
        "anonymous actor cannot sign off",
        r.status_code == 200 and body.get("can_signoff") is False,
        f"{r.status_code} {r.text[:200]}",
    )
    check(
        "anonymous actor uses BZ_ANON_ROLE, not staff",
        body.get("role") == "viewer",
        str(body),
    )

    # --- no duplicate people rows ---------------------------------------
    for _ in range(3):
        client.get("/api/me", headers=hdr(student))
    with db.ro() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM people WHERE LOWER(email) = ?", (student,)
        ).fetchone()["n"]
    check("repeat requests reuse one people row", n == 1, f"rows={n}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("Failed: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
