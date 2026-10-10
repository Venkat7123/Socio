from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import engine
from app.schemas import CaseCreate, CaseInfoReply, CaseOut

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate):
    try:
        case_id = engine.create_case(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return engine.get_case_out(case_id)


@router.get("", response_model=list[CaseOut])
def list_cases(status: str | None = None):
    cases = engine.list_cases(status)
    return [engine.get_case_out(c["id"]) for c in cases]


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str):
    try:
        return engine.get_case_out(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{case_id}/info", response_model=CaseOut)
def supply_info(case_id: str, reply: CaseInfoReply):
    try:
        engine.resume_with_info(case_id, reply)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return engine.get_case_out(case_id)
