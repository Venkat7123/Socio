"""POST /agents/{dept}/evaluate -- exposed directly per prompt.md 2.6, mainly
for debugging/demoing a single department's evaluation of a case in
isolation, outside of the engine's automatic hop loop. The engine itself
calls app.agents.evaluate() as a plain function, not over HTTP.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import agents, engine
from app.config import DEPARTMENTS
from app.schemas import AgentMessage, EvaluateRequest

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/{department}/evaluate", response_model=AgentMessage)
def evaluate(department: str, payload: EvaluateRequest):
    if department not in DEPARTMENTS:
        raise HTTPException(status_code=404, detail=f"unknown department '{department}'. Valid: {DEPARTMENTS}")
    try:
        case = engine.get_case(payload.case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    message = agents.evaluate(case, department, payload.thread_id)
    return message
