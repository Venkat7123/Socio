"""The adjudicator (prompt.md 2.6): "It cannot query any registry. It can
only weigh the evidence already in the transcript (presence beats absence, a
handover record beats absence). Its output is logged as advice. The engine or
the zonal officer makes the decision."

Deliberately deterministic (no model call): the engine only reaches the
adjudicator in genuinely stuck states (a blocked return or the hop cap), and
a reproducible, explainable recommendation is more valuable there than a
second LLM call's latency/variance would be.
"""
from __future__ import annotations


def adjudicate(transcript: list[dict], candidates_overall: list[str]) -> dict:
    all_evidence = [e for m in transcript for e in m.get("evidence", [])]
    handover_msgs = [m for m in transcript if any(e["kind"] == "handover_record" for e in m.get("evidence", []))]
    presence_msgs = [m for m in transcript if any(e["kind"] == "presence" for e in m.get("evidence", []))]

    if handover_msgs:
        m = handover_msgs[-1]
        ho_evidence = next(e for e in m["evidence"] if e["kind"] == "handover_record")
        return {
            "proposed_owner": None,  # the named department is in the evidence text; the handover ref is own authority
            "confidence": 0.70,
            "reasoning": (
                f"A handover record is present in the transcript ({ho_evidence['finding']}). "
                "A handover record outweighs absence evidence from any department. Recommend "
                "honoring the handover record as the basis for ownership."
            ),
        }

    if presence_msgs:
        m = presence_msgs[-1]
        from_dept = m["from"].removesuffix("_agent")
        return {
            "proposed_owner": from_dept,
            "confidence": 0.65,
            "reasoning": (
                f"Presence evidence exists from {from_dept} elsewhere in the transcript, which outweighs "
                "absence evidence from other departments. Recommend provisional ownership by that department "
                "pending a field check."
            ),
        }

    proposed = candidates_overall[0] if candidates_overall else None
    return {
        "proposed_owner": proposed,
        "confidence": 0.30,
        "reasoning": (
            "No department's own registry contains the asset at this point -- likely a registry gap at a "
            "jurisdiction edge. Recommend a field survey"
            + (f"; provisional owner {proposed} as the local body." if proposed else ".")
        ),
    }
