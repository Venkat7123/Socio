"""Debug/demo endpoints: inspect the shared matrix and per-case query log.
Handy for showing judges "no cross-registry reads happened" live.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app import matrix
from app.config import DEPARTMENTS, MATRIX_PATH
from app.db import session

router = APIRouter(tags=["admin"])


@router.get("/matrix")
def get_matrix():
    with open(MATRIX_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("/query-log/{case_id}")
def get_query_log(case_id: str):
    with session() as conn:
        rows = conn.execute(
            "SELECT ref, department, tool, params, result, created_at FROM query_log "
            "WHERE case_id = ? ORDER BY created_at", (case_id,),
        ).fetchall()
    return [
        {
            "ref": r["ref"], "department": r["department"], "tool": r["tool"],
            "params": json.loads(r["params"]), "result": json.loads(r["result"]), "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/registries/{department}/stats")
def registry_stats(department: str):
    from app.registries import ASSET_TABLES, HISTORY_TABLES, HANDOVER_TABLES

    if department not in DEPARTMENTS:
        raise HTTPException(status_code=404, detail=f"unknown department '{department}'")
    stats = {}
    with session() as conn:
        for asset_type, table in ASSET_TABLES.get(department, {}).items():
            stats[asset_type] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        hist_table = HISTORY_TABLES[department]
        stats["history"] = conn.execute(f"SELECT COUNT(*) AS c FROM {hist_table}").fetchone()["c"]
        ho_table = HANDOVER_TABLES.get(department)
        stats["handovers"] = conn.execute(f"SELECT COUNT(*) AS c FROM {ho_table}").fetchone()["c"] if ho_table else 0
    return stats
