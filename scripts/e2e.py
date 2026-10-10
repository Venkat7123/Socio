"""End-to-end test of phases 1-4 against a running API (default http://localhost:8000).

Needs the API running with GROQ_API_KEY set and test images served at IMG_BASE. A full run makes about 9 model calls.
    python scripts/e2e.py
"""
import os
import sqlite3
import sys
from pathlib import Path

import httpx

API = os.environ.get("API", "http://localhost:8000")
IMG = os.environ.get("IMG_BASE", "http://localhost:8001")
MODE = os.environ.get("E2E_MODE", "live Groq")  # set E2E_MODE="stand-in model" when the API runs with fake model calls
ROOT = Path(__file__).resolve().parent.parent
LAT, LNG = 13.0835, 80.2720  # Track C ward W-12 scenario point P2 (Chennai)
PIN = {"lat": LAT, "lng": LNG, "ward": "W-12"}
NEAR = {"lat": LAT + 0.0002, "lng": LNG}  # ~22 m
FAR = {"lat": LAT + 0.002, "lng": LNG}  # ~222 m

http = httpx.Client(base_url=API, timeout=90)
results: list[tuple[str, str, bool, str]] = []


def check(phase: str, name: str, ok: bool, detail: str = "") -> None:
    results.append((phase, name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {phase} | {name}" + (f"  ->  {detail}" if detail else ""))


def post(path, **body):
    return http.post(path, json=body)


def msg(case_id, frm, typ, target=None, refs=(), reason="because"):
    body = {"from_agent": frm, "type": typ, "reason": reason, "evidence": [{"kind": "registry", "ref": r} for r in refs]}
    if target:
        body["target_department"] = target
    return http.post(f"/cases/{case_id}/messages", json=body)


def new_case(desc="Pipe leaking", cat="water_leak", sev="high"):
    r = post("/cases", category=cat, severity=sev, description=desc, location=PIN, citizen_ref="cit_e2e")
    return r.json()["id"]


def status(case_id):
    return http.get(f"/cases/{case_id}").json()["status"]


# ---------------------------------------------------------------- Phase 1
P = "Phase 1 contracts+stubs"
check(P, "API healthy", http.get("/health").json() == {"ok": True})
paths = set(http.get("/openapi.json").json()["paths"])
need = {"/cases", "/cases/{case_id}", "/cases/{case_id}/messages", "/cases/{case_id}/audit", "/cases/{case_id}/verify",
        "/cases/{case_id}/confirm", "/intake", "/analytics/hotspots"}
check(P, "OpenAPI lists every endpoint", need <= paths, f"{len(paths)} paths")
schemas = sorted(p.name for p in (ROOT / "contracts" / "schemas").glob("*.schema.json"))
check(P, "JSON schemas committed to /contracts", len(schemas) >= 10, f"{len(schemas)} schemas")
check(P, "endpoints.md + sample_messages.md present",
      (ROOT / "contracts/endpoints.md").exists() and (ROOT / "contracts/sample_messages.md").exists())
db = sqlite3.connect(ROOT / "backend" / "devfest.db")
tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
check(P, "Database tables created", {"cases", "media", "messages", "audit_log"} <= tables, ", ".join(sorted(t for t in tables if not t.startswith("sqlite"))))
h = http.get("/analytics/hotspots").json()["hotspots"]
check(P, "Hotspots stub returns sample JSON", len(h) > 0, f"{len(h)} rows (stub)")

# ---------------------------------------------------------------- Phase 2
P = "Phase 2 engine"
c1 = new_case()
cs = http.get(f"/cases/{c1}").json()
check(P, "POST /cases creates case, SLA set from severity", cs["status"] == "new" and cs["sla"]["due_at"], f"high -> due {cs['sla']['due_at'][:16]}")
check(P, "GET /cases lists it", any(c["id"] == c1 for c in http.get("/cases", params={"ward": "W-12"}).json()))
r = msg(c1, "corporation", "reject", "water_board", refs=())
check(P, "reject without evidence -> 422", r.status_code == 422)
r = msg(c1, "corporation", "reject", "water_board", refs=("corp/asset/none",), reason="Water main, not road")
check(P, "reject with target+evidence -> 201", r.status_code == 201)
cs = http.get(f"/cases/{c1}").json()
check(P, "case in_dispute, hop_count 1", cs["status"] == "in_dispute" and cs["hop_count"] == 1)
r = msg(c1, "highways", "accept")
check(P, "wrong department responding -> 409", r.status_code == 409, r.json().get("detail", ""))
r = msg(c1, "water_board", "reject", "corporation", refs=("corp/asset/none",))
check(P, "re-send to rejector without new evidence -> 409", r.status_code == 409, r.json().get("detail", ""))
r = msg(c1, "water_board", "accept", refs=("water/pipe/PW-4471",))
check(P, "referred department accepts -> assigned", r.status_code == 201 and status(c1) == "assigned")
r = msg(c1, "electricity", "accept")
check(P, "non-owner posting after accept -> 409", r.status_code == 409)

c2 = new_case("Hop cap test")
msg(c2, "corporation", "reject", "water_board", refs=("a",))
msg(c2, "water_board", "reject", "electricity", refs=("b",))
check(P, "two hops used", http.get(f"/cases/{c2}").json()["hop_count"] == 2)
msg(c2, "electricity", "reject", "highways", refs=("c",))
cs = http.get(f"/cases/{c2}").json()
check(P, "third referral escalates (hop cap 2)", cs["status"] == "escalated" and cs["hop_count"] == 2)
acts = [a["action"] for a in http.get(f"/cases/{c2}/audit").json()]
check(P, "audit log records escalation", "escalated_hop_cap" in acts, " > ".join(acts))
check(P, "message log kept", len(http.get(f"/cases/{c2}/messages").json()) == 3)
check(P, "unknown case -> 404", http.get("/cases/nope").status_code == 404)

# ---------------------------------------------------------------- Phase 3
P = f"Phase 3 intake ({MODE})"
before = f"{IMG}/before.jpg"
r = post("/intake", citizen_ref="cit_e2e", text="Big pothole on MG Road near the bus stop, very dangerous for bikes",
         photo_urls=[before], location=PIN).json()
ok = r["result"] == "case_created"
case = r.get("case") or {}
check(P, "text + photo + pin -> case", ok, f"{case.get('category')} / {case.get('severity')} / \"{case.get('description')}\"")
intake_case = case.get("id")
check(P, "case persisted with before photo", ok and http.get(f"/cases/{intake_case}").json()["media"][0]["url"] == before)
r = post("/intake", citizen_ref="cit_e2e", text="Streetlight not working in our lane for a week").json()
check(P, "no location pin -> need_info(location)", r["result"] == "need_info" and "location" in r["need_info"]["missing"], r["need_info"]["question"])
r2 = post("/intake", citizen_ref="cit_e2e", text="Streetlight not working in our lane for a week", location=PIN).json()
check(P, "citizen replies with pin -> case", r2["result"] == "case_created", f"{r2['case']['category']}" if r2.get("case") else "")
r = post("/intake", citizen_ref="cit_e2e", text="problem here", location=PIN).json()
check(P, "vague text -> need_info(details)", r["result"] == "need_info" and "details" in r["need_info"]["missing"], r["need_info"]["question"])
r = post("/intake", citizen_ref="cit_e2e", photo_urls=[f"{IMG}/blurry.jpg"], location=PIN).json()
check(P, "blurry photo only -> need_info", r["result"] == "need_info", r["need_info"]["question"] if r["result"] == "need_info" else "")
r = post("/intake", citizen_ref="cit_e2e").json()
check(P, "empty report -> need_info(details)", r["result"] == "need_info")
check(P, "unreachable media URL -> 502", post("/intake", citizen_ref="c", photo_urls=[f"{IMG}/missing.jpg"], location=PIN).status_code == 502)
if intake_case:
    r1 = msg(intake_case, "corporation", "reject", "highways", refs=("corp/road/MG-road-arterial",), reason="MG Road is an arterial road")
    r2 = msg(intake_case, "highways", "accept", refs=("hwy/road/MG-road",))
    check(P, "intake case routed through dispute loop to owner", r1.status_code == 201 and r2.status_code == 201 and status(intake_case) == "assigned",
          "corporation -> highways (accept)")

# ---------------------------------------------------------------- Phase 4
P = f"Phase 4 proof ({MODE})"
if not intake_case:
    check(P, "skipped: no intake case", False)
else:
    cid = intake_case
    v = lambda url, pos: post(f"/cases/{cid}/verify", after_photo_url=url, **pos)
    r = http.post(f"/cases/{cid}/confirm", json={"resolved": True})
    check(P, "confirm before verification -> 409", r.status_code == 409)
    r = v(f"{IMG}/after_fixed.jpg", FAR).json()
    check(P, "good photo but 222 m away -> blocked by GPS", not r["passed"] and not r["gps_ok"], r["reason"])
    r = v(f"{IMG}/after_still.jpg", NEAR).json()
    check(P, "pothole still there -> blocked by vision", not r["passed"] and r["gps_ok"] and not r["vision_resolved"], r["reason"])
    r = v(f"{IMG}/wrong_place.jpg", NEAR).json()
    check(P, "photo of a different place -> blocked", not r["passed"], r["reason"])
    check(P, "case still in_progress after failures", status(cid) == "in_progress")
    r = v(f"{IMG}/after_fixed.jpg", NEAR).json()
    check(P, "good after-photo + GPS -> passed, awaiting_citizen", r["passed"] and r["status"] == "awaiting_citizen", r["reason"])
    r = http.post(f"/cases/{cid}/confirm", json={"resolved": False, "comment": "still some damage"}).json()
    check(P, "citizen reopens -> reopened", r["status"] == "reopened")
    r = v(f"{IMG}/after_fixed.jpg", NEAR).json()
    check(P, "crew re-verifies reopened case", r["passed"] and r["status"] == "awaiting_citizen")
    r = http.post(f"/cases/{cid}/confirm", json={"resolved": True}).json()
    check(P, "citizen confirms -> closed", r["status"] == "closed")
    check(P, "closed case accepts no more messages", msg(cid, "highways", "accept").status_code == 409)
    acts = [a["action"] for a in http.get(f"/cases/{cid}/audit").json()]
    print("\nAudit trail for the intake case:\n  " + "\n  ".join(acts))

# ---------------------------------------------------------------- Summary
print("\n" + "=" * 70)
for phase in dict.fromkeys(p for p, *_ in results):
    rs = [r for r in results if r[0] == phase]
    print(f"{phase:34s} {sum(r[2] for r in rs)}/{len(rs)} passed")
bad = [r for r in results if not r[2]]
print(f"\nTOTAL {len(results) - len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
