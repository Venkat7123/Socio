"""Loads and queries /app/data/jurisdiction_matrix.json.

Per prompt.md 2.4: this is the ONLY knowledge shared between department
agents. It holds rules (which departments are candidates for a category),
never asset data. Nothing in this module touches any registry table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.config import MATRIX_PATH


@dataclass(frozen=True)
class MatrixRule:
    id: str
    category: str
    condition: str
    candidates: list[str]
    action: str | None = None


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(MATRIX_PATH, encoding="utf-8") as f:
        return json.load(f)


def rules_for_category(category: str) -> list[MatrixRule]:
    data = _load()
    return [
        MatrixRule(
            id=r["id"],
            category=r["category"],
            condition=r["condition"],
            candidates=r.get("candidates", []),
            action=r.get("action"),
        )
        for r in data["rules"]
        if r["category"] == category
    ]


def rule_by_id(rule_id: str) -> MatrixRule | None:
    data = _load()
    for r in data["rules"]:
        if r["id"] == rule_id:
            return MatrixRule(
                id=r["id"],
                category=r["category"],
                condition=r["condition"],
                candidates=r.get("candidates", []),
                action=r.get("action"),
            )
    return None


def candidates_for_category(category: str) -> list[str]:
    """Full ordered candidate list for a category (used for engine rule 7:
    'every candidate department has returned absence-only' check)."""
    data = _load()
    return list(data.get("candidates_by_category", {}).get(category, []))


def is_candidate(department: str, category: str) -> tuple[bool, list[str]]:
    """Backs the in_jurisdiction(ward, category) tool.

    Answers a narrower question than "does any matrix rule ever name this
    department for this category": it is True only when the department is
    the category's DEFAULT/primary owner (first entry in
    candidates_by_category) or when a condition-less ("any") rule names it
    outright. A department that is only a candidate under a specific
    condition (e.g. water_board for waterlogging, only on pipeline_burst) is
    NOT generally "in jurisdiction" for the category -- it only becomes
    relevant once its own registry confirms that condition, which is exactly
    what assets_near is for. This mirrors prompt.md 2.7 S2, where
    water_board's in_jurisdiction(waterlogging) is false even though
    water_board appears in the matrix's waterlogging candidate list.

    Ward is accepted by the tool signature for forward-compatibility with
    per-ward overrides, but this demo matrix has none, so ward does not
    change the answer.
    """
    overall = candidates_for_category(category)
    matching_rule_ids = [r.id for r in rules_for_category(category) if department in r.candidates]

    if overall and overall[0] == department:
        return True, matching_rule_ids

    blanket_rule_ids = [r.id for r in rules_for_category(category) if r.condition == "any" and department in r.candidates]
    if blanket_rule_ids:
        return True, blanket_rule_ids

    return False, matching_rule_ids


def departments() -> list[str]:
    return list(_load()["departments"])
