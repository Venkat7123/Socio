from datetime import datetime, timedelta, timezone

import pytest

from app import engine
from app.engine import EngineError
from app.models import AgentMessage, CaseCreate, CaseStatus

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)


def new_case(conn, severity="medium", now=T0):
    return engine.create_case(conn, CaseCreate(
        category="water_leak", severity=severity, description="Pipe leaking",
        location={"lat": 13.0835, "lng": 80.272, "ward": "W-12"}, citizen_ref="cit_1",
        media=[{"kind": "photo", "url": "https://x/a.jpg"}],
    ), now=now)


def msg(frm, typ, target=None, refs=("r1",), reason="because"):
    return AgentMessage(from_agent=frm, type=typ, target_department=target, reason=reason,
                        evidence=[{"kind": "registry", "ref": r} for r in refs] if typ in ("reject", "transfer") else [])


def test_create_sets_sla_and_audit(conn):
    c = new_case(conn, "critical")
    assert c.status == CaseStatus.new and c.hop_count == 0
    assert c.sla.due_at == T0 + timedelta(hours=4) and not c.sla.breached
    assert c.media[0].url == "https://x/a.jpg"
    assert [a.action for a in engine.list_audit(conn, c.id)] == ["case_created"]


def test_reject_then_accept(conn):
    c = new_case(conn)
    engine.post_message(conn, c.id, msg("corporation", "reject", "water_board"), now=T0)
    mid = engine.get_case(conn, c.id, now=T0)
    assert mid.status == CaseStatus.in_dispute and mid.hop_count == 1 and mid.owner_department is None
    engine.post_message(conn, c.id, msg("water_board", "accept"), now=T0)
    done = engine.get_case(conn, c.id, now=T0)
    assert done.status == CaseStatus.assigned and done.owner_department.value == "water_board"
    assert len(engine.list_messages(conn, c.id)) == 2


def test_only_referred_department_may_respond(conn):
    c = new_case(conn)
    engine.post_message(conn, c.id, msg("corporation", "reject", "water_board"), now=T0)
    with pytest.raises(EngineError) as e:
        engine.post_message(conn, c.id, msg("highways", "accept"), now=T0)
    assert e.value.status_code == 409


def test_no_resend_without_new_evidence(conn):
    c = new_case(conn)
    engine.post_message(conn, c.id, msg("corporation", "reject", "water_board", ("r1",)), now=T0)
    # water_board bounces it back to corporation with its own evidence, which corporation has already rejected
    with pytest.raises(EngineError) as e:
        engine.post_message(conn, c.id, msg("water_board", "reject", "corporation", ("r1",)), now=T0)
    assert e.value.status_code == 409 and "new evidence" in e.value.detail
    engine.post_message(conn, c.id, msg("water_board", "reject", "corporation", ("r1", "r2")), now=T0)
    assert engine.get_case(conn, c.id, now=T0).hop_count == 2


def test_hop_cap_escalates(conn):
    c = new_case(conn)
    engine.post_message(conn, c.id, msg("corporation", "reject", "water_board", ("a",)), now=T0)
    engine.post_message(conn, c.id, msg("water_board", "reject", "electricity", ("b",)), now=T0)
    assert engine.get_case(conn, c.id, now=T0).hop_count == 2
    engine.post_message(conn, c.id, msg("electricity", "reject", "highways", ("c",)), now=T0)
    final = engine.get_case(conn, c.id, now=T0)
    assert final.status == CaseStatus.escalated and final.hop_count == 2
    actions = [a.action for a in engine.list_audit(conn, c.id)]
    assert "escalated_hop_cap" in actions
    with pytest.raises(EngineError):
        engine.post_message(conn, c.id, msg("highways", "accept"), now=T0)


def test_owner_only_after_accept(conn):
    c = new_case(conn)
    engine.post_message(conn, c.id, msg("corporation", "accept"), now=T0)
    with pytest.raises(EngineError):
        engine.post_message(conn, c.id, msg("water_board", "accept"), now=T0)


def test_sla_breach_escalates_and_flags(conn):
    c = new_case(conn, "critical")
    later = T0 + timedelta(hours=5)
    got = engine.get_case(conn, c.id, now=later)
    assert got.sla.breached and got.status == CaseStatus.escalated
    assert "sla_breached" in [a.action for a in engine.list_audit(conn, c.id)]


def test_transition_table():
    engine.check_transition(CaseStatus.awaiting_citizen, CaseStatus.closed)
    with pytest.raises(EngineError):
        engine.check_transition(CaseStatus.closed, CaseStatus.new)


def test_api_end_to_end(client):
    body = {"category": "pothole", "severity": "low", "description": "Deep pothole",
            "location": {"lat": 13.083, "lng": 80.271, "ward": "W-7"}, "citizen_ref": "cit_x"}
    cid = client.post("/cases", json=body).json()["id"]
    assert client.get("/cases", params={"ward": "W-7"}).json()[0]["id"] == cid
    bad = {"from_agent": "corporation", "type": "reject", "target_department": "water_board", "reason": "no", "evidence": []}
    assert client.post(f"/cases/{cid}/messages", json=bad).status_code == 422
    ok = {**bad, "reason": "not ours", "evidence": [{"kind": "registry", "ref": "r1"}]}
    assert client.post(f"/cases/{cid}/messages", json=ok).status_code == 201
    assert client.post(f"/cases/{cid}/messages", json={"from_agent": "highways", "type": "accept", "reason": "mine"}).status_code == 409
    assert client.get("/cases/nope").status_code == 404
    assert len(client.get(f"/cases/{cid}/messages").json()) == 1
    assert len(client.get(f"/cases/{cid}/audit").json()) == 2
