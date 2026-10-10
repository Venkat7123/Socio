"""Runs S2, S3 and S4 through the backend engine and the real Track C agents (backend on :8000, Track C on :8100).

Each scenario is reported as LIVE-LLM (every decision came from a Groq model), RULE-STUB (rules backend) or FAILED
(did not reach the expected outcome). model_backend is read off every message, so nothing is guessed.
    python scripts/e2e_trackc.py
"""
import collections
import sys

import httpx

API = "http://localhost:8000"
P = {"P2": (13.08350, 80.27200), "P3": (13.08250, 80.26950), "P4": (13.08400, 80.27300)}
SCENARIOS = [
    ("S2 waterlogged road", "waterlogging", "P2", "Road waterlogged near the school"),
    ("S3 streetlight", "streetlight", "P3", "Streetlight not working"),
    ("S4 road edge", "pothole", "P4", "Pothole at the road edge"),
]
SCENARIOS = [s for s in SCENARIOS if len(sys.argv) < 2 or s[0].split()[0] in sys.argv[1:]]  # optional: S2 S3 S4
http = httpx.Client(base_url=API, timeout=120)


def expected(name, case, steps, subs):
    seq = [(s["department"], s["type"]) for s in steps if not s["sub_task_id"]]
    if name.startswith("S2"):
        return (seq[:2] == [("water_board", "reject"), ("corporation", "accept")] and case["owner_department"] == "corporation"
                and any(t["department"] == "highways" and t["status"] == "assigned" for t in subs))
    if name.startswith("S3"):
        return seq[:2] == [("corporation", "reject"), ("electricity", "accept")] and case["owner_department"] == "electricity"
    return case["status"] == "escalated" and seq[0] == ("corporation", "reject") and seq[-1][1] == "escalate"


results = []
for name, cat, pt, desc in SCENARIOS:
    lat, lng = P[pt]
    cid = http.post("/cases", json={"category": cat, "severity": "high", "description": desc,
                                    "location": {"lat": lat, "lng": lng, "ward": "W-12"}, "citizen_ref": "e2e"}).json()["id"]
    r = http.post(f"/cases/{cid}/route")
    if r.status_code != 200:
        results.append((name, "FAILED", f"HTTP {r.status_code} {r.text[:150]}", {}))
        continue
    body = r.json()
    case, steps, subs = body["case"], body["steps"], body["case"]["sub_tasks"]
    backends = collections.Counter((s["model_backend"] or "?") for s in steps)
    live = all((s["model_backend"] or "").startswith("groq:") for s in steps)
    rules = all(s["model_backend"] in ("rules", "driver:escalate_on_block") for s in steps)
    ok = expected(name, case, steps, subs)
    label = "FAILED" if not ok else ("LIVE-LLM" if live else "RULE-STUB" if rules else "MIXED/FALLBACK")
    print(f"\n{name}: {label}  status={case['status']} owner={case['owner_department']} hops={case['hop_count']}")
    for s in steps:
        tgt = f" -> {s['target_department']}" if s["target_department"] else ""
        sub = " [sub-task]" if s["sub_task_id"] else ""
        print(f"   {s['department']:12s} {s['type']:12s}{tgt}{sub}  ({s['model_backend']}, conf {s['confidence']})" + (f"  NOTE: {s['note'][:110]}" if s["note"] else ""))
    for t in subs:
        print(f"   sub-task {t['department']}: {t['status']}")
    results.append((name, label, dict(backends), {}))

print("\n=== SUMMARY ===")
total = collections.Counter()
for name, label, info, _ in results:
    print(f"{name:22s} {label:15s} {info}")
    if isinstance(info, dict):
        total.update(info)
live_n = sum(v for k, v in total.items() if k.startswith("groq:"))
print(f"decisions: {live_n} live-LLM, {total.get('rules', 0)} rule-stub, "
      f"{sum(v for k, v in total.items() if k.startswith('fallback:'))} fallback, of {sum(total.values())}")
sys.exit(0 if all(r[1] in ("LIVE-LLM", "RULE-STUB") for r in results) else 1)
