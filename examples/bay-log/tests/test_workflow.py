"""End-to-end exercise of the Bay Log service.

Walks a repair order through every stage gate, proving that the gates
actually block and that satisfying them unblocks the advance. Run with:
    .venv/bin/python -m tests.test_workflow
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="baylog-test-"))
os.environ["BZ_DB_PATH"] = str(TMP / "test.db")
os.environ["BZ_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["BZ_DEV_AUTH"] = "1"
os.environ["BZ_REQUIRE_AUTH"] = "0"
sys.path.insert(0, str(BASE))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASS, FAIL = [], []


def check(label: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(label)
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  -- {detail}" if detail and not condition else ""))


def png_bytes() -> bytes:
    # Smallest valid 1x1 PNG.
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def main() -> int:
    with TestClient(app) as c:
        # ---------- meta ----------
        h = c.get("/api/health").json()
        check("health reports ok", h.get("status") == "ok", str(h))

        cfg = c.get("/api/config").json()
        check("config exposes 7 Bay Log stages", len(cfg["stages"]) == 7,
              str([s["key"] for s in cfg["stages"]]))
        check("subject label is Vehicle", cfg["subject_label"] == "Vehicle")

        # ---------- seed ----------
        tickets = c.get("/api/tickets").json()
        check("seed loaded 3 repair orders", len(tickets) == 3, str(len(tickets)))
        kb = c.get("/api/kb").json()
        check("seed loaded knowledge base", len(kb) >= 5, str(len(kb)))
        res = c.get("/api/resources").json()
        check("seed loaded parts catalog", len(res) >= 10, str(len(res)))
        board = c.get("/api/board").json()
        check("status board view works", len(board) == 3, str(len(board)))

        # ---------- roles ----------
        student = c.get("/api/me", params={"as": "student"}).json()
        check("student cannot sign off", student["can_signoff"] is False)
        instr = c.get("/api/me", params={"as": "instructor"}).json()
        check("instructor can sign off", instr["can_signoff"] is True)

        # ---------- create ----------
        created = c.post("/api/tickets", json={
            "subject_label": "2019 Toyota Camry LE",
            "subject_attributes": {"vin": "4T1B11HK9KU000444", "mileage": 61240},
            "title": "Overheating on the freeway",
            "priority": "rush",
            "stage_data": {"complaint": "Temp gauge climbing", "mileage_in": 61240},
        })
        check("create returns 201", created.status_code == 201, created.text[:200])
        t = created.json()
        tid = t["ticket_id"]
        check("ticket id follows T- sequence", tid.startswith("T-"), tid)
        check("new ticket starts at intake", t["stage_key"] == "intake", t["stage_key"])
        check("intake requirements satisfied at creation", t["blockers"] == [],
              str(t["blockers"]))

        # ---------- gate: intake -> diagnosis ----------
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("advance intake -> diagnosis", r.status_code == 200, r.text[:200])
        check("now at diagnosis", r.json()["stage_key"] == "diagnosis")

        # ---------- gate blocks without findings ----------
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("diagnosis gate blocks with no findings", r.status_code == 422,
              f"got {r.status_code}")
        blockers = r.json()["detail"]["blockers"]
        check("blocker names the missing field",
              any("Diagnostic findings" in b for b in blockers), str(blockers))

        # ---------- satisfy, then advance ----------
        r = c.put(f"/api/tickets/{tid}/stage-data", json={"data": {
            "findings": "Radiator seeping at the lower seam under 15 psi.",
            "codes": "none"}})
        check("stage data saved", r.status_code == 200, r.text[:200])
        check("saving clears the blocker", r.json()["blockers"] == [],
              str(r.json()["blockers"]))
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("advance to estimate_approval", r.json()["stage_key"] == "estimate_approval")

        # ---------- signoff gate ----------
        r = c.put(f"/api/tickets/{tid}/stage-data",
                  json={"data": {"estimate_hours": 3, "estimate_parts": 240}})
        blockers = r.json()["blockers"]
        check("signoff still required after fields filled",
              any("sign-off" in b for b in blockers), str(blockers))

        r = c.post(f"/api/tickets/{tid}/signoff", json={}, params={"as": "student"})
        check("student sign-off rejected with 403", r.status_code == 403,
              f"got {r.status_code}")

        r = c.post(f"/api/tickets/{tid}/signoff", json={}, params={"as": "instructor"})
        check("instructor sign-off accepted", r.status_code == 200, r.text[:200])
        check("signoff clears the gate", r.json()["blockers"] == [],
              str(r.json()["blockers"]))

        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("advance to in_bay", r.json()["stage_key"] == "in_bay")

        # ---------- resources + kb links ----------
        r = c.post(f"/api/tickets/{tid}/resources", json={"resource_id": 1, "quantity": 5})
        check("parts recorded against ticket", len(r.json()["resources"]) == 1)
        r = c.post(f"/api/tickets/{tid}/kb-links", json={"entry_id": 4})
        check("kb entry linked", len(r.json()["knowledge_links"]) == 1)

        c.put(f"/api/tickets/{tid}/stage-data", json={"data": {
            "work_performed": "Replaced radiator, refilled and bled coolant.",
            "actual_hours": 3.5}})
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("advance to qc_inspection", r.json()["stage_key"] == "qc_inspection")

        # ---------- attachment gate ----------
        r = c.put(f"/api/tickets/{tid}/stage-data", json={"data": {
            "inspection_notes": "No leaks after 20 minute road test.", "road_tested": True}})
        blockers = r.json()["blockers"]
        check("QC needs both signoff and a photo", len(blockers) == 2, str(blockers))

        r = c.post(f"/api/tickets/{tid}/attachments",
                   files={"file": ("bay.txt", io.BytesIO(b"nope"), "text/plain")})
        check("wrong file type rejected with 415", r.status_code == 415,
              f"got {r.status_code}")

        r = c.post(f"/api/tickets/{tid}/attachments",
                   files={"file": ("repair.png", io.BytesIO(png_bytes()), "image/png")})
        check("photo upload accepted", r.status_code == 201, r.text[:200])
        aid = r.json()["attachment_id"]
        r = c.get(f"/api/attachments/{aid}")
        check("photo downloads back", r.status_code == 200 and r.content == png_bytes())

        c.post(f"/api/tickets/{tid}/signoff", json={}, params={"as": "instructor"})
        r = c.get(f"/api/tickets/{tid}")
        check("QC gate fully satisfied", r.json()["blockers"] == [], str(r.json()["blockers"]))

        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("advance to ready", r.json()["stage_key"] == "ready")

        # ---------- revert preserves prior work ----------
        r = c.post(f"/api/tickets/{tid}/revert")
        check("revert goes back to qc_inspection", r.json()["stage_key"] == "qc_inspection")
        check("reverted stage keeps its earlier notes",
              "road test" in str(r.json()["stage_data"].get("inspection_notes", "")),
              str(r.json()["stage_data"]))
        c.post(f"/api/tickets/{tid}/advance", json={"force": False})

        # ---------- close ----------
        c.put(f"/api/tickets/{tid}/stage-data", json={"data": {"customer_notified": True}})
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        final = r.json()
        check("advance to closed", final["stage_key"] == "closed", final["stage_key"])
        check("closing marks the ticket done", final["done"] is True)
        check("closed_at stamped", bool(final["closed_at"]))
        r = c.post(f"/api/tickets/{tid}/advance", json={"force": False})
        check("cannot advance past the final stage", r.status_code == 409,
              f"got {r.status_code}")

        # ---------- audit trail ----------
        rec = c.get(f"/api/tickets/{tid}").json()
        stages_seen = [h["stage_key"] for h in rec["history"]]
        check("history captured every stage entry", len(stages_seen) == 9,
              str(stages_seen))
        check("full record retains both sign-offs", len(rec["signoffs"]) == 2,
              str(rec["signoffs"]))

        # ---------- clarity tiers ----------
        line = c.get(f"/api/tickets/{tid}/summary", params={"tier": "line"}).json()
        check("1-line tier mentions ticket and stage",
              tid in line["text"] and "Closed" in line["text"], line["text"])
        para = c.get(f"/api/tickets/{tid}/summary", params={"tier": "paragraph"}).json()
        check("1-paragraph tier lists completed stages",
              "Completed stages" in para["text"], para["text"][:160])
        full = c.get(f"/api/tickets/{tid}/summary", params={"tier": "full"}).json()
        check("full tier returns the whole record", "record" in full)
        r = c.get(f"/api/tickets/{tid}/summary", params={"tier": "bogus"})
        check("bad tier rejected", r.status_code == 422)

        # ---------- force override ----------
        t2 = c.post("/api/tickets", json={
            "subject_label": "2008 Chevy Silverado",
            "stage_data": {"complaint": "Brake pull", "mileage_in": 210000}}).json()
        c.post(f"/api/tickets/{t2['ticket_id']}/advance", json={"force": False})
        r = c.post(f"/api/tickets/{t2['ticket_id']}/advance",
                   json={"force": True}, params={"as": "student"})
        check("student cannot force past a gate", r.status_code == 403, f"got {r.status_code}")
        r = c.post(f"/api/tickets/{t2['ticket_id']}/advance",
                   json={"force": True}, params={"as": "instructor"})
        check("instructor can force past a gate", r.status_code == 200, r.text[:200])

        # ---------- 404s ----------
        check("unknown ticket 404s", c.get("/api/tickets/T-9999").status_code == 404)

        # ---------- frontend served ----------
        r = c.get("/")
        check("frontend shell served", r.status_code == 200 and "bz-root" in r.text)

        # ---------- LTI mount ----------
        from app.asgi import LTI_MOUNTED
        check("LTI provider mounts", LTI_MOUNTED is True)

    print("\n" + "=" * 56)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
