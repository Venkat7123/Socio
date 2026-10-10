"""Per-department registry tools: assets_near, in_jurisdiction, history, handovers_near.

Per prompt.md 2.5: "each agent can query only its own registry... The engine
enforces this by giving each agent only its own tool set." This module is
that enforcement boundary -- every function takes `department` and only ever
touches that department's own tables. There is no function here, or anywhere
else in the codebase, that lets one department read another's asset tables.

Every call is logged via app.query_log.log() and returns (payload, ref).
Findings text (the human-readable sentence) is built here in code, never by
the model -- see prompt.md 2.6 step 2 / step 4.
"""
from __future__ import annotations

from app import matrix, query_log
from app.db import session
from app.geo import distance_m

ASSET_TABLES: dict[str, dict[str, str]] = {
    "corporation": {
        "road": "corporation_roads",
        "drain": "corporation_drains",
        "lamp": "corporation_lamps",
        "garbage": "corporation_garbage_points",
    },
    "water_board": {
        "pipeline": "water_board_pipelines",
        "valve": "water_board_valves",
    },
    "electricity": {
        "pole": "electricity_poles",
        "transformer": "electricity_transformers",
        "feeder": "electricity_feeders",
    },
    "highways": {
        "segment": "highways_segments",
        "bridge": "highways_bridges",
    },
}

HISTORY_TABLES = {dept: f"{dept}_history" for dept in ASSET_TABLES}

HANDOVER_TABLES = {
    "corporation": "corporation_handovers",
    # Other departments do not hold handover records in this demo seed
    # (prompt.md 2.5: "In practice only the Corporation registry holds such
    # records in the demo seed.")
}

ASSET_TYPE_LABELS = {
    "road": "municipal road segment",
    "drain": "storm drain",
    "lamp": "streetlight lamp",
    "garbage": "garbage collection point",
    "pipeline": "pipeline",
    "valve": "valve",
    "pole": "pole",
    "transformer": "transformer",
    "feeder": "feeder line",
    "segment": "highway/state-road segment",
    "bridge": "bridge",
}


def _asset_types_for(department: str, asset_type: str | None) -> list[str]:
    table_map = ASSET_TABLES.get(department, {})
    if asset_type:
        if asset_type not in table_map:
            return []
        return [asset_type]
    return list(table_map.keys())


def assets_near(
    case_id: str, department: str, lat: float, lng: float, radius_m: float, asset_type: str | None = None
) -> tuple[dict, str]:
    table_map = ASSET_TABLES.get(department, {})
    types_to_search = _asset_types_for(department, asset_type)
    found = []
    with session() as conn:
        for t in types_to_search:
            table = table_map[t]
            rows = conn.execute(f"SELECT id, lat, lng FROM {table}").fetchall()
            for row in rows:
                d = distance_m(lat, lng, row["lat"], row["lng"])
                if d <= radius_m:
                    found.append({"id": row["id"], "type": t, "distance_m": round(d, 1)})
    found.sort(key=lambda x: x["distance_m"])

    if found:
        labels = ", ".join(f"{ASSET_TYPE_LABELS.get(a['type'], a['type'])} {a['id']}" for a in found[:3])
        finding = f"Found {labels} within {radius_m:.0f} m of the reported point."
    else:
        searched_labels = " or ".join(ASSET_TYPE_LABELS.get(t, t) for t in types_to_search) or "assets"
        finding = f"No {searched_labels} within {radius_m:.0f} m of the reported point (searched {department} registry)."

    result = {
        "found": found,
        "radius_m": radius_m,
        "types_searched": types_to_search,
        "finding": finding,
        "kind": "presence" if found else "absence",
    }
    ref = query_log.log(
        case_id, department, "assets_near",
        {"lat": lat, "lng": lng, "radius_m": radius_m, "type": asset_type}, result,
    )
    return result, ref


def in_jurisdiction(case_id: str, department: str, ward: str, category: str) -> tuple[dict, str]:
    is_cand, rule_ids = matrix.is_candidate(department, category)
    if is_cand:
        finding = f"{category} is a {department} category in {ward} (matrix rule(s) {', '.join(rule_ids)})."
    else:
        finding = f"{category} is not a {department} category in {ward}."
    result = {
        "in_jurisdiction": is_cand,
        "rule_ids": rule_ids,
        "finding": finding,
        "kind": "jurisdiction_rule",
    }
    ref = query_log.log(case_id, department, "in_jurisdiction", {"ward": ward, "category": category}, result)
    return result, ref


def history(case_id: str, department: str, lat: float, lng: float, radius_m: float) -> tuple[dict, str]:
    table = HISTORY_TABLES[department]
    with session() as conn:
        rows = conn.execute(f"SELECT lat, lng, category, outcome FROM {table}").fetchall()
    nearby = [r for r in rows if distance_m(lat, lng, r["lat"], r["lng"]) <= radius_m]
    outcomes: dict[str, int] = {}
    for r in nearby:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    finding = (
        f"{len(nearby)} past {department} complaint(s) within {radius_m:.0f} m: {outcomes}"
        if nearby
        else f"No past {department} complaints within {radius_m:.0f} m of the reported point."
    )
    result = {"count": len(nearby), "outcomes": outcomes, "finding": finding, "kind": "history"}
    ref = query_log.log(case_id, department, "history", {"lat": lat, "lng": lng, "radius_m": radius_m}, result)
    return result, ref


def handovers_near(case_id: str, department: str, lat: float, lng: float, radius_m: float) -> tuple[dict, str]:
    table = HANDOVER_TABLES.get(department)
    found = []
    if table:
        with session() as conn:
            rows = conn.execute(
                f"SELECT id, lat, lng, asset_type, receiving_department, order_ref FROM {table}"
            ).fetchall()
        for row in rows:
            d = distance_m(lat, lng, row["lat"], row["lng"])
            if d <= radius_m:
                found.append({
                    "id": row["id"],
                    "asset_type": row["asset_type"],
                    "receiving_department": row["receiving_department"],
                    "order_ref": row["order_ref"],
                    "distance_m": round(d, 1),
                })
    found.sort(key=lambda x: x["distance_m"])
    if found:
        f0 = found[0]
        finding = (
            f"Own handover record {f0['id']}: {ASSET_TYPE_LABELS.get(f0['asset_type'], f0['asset_type'])} "
            f"at this point was handed over to {f0['receiving_department']} under order {f0['order_ref']}."
        )
    else:
        finding = f"No own handover record within {radius_m:.0f} m of the reported point."
    result = {"found": found, "finding": finding, "kind": "handover_record" if found else "absence"}
    ref = query_log.log(case_id, department, "handovers_near", {"lat": lat, "lng": lng, "radius_m": radius_m}, result)
    return result, ref
