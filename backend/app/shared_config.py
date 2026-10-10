"""Shared jurisdiction matrix and first-contact triage rule, read from /contracts (or MATRIX_PATH / ROUTING_SEED_PATH).

These two files are the only knowledge shared between the backend and the Track C department agents. They hold rules,
never asset data. Neither service keeps its own copy.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent.parent.parent / "contracts"
MATRIX_PATH = Path(os.environ.get("MATRIX_PATH", CONTRACTS / "jurisdiction_matrix.json"))
ROUTING_SEED_PATH = Path(os.environ.get("ROUTING_SEED_PATH", CONTRACTS / "routing_seed.json"))
DEFAULT_WARD = "W-12"


@lru_cache(maxsize=1)
def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _seed() -> dict:
    return json.loads(ROUTING_SEED_PATH.read_text(encoding="utf-8"))


def categories() -> list[str]:
    return list(_matrix()["candidates_by_category"])


def departments() -> list[str]:
    return list(_matrix()["departments"])


def candidates_for(category: str) -> list[str]:
    """Ordered departments that may own a category; empty means a human must triage it."""
    return list(_matrix()["candidates_by_category"].get(category, []))


def rule(rule_id: str) -> dict | None:
    """A matrix rule by id (M-POT-2 ...), or None."""
    return next((r for r in _matrix()["rules"] if r["id"] == rule_id), None)


def first_contact(category: str, ward: str = DEFAULT_WARD) -> tuple[str | None, float]:
    """(department, confidence) of the department whose agent is asked first, or (None, 0) for human triage."""
    for row in _seed()["rows"]:
        if row["category"] == category and row["ward"] == ward:
            if row.get("action") == "escalate_to_human_triager" or row.get("department") is None:
                return None, 0.0
            return row["department"], row["confidence"]
    return None, 0.0
