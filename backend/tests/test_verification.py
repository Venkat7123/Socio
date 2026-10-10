import time
from datetime import datetime, timezone

import pytest
from fakes import FakeLLM

from app import engine
from app import llm as llm_mod
from app.engine import EngineError
from app.llm import Image
from app.main import app, get_verification_agent
from app.models import AgentMessage, CaseCreate, CaseStatus, ConfirmRequest, VerifyRequest
from app.verification import VerificationAgent, distance_m

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
LAT, LNG = 13.0835, 80.2720  # Track C ward W-12 scenario point P2 (Chennai)
NEAR = (LAT + 0.0002, LNG)  # about 22 m north
FAR = (LAT + 0.002, LNG)  # about 222 m north


def fetch(url):
    return b"img:" + url.encode(), "image/jpeg"


def verifier(same_spot=True, resolved=True, reason="Looks fixed.", fail=False):
    llm = FakeLLM({"same_spot": same_spot, "resolved": resolved, "reason": reason}, fail=fail)
    return VerificationAgent(llm=llm, radius_m=50, fetch=fetch), llm


def assigned_case(conn, photos=("https://h/before.jpg",)):
    c = engine.create_case(conn, CaseCreate(
        category="water_leak", severity="high", description="Pipe leaking on the road",
        location={"lat": LAT, "lng": LNG}, citizen_ref="c",
        media=[{"kind": "photo", "url": u} for u in photos]), now=T0)
    engine.post_message(conn, c.id, AgentMessage(from_agent="water_board", type="accept", reason="ours"), now=T0)
    return c.id


def vreq(pos=NEAR):
    return VerifyRequest(after_photo_url="https://h/after.jpg", lat=pos[0], lng=pos[1])


def test_distance_helper():
    assert distance_m(LAT, LNG, LAT, LNG) == 0
    assert 215 < distance_m(LAT, LNG, *FAR) < 230


def test_good_photo_passes_and_awaits_citizen(conn):
    cid = assigned_case(conn)
    agent, llm = verifier()
    r = engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert r.passed and r.gps_ok and r.status == CaseStatus.awaiting_citizen and r.distance_m < 50
    assert engine.get_case(conn, cid, now=T0).status == CaseStatus.awaiting_citizen
    parts = llm.json_calls[0]["parts"]
    assert parts[0] == "BEFORE photo 1:" and isinstance(parts[1], Image) and "AFTER photo:" in parts
    assert "verification_passed" in [a.action for a in engine.list_audit(conn, cid)]


def test_far_gps_blocks_without_calling_model(conn):
    cid = assigned_case(conn)
    agent, llm = verifier()
    r = engine.verify_case(conn, cid, vreq(FAR), agent, now=T0)
    assert not r.passed and not r.gps_ok and "m from the reported location" in r.reason
    assert llm.json_calls == []
    assert r.status == CaseStatus.in_progress


@pytest.mark.parametrize("kw", [{"resolved": False}, {"same_spot": False}])
def test_bad_vision_blocks_and_case_stays_open(conn, kw):
    cid = assigned_case(conn)
    agent, _ = verifier(reason="Still leaking.", **kw)
    r = engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert not r.passed and r.gps_ok and r.status == CaseStatus.in_progress and r.reason == "Still leaking."
    # crew can resubmit and pass
    good, _ = verifier()
    assert engine.verify_case(conn, cid, vreq(), good, now=T0).status == CaseStatus.awaiting_citizen


def test_no_before_photo_is_noted_in_prompt(conn):
    cid = assigned_case(conn, photos=())
    agent, llm = verifier()
    engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert "Before photos provided: 0" in llm.json_calls[0]["parts"][-1]


def test_model_failure_returns_retry_and_leaves_case_untouched(conn):
    cid = assigned_case(conn)
    agent, _ = verifier(fail=True)
    r = engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert r.retry and not r.passed and "resubmit" in r.reason and r.status == CaseStatus.assigned
    assert engine.get_case(conn, cid, now=T0).status == CaseStatus.assigned
    assert "verification_unavailable" in [a.action for a in engine.list_audit(conn, cid)]


def test_slow_model_returns_retry_quickly(conn, monkeypatch):
    monkeypatch.setattr(llm_mod, "TIMEOUT_S", 0.3)
    cid = assigned_case(conn)
    agent, llm = verifier()
    llm.complete_json = lambda *a, **k: llm_mod._guarded(lambda: time.sleep(5))
    t = time.time()
    r = engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert time.time() - t < 2 and r.retry and r.status == CaseStatus.assigned


def test_far_gps_never_needs_the_model(conn):
    """GPS failures are decided without the model, so they work even when it is down."""
    cid = assigned_case(conn)
    agent, _ = verifier(fail=True)
    r = engine.verify_case(conn, cid, vreq(FAR), agent, now=T0)
    assert not r.retry and not r.gps_ok


def test_verify_needs_assigned_case(conn):
    c = engine.create_case(conn, CaseCreate(category="pothole", severity="low", description="hole",
                                            location={"lat": LAT, "lng": LNG}, citizen_ref="c"), now=T0)
    agent, _ = verifier()
    with pytest.raises(EngineError) as e:
        engine.verify_case(conn, c.id, vreq(), agent, now=T0)
    assert e.value.status_code == 409


def test_confirm_closes_or_reopens(conn):
    agent, _ = verifier()
    cid = assigned_case(conn)
    engine.verify_case(conn, cid, vreq(), agent, now=T0)
    assert engine.confirm_case(conn, cid, ConfirmRequest(resolved=True), now=T0).status == CaseStatus.closed
    with pytest.raises(EngineError):
        engine.confirm_case(conn, cid, ConfirmRequest(resolved=True), now=T0)

    cid2 = assigned_case(conn)
    engine.verify_case(conn, cid2, vreq(), agent, now=T0)
    c = engine.confirm_case(conn, cid2, ConfirmRequest(resolved=False, comment="still wet"), now=T0)
    assert c.status == CaseStatus.reopened and c.owner_department.value == "water_board"
    assert engine.verify_case(conn, cid2, vreq(), agent, now=T0).passed  # reopened cases can be verified again


def test_confirm_requires_verification(conn):
    cid = assigned_case(conn)
    with pytest.raises(EngineError) as e:
        engine.confirm_case(conn, cid, ConfirmRequest(resolved=True), now=T0)
    assert e.value.status_code == 409


def test_api_blocks_bad_and_closes_good(client):
    app.dependency_overrides[get_verification_agent] = lambda: verifier()[0]
    try:
        cid = client.post("/cases", json={"category": "water_leak", "severity": "high", "description": "leak",
                                          "location": {"lat": LAT, "lng": LNG}, "citizen_ref": "c"}).json()["id"]
        client.post(f"/cases/{cid}/messages", json={"from_agent": "water_board", "type": "accept", "reason": "ours"})
        body = {"after_photo_url": "https://h/after.jpg", "lat": FAR[0], "lng": FAR[1]}
        assert client.post(f"/cases/{cid}/verify", json=body).json()["passed"] is False
        assert client.post(f"/cases/{cid}/confirm", json={"resolved": True}).status_code == 409
        good = {**body, "lat": NEAR[0], "lng": NEAR[1]}
        assert client.post(f"/cases/{cid}/verify", json=good).json()["status"] == "awaiting_citizen"
        assert client.post(f"/cases/{cid}/confirm", json={"resolved": True}).json()["status"] == "closed"
        app.dependency_overrides[get_verification_agent] = lambda: verifier(fail=True)[0]
        cid2 = client.post("/cases", json={"category": "pothole", "severity": "low", "description": "hole",
                                           "location": {"lat": LAT, "lng": LNG}, "citizen_ref": "c"}).json()["id"]
        client.post(f"/cases/{cid2}/messages", json={"from_agent": "highways", "type": "accept", "reason": "ours"})
        r = client.post(f"/cases/{cid2}/verify", json=good).json()
        assert r["retry"] is True and r["passed"] is False and r["status"] == "assigned"
    finally:
        app.dependency_overrides.pop(get_verification_agent, None)


def test_listed_mismatch_overrides_a_same_spot_verdict():
    """The model claims same spot but lists a differing landmark: code trusts the observation, not the verdict."""
    llm = FakeLLM({"same_spot": True, "resolved": True, "reason": "Looks the same.",
                   "before_landmarks": ["red building left"], "after_landmarks": ["blue building left"],
                   "mismatches": ["red building on the left is a blue building in the after photo"]})
    from app.models import Case
    case = Case.model_validate({
        "id": "c", "status": "in_progress", "category": "pothole", "severity": "low", "description": "hole",
        "location": {"lat": LAT, "lng": LNG}, "media": [{"kind": "photo", "url": "https://h/b.jpg"}], "citizen_ref": "c",
        "sla": {"due_at": "2030-01-01T00:00:00+00:00"}, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"})
    v = VerificationAgent(llm=llm, radius_m=50, fetch=fetch).verify(case, vreq())
    assert not v.vision_same_spot and not v.passed and "original spot" in v.reason and "blue building" in v.reason


def test_no_before_photos_ignores_mismatch_list(conn):
    llm = FakeLLM({"same_spot": True, "resolved": True, "reason": "ok", "mismatches": ["noise"]})
    cid = assigned_case(conn, photos=())
    r = engine.verify_case(conn, cid, vreq(), VerificationAgent(llm=llm, radius_m=50, fetch=fetch), now=T0)
    assert r.passed
