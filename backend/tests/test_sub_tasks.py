from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app import engine
from app.engine import EngineError
from app.models import AgentMessage, CaseCreate, CaseStatus, SubTaskStatus

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
FINDING = {"kind": "presence", "ref": "corporation:presence:abc", "summary": "Found storm drain SD-112 within 30 m",
           "source": "corporation_registry"}
HANDOVER = {"kind": "handover_record", "ref": "corporation:handover_record:def", "summary": "Road handed to highways",
            "source": "corporation_registry"}
SPLIT = {"from_agent": "corporation", "type": "accept", "reason": "Own drain is here; the road went to highways",
         "evidence": [FINDING, HANDOVER], "confidence": 0.85, "model_backend": "rules",
         "sub_tasks": [{"department": "highways", "task": "Repair the road surface", "target_basis": "handover_record:corporation:handover_record:def"}]}


def new_case(conn):
    return engine.create_case(conn, CaseCreate(
        category="waterlogging", severity="high", description="Road waterlogged near school",
        location={"lat": 13.0835, "lng": 80.272, "ward": "W-12"}, citizen_ref="c"), now=T0).id


def split_case(conn):
    cid = new_case(conn)
    engine.post_message(conn, cid, AgentMessage(from_agent="water_board", type="reject", target_department="corporation",
        reason="No pipeline here", evidence=[{"kind": "absence", "ref": "wb:absence:1", "summary": "No pipeline within 50 m"}],
        target_basis="matrix_rule:M-WL-1"), now=T0)
    engine.post_message(conn, cid, AgentMessage(**SPLIT), now=T0)
    return cid


def test_new_contract_fields_are_stored_and_returned(conn):
    cid = split_case(conn)
    msgs = engine.list_messages(conn, cid)
    assert [m.type.value for m in msgs] == ["reject", "accept"]
    assert msgs[0].target_basis == "matrix_rule:M-WL-1" and msgs[0].evidence[0].kind == "absence"
    acc = msgs[1]
    assert acc.confidence == 0.85 and acc.model_backend == "rules" and acc.evidence[0].source == "corporation_registry"
    assert acc.sub_tasks[0].department.value == "highways"


def test_accept_with_sub_task_keeps_one_owner_and_proposes_the_rest(conn):
    cid = split_case(conn)
    case = engine.get_case(conn, cid, now=T0)
    assert case.status == CaseStatus.assigned and case.owner_department.value == "corporation"
    assert len(case.sub_tasks) == 1
    st = case.sub_tasks[0]
    assert st.department.value == "highways" and st.status == SubTaskStatus.proposed and st.proposed_by.value == "corporation"
    assert "sub_task_proposed" in [a.action for a in engine.list_audit(conn, cid)]


def answer(conn, cid, sid, frm="highways", typ="accept", **kw):
    return engine.post_sub_task_message(conn, cid, sid, AgentMessage(from_agent=frm, type=typ, reason="ok then", **kw), now=T0)


def test_sub_task_stays_proposed_until_target_accepts(conn):
    cid = split_case(conn)
    sid = engine.get_case(conn, cid, now=T0).sub_tasks[0].id
    assert engine.list_sub_tasks(conn, cid)[0].status == SubTaskStatus.proposed
    m = answer(conn, cid, sid, evidence=[{"kind": "presence", "ref": "hwy:presence:1", "summary": "Segment H-07 within 50 m"}])
    assert m.sub_task_id == sid
    assert engine.list_sub_tasks(conn, cid)[0].status == SubTaskStatus.assigned
    assert engine.get_case(conn, cid, now=T0).owner_department.value == "corporation"  # the case owner is unchanged


def test_only_the_target_department_may_answer_and_only_once(conn):
    cid = split_case(conn)
    sid = engine.get_case(conn, cid, now=T0).sub_tasks[0].id
    with pytest.raises(EngineError) as e:
        answer(conn, cid, sid, frm="electricity")
    assert e.value.status_code == 409
    answer(conn, cid, sid)
    with pytest.raises(EngineError):
        answer(conn, cid, sid)
    with pytest.raises(EngineError) as e:
        answer(conn, cid, "sub_nope")
    assert e.value.status_code == 404


def test_refused_sub_task_goes_to_a_human(conn):
    cid = split_case(conn)
    sid = engine.get_case(conn, cid, now=T0).sub_tasks[0].id
    answer(conn, cid, sid, typ="reject", target_department="corporation",
           evidence=[{"kind": "absence", "ref": "hwy:absence:1", "summary": "No segment"}])
    assert engine.list_sub_tasks(conn, cid)[0].status == SubTaskStatus.escalated


def test_sub_task_messages_stay_out_of_the_case_thread(conn):
    cid = split_case(conn)
    sid = engine.get_case(conn, cid, now=T0).sub_tasks[0].id
    answer(conn, cid, sid)
    assert len(engine.list_messages(conn, cid)) == 2  # the protocol never sees sub-task messages
    assert len(engine.list_messages(conn, cid, include_sub_tasks=True)) == 3


def test_sub_tasks_are_only_valid_on_accept_for_other_departments():
    base = {"from_agent": "corporation", "reason": "because", "sub_tasks": [{"department": "highways", "task": "Fix road"}]}
    with pytest.raises(ValidationError):
        AgentMessage(type="reject", target_department="highways", evidence=[FINDING], **base)
    with pytest.raises(ValidationError):
        AgentMessage(type="accept", **{**base, "sub_tasks": [{"department": "corporation", "task": "Fix road"}]})
    with pytest.raises(ValidationError):
        AgentMessage(type="accept", **{**base, "sub_tasks": [{"department": "highways", "task": "Fix a"}, {"department": "highways", "task": "Fix b"}]})
    AgentMessage(type="accept", **base)


def test_confidence_must_be_a_probability_and_evidence_kinds_are_checked():
    with pytest.raises(ValidationError):
        AgentMessage(from_agent="corporation", type="accept", reason="fine", confidence=1.5)
    with pytest.raises(ValidationError):
        AgentMessage(from_agent="corporation", type="accept", reason="fine", evidence=[{"kind": "rumour", "ref": "x"}])


def test_api_sub_task_flow(client):
    cid = client.post("/cases", json={"category": "waterlogging", "severity": "high", "description": "water on road",
                                      "location": {"lat": 13.0835, "lng": 80.272, "ward": "W-12"}, "citizen_ref": "c"}).json()["id"]
    assert client.post(f"/cases/{cid}/messages", json=SPLIT).status_code == 201
    case = client.get(f"/cases/{cid}").json()
    sid = case["sub_tasks"][0]["id"]
    assert case["sub_tasks"][0]["status"] == "proposed" and client.get(f"/cases/{cid}/sub_tasks").json()[0]["id"] == sid
    ans = {"from_agent": "highways", "type": "accept", "reason": "H-07 is ours",
           "evidence": [{"kind": "presence", "ref": "hwy:presence:1", "summary": "Segment H-07"}]}
    assert client.post(f"/cases/{cid}/sub_tasks/{sid}/messages", json=ans).status_code == 201
    assert client.get(f"/cases/{cid}").json()["sub_tasks"][0]["status"] == "assigned"
    assert len(client.get(f"/cases/{cid}/messages").json()) == 2
    assert len(client.get(f"/cases/{cid}/messages", params={"include_sub_tasks": "false"}).json()) == 1
    assert client.post(f"/cases/{cid}/sub_tasks/{sid}/messages", json=ans).status_code == 409
    assert client.get("/cases/nope/sub_tasks").status_code == 404
