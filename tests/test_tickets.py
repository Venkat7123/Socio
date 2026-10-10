"""Ticket-based acceptance tests (T1-T7) against the real FastAPI app via
TestClient -- this dispatches through the actual ASGI routing/validation
layer (status codes, Pydantic validation included), not just internal
functions, which is what "send tickets to the case API" means here. Using
TestClient instead of a live curl/uvicorn process keeps this deterministic
and quota-free: tests/conftest.py forces GEMINI_API_KEY="" for the whole
tests/ package, so every decision goes through the fallback_rules backend,
not live Gemini.

T3, T4 and T6 use real coordinates pulled from the seeded registries
(RNG_SEED=42 in seed_db.py, so these are reproducible on any
`python seed_db.py --reset`):

  T3: corporation drain SD-0001 (13.086316380717925, 80.27058851852587) --
      108.4 m from the nearest corporation road, 252.9 m from the nearest
      handover record (clean presence-only accept, not a split), 62.9 m from
      the nearest water_board pipeline and 192.5 m from the nearest valve
      (clean water_board absence).
  T4: there is exactly ONE point in the seeded data where a corporation drain
      is within 30 m AND a highways segment is within 50 m of the same spot:
      the official P2 fixture itself (handover HO-07 -> drain SD-112 at
      18.0 m, highway segment H-07 at 0.0 m). HO-90 (drain 181.1 m away) and
      HO-91 (drain 53.1 m away) were checked and don't qualify. So T4
      necessarily reuses P2's coordinates -- there is no second organic split
      point to pick from in the current seed.
  T6: (13.079, 80.266) -- 231.2 m from the nearest corporation lamp, 391.0 m
      from the nearest electricity pole. Nothing from either streetlight
      candidate department is anywhere nearby.

T2 (duplicate linking) is now implemented: app/engine.py::_find_duplicate
runs before any routing/agent work, for any ticket with a usable location,
and matches on (category, ward, within config.DUPLICATE_RADIUS_M meters) --
see app/engine.py::create_case. A match short-circuits straight to a
DUPLICATE_LINKED case with zero query_log entries and an empty transcript
(no agent was ever called), pointing at the original via `linked_case_id`.

The remaining tickets describe behavior that isn't implemented today; those
are written as literal, unmodified assertions of what the ticket asked for,
and are EXPECTED to fail -- see the module docstring in the terminal report
for details, not softened here, since the point of this file is to surface
the gap, not paper over it:
  - T4 ("each with owner and deadline"): sub_tasks have no `deadline` field
    (app/schemas.py::SubTaskOut).
  - T5 (no lat/lng -> need_info): app/engine.py::_resolve_location raises
    ValueError when neither point_label nor both lat/lng are given, which
    app/routers/cases.py turns into an HTTP 400 -- no case is ever persisted,
    so there is no NEEDS_INFO case to inspect.
  - T6 (escalate at "2 hops"): engine rule 7 escalates as soon as every
    matrix candidate has rejected absence-only, which for a 2-candidate
    category (corporation, electricity) happens at hop_count=1 -- the same
    as the official S4 scenario (also a 2-candidate category).
  - T7 (null category -> need_info/triage): `category` is a required `str`
    in CaseCreate; `null` fails FastAPI/Pydantic request validation with a
    422 before any case is created, so there's no case to be NEEDS_INFO or
    ESCALATED.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import engine
from app.main import app

client = TestClient(app)

T1_PAYLOAD = {"category": "garbage", "lat": 13.0845, "lng": 80.268, "ward": "W-12",
              "description": "Overflowing garbage bin, asset GB-0004 is 22.6m away"}


def test_t1_garbage_assigned_corporation_zero_hops():
    resp = client.post("/cases", json=T1_PAYLOAD)
    assert resp.status_code == 201, resp.text
    case = resp.json()
    assert case["status"] == "ASSIGNED", f"actual response: {case}"
    assert case["owner_department"] == "corporation", f"actual response: {case}"
    assert case["hop_count"] == 0, f"actual response: {case}"


def test_t2_duplicate_ticket_links_to_t1_no_new_agent_calls():
    """Identical location+category links to the existing case (status
    DUPLICATE_LINKED) and triggers no new agent evaluation at all."""
    first = client.post("/cases", json=T1_PAYLOAD)
    assert first.status_code == 201, first.text
    case1 = first.json()
    log1_before = client.get(f"/query-log/{case1['id']}").json()

    second = client.post("/cases", json=T1_PAYLOAD)
    assert second.status_code == 201, second.text
    case2 = second.json()

    log1_after = client.get(f"/query-log/{case1['id']}").json()
    log2 = client.get(f"/query-log/{case2['id']}").json()

    assert case2["status"] == "DUPLICATE_LINKED", f"actual response: {case2}"
    assert case2["linked_case_id"] == case1["id"], f"actual response: {case2}"
    assert case2["owner_department"] == case1["owner_department"], f"actual response: {case2}"
    assert case2["hop_count"] == 0, f"actual response: {case2}"
    assert case2["transcript"] == [], f"no agent should ever have been called: {case2['transcript']}"
    assert len(log1_after) == len(log1_before), "case1's own query log should be untouched"
    assert len(log2) == 0, f"case2 should have zero tool calls of its own, found: {log2}"


def test_t2b_duplicate_detection_is_distance_bounded_not_just_category():
    """A same-category ticket far enough away must NOT be linked -- duplicate
    detection is about the same physical complaint, not just the same
    category anywhere in the ward."""
    far_payload = {**T1_PAYLOAD, "lat": T1_PAYLOAD["lat"] + 0.01, "lng": T1_PAYLOAD["lng"] + 0.01,
                   "description": "Different garbage complaint, different part of the ward"}
    first = client.post("/cases", json=T1_PAYLOAD)
    assert first.status_code == 201, first.text

    far = client.post("/cases", json=far_payload)
    assert far.status_code == 201, far.text
    far_case = far.json()
    assert far_case["status"] != "DUPLICATE_LINKED", f"actual response: {far_case}"
    assert far_case.get("linked_case_id") is None, f"actual response: {far_case}"


def test_t3_waterlogging_water_board_rejects_corporation_accepts():
    payload = {"category": "waterlogging", "lat": 13.086316380717925, "lng": 80.27058851852587,
               "ward": "W-12", "description": "Water logged near drain SD-0001"}
    resp = client.post("/cases", json=payload)
    assert resp.status_code == 201, resp.text
    case = resp.json()

    assert case["status"] == "ASSIGNED", f"actual response: {case}"
    assert case["owner_department"] == "corporation", f"actual response: {case}"
    assert case["hop_count"] == 1, f"actual response: {case}"

    reject_msgs = [m for m in case["transcript"] if m["type"] == "reject"]
    assert len(reject_msgs) == 1, f"expected exactly one reject; actual transcript: {case['transcript']}"
    wb_reject = reject_msgs[0]
    assert wb_reject["from"] == "water_board_agent", f"actual response: {wb_reject}"
    assert wb_reject["target"] == "corporation_agent", f"actual response: {wb_reject}"
    assert len(wb_reject["evidence"]) > 0, "reject must carry evidence"

    accept_msgs = [m for m in case["transcript"] if m["type"] == "accept"]
    assert len(accept_msgs) == 1 and accept_msgs[0]["from"] == "corporation_agent", f"actual response: {case['transcript']}"


def test_t4_waterlogging_split_with_owner_and_deadline():
    """Reuses the P2 fixture's coordinates: it's the only point in the seeded
    data with both a corporation drain within 30 m (SD-112, 18.0 m) AND a
    highways segment within 50 m (H-07, 0.0 m) of the same spot, verified by
    checking all 3 handover records (see module docstring)."""
    payload = {"category": "waterlogging", "point_label": "P2",
               "description": "Drain blocked and the handed-over road surface is damaged after the flood"}
    resp = client.post("/cases", json=payload)
    assert resp.status_code == 201, resp.text
    case = resp.json()

    assert case["status"] == "SPLIT", f"actual response: {case}"
    assert len(case["sub_tasks"]) == 2, f"actual response: {case}"
    depts = {st["department"] for st in case["sub_tasks"]}
    assert depts == {"corporation", "highways"}, f"actual response: {case['sub_tasks']}"

    for st in case["sub_tasks"]:
        assert st.get("department"), f"sub_task missing an owning department: {st}"
        assert "deadline" in st, (
            f"sub_tasks have no 'deadline' field at all (see app/schemas.py::SubTaskOut and the "
            f"sub_tasks table in app/db.py) -- actual sub_task: {st}"
        )


def test_t5_no_coordinates_returns_need_info_nothing_routed():
    payload = {"category": "pothole", "accuracy_m": 500, "description": "Pothole somewhere in the ward, not sure where"}
    resp = client.post("/cases", json=payload)

    assert resp.status_code == 201, (
        f"expected a persisted NEEDS_INFO case, but the request was rejected outright. "
        f"actual: HTTP {resp.status_code} {resp.text}"
    )
    case = resp.json()
    assert case["status"] == "NEEDS_INFO", f"actual response: {case}"
    assert any("location" in f for f in case["needs_info_fields"]), f"actual response: {case}"
    assert case["owner_department"] is None, f"actual response: {case}"


def test_t6_streetlight_no_asset_anywhere_escalates_at_two_hops():
    payload = {"category": "streetlight", "lat": 13.079, "lng": 80.266, "ward": "W-12",
               "description": "Street light out, nothing else around"}
    resp = client.post("/cases", json=payload)
    assert resp.status_code == 201, resp.text
    case = resp.json()

    assert case["status"] == "ESCALATED", f"actual response: {case}"
    assert case["escalation_reason"], f"actual response: {case}"
    assert case["hop_count"] == 2, (
        f"engine rule 7 escalates as soon as every matrix candidate for streetlight (corporation, "
        f"electricity -- only 2) has rejected absence-only, which happens at hop_count=1, same as the "
        f"official S4 scenario. actual response: {case}"
    )
    assert len(case["adjudications"]) >= 1, f"actual response: {case}"


def test_t7_vague_description_null_category_never_a_confident_owner():
    payload = {"category": None, "lat": 13.083, "lng": 80.271, "ward": "W-12",
               "description": "not sure what this is, something's wrong on this street"}
    resp = client.post("/cases", json=payload)

    assert resp.status_code == 201, (
        f"expected a persisted case in NEEDS_INFO or ESCALATED, but `category: null` fails FastAPI/Pydantic "
        f"request validation (CaseCreate.category is a required str) before any case is created. "
        f"actual: HTTP {resp.status_code} {resp.text}"
    )
    case = resp.json()
    assert case["status"] in ("NEEDS_INFO", "ESCALATED"), f"actual response: {case}"
    assert case["owner_department"] is None, f"actual response: {case}"
