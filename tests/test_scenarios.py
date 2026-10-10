"""End-to-end tests for the four worked scenarios in prompt.md 2.7, plus the
"Test assertions to add for Track C" from the same section. Runs against the
deterministic fallback_rules LLM backend (see conftest.py) so results are
reproducible in CI without a Gemini key.
"""
from fastapi.testclient import TestClient

from app import matrix
from app.main import app

client = TestClient(app)


def create_case(category: str, point_label: str | None = None, **kwargs) -> dict:
    payload = {"category": category, **kwargs}
    if point_label:
        payload["point_label"] = point_label
    resp = client.post("/cases", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# S1-S4
# --------------------------------------------------------------------------- #

def test_s1_pothole_on_municipal_road():
    case = create_case("pothole", "P1")
    assert case["status"] == "ASSIGNED"
    assert case["owner_department"] == "corporation"
    assert case["hop_count"] == 0


def test_s2_waterlogging_near_school_splits():
    case = create_case("waterlogging", "P2")
    assert case["status"] == "SPLIT"
    assert case["owner_department"] == "corporation"
    assert case["hop_count"] == 1  # the water_board -> corporation reject is the one hop

    by_dept = {st["department"]: st for st in case["sub_tasks"]}
    assert set(by_dept) == {"corporation", "highways"}
    assert by_dept["corporation"]["status"] == "ASSIGNED"
    assert by_dept["highways"]["status"] == "ASSIGNED"
    assert by_dept["highways"]["depends_on"] == by_dept["corporation"]["id"]
    assert by_dept["highways"]["target_basis"].startswith("handover_record:")


def test_s3_streetlight_pole_goes_to_electricity():
    case = create_case("streetlight", "P3")
    assert case["status"] == "ASSIGNED"
    assert case["owner_department"] == "electricity"
    assert case["hop_count"] == 1


def test_s4_two_agents_reject_each_other_escalates():
    case = create_case("pothole", "P4")
    assert case["status"] == "ESCALATED"
    assert case["escalation_reason"] == "return blocked, all candidates absence-only"
    assert len(case["adjudications"]) == 1
    assert case["adjudications"][0]["trigger_reason"] == "return blocked, all candidates absence-only"


def test_other_category_has_no_candidates_and_escalates_immediately():
    resp = client.post("/cases", json={"category": "other", "description": "unclassifiable complaint"})
    assert resp.status_code == 201
    case = resp.json()
    assert case["status"] == "ESCALATED"
    assert case["hop_count"] == 0


# --------------------------------------------------------------------------- #
# "Test assertions to add for Track C"
# --------------------------------------------------------------------------- #

def test_no_evidence_ref_belongs_to_another_departments_query_log():
    case = create_case("waterlogging", "P2")
    log = client.get(f"/query-log/{case['id']}").json()
    ref_to_dept = {entry["ref"]: entry["department"] for entry in log}

    for msg in case["transcript"]:
        from_dept = msg["from"].removesuffix("_agent")
        for ev in msg["evidence"]:
            assert ref_to_dept.get(ev["ref"]) == from_dept, (
                f"ref {ev['ref']} appears in a message from {from_dept} but belongs to "
                f"{ref_to_dept.get(ev['ref'])}'s query log"
            )


def test_no_agent_tool_set_contains_another_departments_registry():
    from app.registries import ASSET_TABLES

    all_tables = [t for tables in ASSET_TABLES.values() for t in tables.values()]
    assert len(all_tables) == len(set(all_tables)), "a table name is shared across departments"
    for dept, tables in ASSET_TABLES.items():
        for t in tables.values():
            assert t.startswith(dept), f"table '{t}' is not namespaced under its owning department '{dept}'"


def test_every_reject_has_a_valid_target_basis():
    for category, point in [("waterlogging", "P2"), ("streetlight", "P3"), ("pothole", "P4")]:
        case = create_case(category, point)
        for msg in case["transcript"]:
            if msg["type"] != "reject":
                continue
            tb = msg["target_basis"]
            assert tb, f"reject message in {category}/{point} has no target_basis"
            if tb.startswith("matrix_rule:"):
                rule = matrix.rule_by_id(tb.split(":", 1)[1])
                assert rule is not None, f"target_basis references unknown rule {tb}"
                target_dept = msg["target"].removesuffix("_agent")
                assert target_dept in rule.candidates
            elif tb.startswith("handover_record:"):
                ref = tb.split(":", 1)[1]
                assert any(e["ref"] == ref and e["kind"] == "handover_record" for e in msg["evidence"])
            else:
                raise AssertionError(f"malformed target_basis: {tb}")


def test_no_department_is_assigned_owner_without_presence_evidence():
    case1 = create_case("pothole", "P1")
    accept_msgs = [m for m in case1["transcript"] if m["type"] == "accept" and m["from"] == "corporation_agent"]
    assert accept_msgs and any(e["kind"] == "presence" for e in accept_msgs[-1]["evidence"])

    case2 = create_case("streetlight", "P3")
    accept_msgs2 = [m for m in case2["transcript"] if m["type"] == "accept" and m["from"] == "electricity_agent"]
    assert accept_msgs2 and any(e["kind"] == "presence" for e in accept_msgs2[-1]["evidence"])

    case3 = create_case("waterlogging", "P2")
    for st in case3["sub_tasks"]:
        if st["status"] != "ASSIGNED":
            continue
        dept_agent = f"{st['department']}_agent"
        msgs = [m for m in case3["transcript"] if m["from"] == dept_agent and any(e["kind"] == "presence" for e in m["evidence"])]
        assert msgs, f"{st['department']} is ASSIGNED without ever citing presence evidence"
