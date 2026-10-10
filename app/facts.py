"""Builds the per-department "facts sheet" (prompt.md 2.6 step 1-2).

This is the deterministic half of the pipeline: it decides which of the
department's own tools to call for a given category, calls them, and turns
raw results into evidence dicts with code-generated `finding` text. The
model (app/llm.py) only ever reads this sheet -- it never calls a tool
itself and never writes finding text.
"""
from __future__ import annotations

from app import matrix, registries

# Which of a department's own asset types are relevant to each category.
# Not covered by the provided spec fragment -- chosen to match the radii and
# asset types implied by the worked examples in prompt.md 2.7 (e.g. "No
# pipeline or valve within 50 m", "No municipal road segment within 30 m").
CATEGORY_ASSET_PLAN: dict[str, dict[str, list[str]]] = {
    "corporation": {
        "pothole": ["road"],
        "waterlogging": ["drain", "road"],
        "drain_block": ["drain"],
        "garbage": ["garbage"],
        "streetlight": ["lamp"],
        "water_leak": ["drain"],
    },
    "water_board": {
        "waterlogging": ["pipeline", "valve"],
        "water_leak": ["pipeline", "valve"],
    },
    "electricity": {
        "streetlight": ["pole", "transformer", "feeder"],
    },
    "highways": {
        "pothole": ["segment"],
        "waterlogging": ["segment"],
    },
}

ASSET_RADIUS_M = {
    "road": 30, "drain": 30, "lamp": 30, "garbage": 30,
    "pipeline": 50, "valve": 50,
    "pole": 30, "transformer": 30, "feeder": 30,
    "segment": 50, "bridge": 50,
}
DEFAULT_RADIUS_M = 30
HISTORY_RADIUS_M = 100
HANDOVER_RADIUS_M = 30


def _evidence_dict(result: dict, ref: str, department: str) -> dict:
    # `_raw` carries the full tool result (found[]/types_searched/rule_ids/...)
    # for the model/fallback-stub's own reasoning. It is never copied into a
    # final AgentMessage -- validation.py rebuilds the public evidence shape
    # ({kind, source, finding, ref}) straight from the query log instead.
    return {
        "kind": result["kind"],
        "source": f"{department}_registry",
        "finding": result["finding"],
        "ref": ref,
        "_raw": {k: v for k, v in result.items() if k not in ("kind", "finding")},
    }


def build_facts_sheet(case: dict, department: str) -> dict:
    case_id, category, ward = case["id"], case["category"], case["ward"]
    lat, lng = case["lat"], case["lng"]

    evidence: list[dict] = []

    asset_types = CATEGORY_ASSET_PLAN.get(department, {}).get(category)
    if asset_types:
        for t in asset_types:
            radius = ASSET_RADIUS_M.get(t, DEFAULT_RADIUS_M)
            result, ref = registries.assets_near(case_id, department, lat, lng, radius, t)
            evidence.append(_evidence_dict(result, ref, department))
    else:
        # Department has no asset type specifically tied to this category --
        # still run a broad own-registry check so the agent can speak to its
        # own absence rather than staying silent.
        result, ref = registries.assets_near(case_id, department, lat, lng, DEFAULT_RADIUS_M, None)
        evidence.append(_evidence_dict(result, ref, department))

    jr, jref = registries.in_jurisdiction(case_id, department, ward, category)
    evidence.append(_evidence_dict(jr, jref, department))

    hr, href = registries.history(case_id, department, lat, lng, HISTORY_RADIUS_M)
    evidence.append(_evidence_dict(hr, href, department))

    ho, horef = registries.handovers_near(case_id, department, lat, lng, HANDOVER_RADIUS_M)
    evidence.append(_evidence_dict(ho, horef, department))

    matrix_rules = [
        {"id": r.id, "condition": r.condition, "candidates": r.candidates}
        for r in matrix.rules_for_category(category)
    ]

    return {
        "department": department,
        "case_id": case_id,
        "category": category,
        "ward": ward,
        "evidence": evidence,
        "matrix_rules": matrix_rules,
        "candidates_overall": matrix.candidates_for_category(category),
    }
