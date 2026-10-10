"""Step 4 of the pipeline (prompt.md 2.6): "Code: validate and assemble the
message." This is where every rule that the model must not be trusted to
enforce actually gets enforced. On failure the caller (app/agents.py) retries
the model once with the failure reason, then gives up and returns type "error".

The model never writes finding text and never sets confidence -- both are
rebuilt here straight from the query log / confidence table.
"""
from __future__ import annotations

from app import matrix, query_log


class ValidationError(Exception):
    pass


def check_forced_need_info(case: dict, facts: dict) -> tuple[bool, str | None]:
    """Section 2.6 confidence table, last row: "Two own assets of different
    classes within 30 m, or location precision worse than 50 m -> Force
    need_info, 0.40." This overrides whatever the model chose."""
    reasons = []

    accuracy_m = case.get("accuracy_m")
    if accuracy_m is not None and accuracy_m > 50:
        reasons.append(f"location precision ({accuracy_m:.0f} m) is worse than 50 m")

    distinct_types_within_30m: set[str] = set()
    for e in facts["evidence"]:
        if e["kind"] != "presence":
            continue
        for f in e.get("_raw", {}).get("found", []):
            if f["distance_m"] <= 30:
                distinct_types_within_30m.add(f["type"])
    if len(distinct_types_within_30m) >= 2:
        reasons.append(
            f"multiple distinct own asset classes within 30 m: {sorted(distinct_types_within_30m)}"
        )

    if reasons:
        return True, "; ".join(reasons)
    return False, None


def _evidence_from_refs(refs: list[str], case_id: str, department: str) -> tuple[list[dict], dict]:
    logged = query_log.get_many(refs, case_id, department)
    missing_refs = [r for r in refs if r not in logged]
    if missing_refs:
        raise ValidationError(
            f"cite_refs contain refs not found in {department}'s own query log for this case: {missing_refs}"
        )
    # de-dupe, preserve order
    seen: dict[str, dict] = {}
    for r in refs:
        if r in seen:
            continue
        entry = logged[r]
        seen[r] = {
            "kind": entry["result"]["kind"],
            "source": f"{department}_registry",
            "finding": entry["result"]["finding"],
            "ref": r,
        }
    return list(seen.values()), logged


def _min_presence_distance(evidence_objs: list[dict], logged: dict) -> float | None:
    distances = []
    for e in evidence_objs:
        if e["kind"] != "presence":
            continue
        found = logged[e["ref"]]["result"].get("found", [])
        if found:
            distances.append(min(f["distance_m"] for f in found))
    return min(distances) if distances else None


def _accept_confidence(evidence_objs: list[dict], logged: dict) -> float:
    d = _min_presence_distance(evidence_objs, logged)
    if d is None:
        return 0.60
    if d <= 30:
        return 0.90
    if d <= 75:
        return 0.70
    return 0.50


def _reject_confidence(evidence_objs: list[dict], logged: dict) -> float:
    kinds = {e["kind"] for e in evidence_objs}
    if "handover_record" in kinds:
        return 0.85
    jurisdiction_false = any(
        e["kind"] == "jurisdiction_rule" and logged[e["ref"]]["result"].get("in_jurisdiction") is False
        for e in evidence_objs
    )
    if jurisdiction_false:
        return 0.75
    return 0.60  # "absence only" row, capped at 0.70 by construction


def _validate_target_basis(target: str, target_basis: str | None, category: str, logged: dict) -> None:
    if not target_basis:
        raise ValidationError("reject/sub_task requires target_basis")
    if target_basis.startswith("matrix_rule:"):
        rule_id = target_basis.split(":", 1)[1]
        rule = matrix.rule_by_id(rule_id)
        if not rule or rule.category != category or target not in rule.candidates:
            raise ValidationError(
                f"target_basis '{target_basis}' does not support target '{target}' for category '{category}'"
            )
    elif target_basis.startswith("handover_record:"):
        ref = target_basis.split(":", 1)[1]
        entry = logged.get(ref)
        if not entry or entry["result"].get("kind") != "handover_record":
            raise ValidationError(f"target_basis '{target_basis}' does not cite a real handover_record")
        found = entry["result"].get("found", [])
        if not found or found[0]["receiving_department"] != target:
            raise ValidationError(f"handover_record {ref} does not name '{target}' as receiving department")
    else:
        raise ValidationError("target_basis must be 'matrix_rule:<id>' or 'handover_record:<ref>'")


def validate_and_assemble(department: str, case: dict, facts: dict, decision: dict) -> dict:
    """Returns a dict with keys: type, evidence, target, target_basis,
    sub_tasks (raw), missing, confidence, rationale. Raises ValidationError
    on any rule violation (caller retries the model once, then gives up)."""

    forced, forced_reason = check_forced_need_info(case, facts)
    if forced:
        return {
            "type": "need_info",
            "evidence": [e for e in facts["evidence"] if e["kind"] == "presence"],
            "target": None,
            "target_basis": None,
            "sub_tasks": [],
            "missing": ["exact_location"],
            "confidence": 0.40,
            "rationale": f"Forced by validation: {forced_reason}.",
        }

    dtype = decision["type"]
    category = case["category"]

    # Guard added after observing live-LLM behavior: a department that has
    # its own presence evidence for this category (an asset of its own was
    # actually found near the point) has standing -- the only sensible
    # outcomes are "accept" or "split" (own part). A live model sometimes
    # still rejects or asks for more info by over-weighting a generic
    # jurisdiction_rule=false finding and effectively ignoring its own
    # presence evidence. That's wrong per the evidence-strength table
    # (presence is "Strong, proves ownership") and would silently bounce a
    # case the department can already resolve, so it's blocked here rather
    # than left to the model's discretion.
    has_own_presence = any(e["kind"] == "presence" for e in facts["evidence"])
    if dtype in ("reject", "need_info") and has_own_presence:
        raise ValidationError(
            f"your own registry already found a present asset for this category (kind='presence' in the "
            f"facts sheet) -- that is strong evidence of your own standing. You cannot {dtype} while "
            f"ignoring it; choose 'accept' (or 'split' if another department also owns part of this)."
        )

    # Guard added after observing live-LLM behavior: when the agent's own
    # evidence is absence-only and the matrix still has an untried candidate
    # for this category, the correct move is `reject` to that candidate --
    # the engine escalates automatically once every candidate has rejected
    # (rule 7). A live model sometimes asks for more precise location instead
    # ("need_info") even though no tool result actually depends on location
    # precision; that just delays the case instead of letting the engine's
    # own escalation rule do its job. The one legitimate non-forced need_info
    # case is when this department has no further matrix candidate to hand
    # off to at all.
    if dtype == "need_info":
        remaining_candidates = [c for c in matrix.candidates_for_category(category) if c != department]
        if remaining_candidates:
            raise ValidationError(
                f"need_info is not appropriate here: your evidence is absence-only but matrix candidate(s) "
                f"{remaining_candidates} for category '{category}' have not been tried yet. Reject to the "
                f"next candidate instead -- the engine escalates automatically once every candidate has "
                f"rejected absence-only."
            )

    if dtype == "accept":
        evidence_objs, logged = _evidence_from_refs(decision.get("cite_refs", []), case["id"], department)
        if not any(e["kind"] == "presence" for e in evidence_objs):
            raise ValidationError("accept requires at least one cited ref with kind 'presence'")
        # Guard added after observing live-LLM behavior: a department can
        # have presence evidence for part of a complaint AND its own
        # handover_record showing another part was transferred elsewhere
        # (prompt.md 2.7 S2 exactly). A plain "accept" in that situation
        # silently drops the handed-over department's part of the work --
        # "split" is required so that part becomes its own proposed sub_task
        # instead of disappearing.
        if any(e["kind"] == "handover_record" for e in facts["evidence"]):
            raise ValidationError(
                "your own registry also holds a handover_record for this point -- that means another "
                "department owns part of this complaint. Use 'split' instead of 'accept': your own "
                "sub_task citing the presence evidence, plus a proposed sub_task for the handover "
                "record's receiving department with target_basis 'handover_record:<ref>', so that "
                "department's part isn't silently dropped."
            )
        return {
            "type": "accept",
            "evidence": evidence_objs,
            "target": None,
            "target_basis": None,
            "sub_tasks": [],
            "missing": [],
            "confidence": _accept_confidence(evidence_objs, logged),
            "rationale": decision.get("rationale", ""),
        }

    if dtype == "reject":
        target = decision.get("target")
        target_basis = decision.get("target_basis")
        if not target:
            raise ValidationError("reject requires a target")
        if target == department:
            raise ValidationError("reject target cannot be the rejecting department itself")
        candidates = matrix.candidates_for_category(category)
        if target not in candidates:
            raise ValidationError(f"target '{target}' is not a matrix candidate for category '{category}'")
        evidence_objs, logged = _evidence_from_refs(decision.get("cite_refs", []), case["id"], department)
        _validate_target_basis(target, target_basis, category, logged)
        return {
            "type": "reject",
            "evidence": evidence_objs,
            "target": target,
            "target_basis": target_basis,
            "sub_tasks": [],
            "missing": [],
            "confidence": _reject_confidence(evidence_objs, logged),
            "rationale": decision.get("rationale", ""),
        }

    if dtype == "split":
        sub_tasks = decision.get("sub_tasks", [])
        if not sub_tasks:
            raise ValidationError("split requires at least one sub_task")
        own = [s for s in sub_tasks if s["department"] == department]
        if not own:
            raise ValidationError("split requires the department's own sub_task to be present")
        own_evidence, own_logged = _evidence_from_refs(own[0].get("cite_refs", []), case["id"], department)
        if not any(e["kind"] == "presence" for e in own_evidence):
            raise ValidationError("split's own sub_task must cite presence evidence from the own registry")

        part_confidences = [_accept_confidence(own_evidence, own_logged)]
        for s in sub_tasks:
            if s["department"] == department:
                continue
            s_evidence, s_logged = _evidence_from_refs(s.get("cite_refs", []), case["id"], department)
            _validate_target_basis(s["department"], s.get("target_basis"), category, s_logged)
            tb = s["target_basis"]
            part_confidences.append(0.85 if tb.startswith("handover_record:") else 0.75)

        overall_evidence, overall_logged = _evidence_from_refs(
            decision.get("cite_refs", []) or [r for s in sub_tasks for r in s.get("cite_refs", [])],
            case["id"], department,
        )
        return {
            "type": "split",
            "evidence": overall_evidence,
            "target": None,
            "target_basis": None,
            "sub_tasks": sub_tasks,
            "missing": [],
            "confidence": min(part_confidences),
            "rationale": decision.get("rationale", ""),
        }

    if dtype == "need_info":
        missing = decision.get("missing", [])
        if not missing:
            raise ValidationError("need_info requires at least one entry in 'missing'")
        evidence_objs, _logged = _evidence_from_refs(decision.get("cite_refs", []), case["id"], department)
        return {
            "type": "need_info",
            "evidence": evidence_objs,
            "target": None,
            "target_basis": None,
            "sub_tasks": [],
            "missing": missing,
            "confidence": 0.40,
            "rationale": decision.get("rationale", ""),
        }

    raise ValidationError(f"unknown decision type '{dtype}'")
