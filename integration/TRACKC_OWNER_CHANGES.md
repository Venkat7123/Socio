# Changes for the Track C owner

`trackc-owner.patch` is the exact diff. It applies cleanly to `github.com/Venkat7123/Socio` (commit `76a2729`):

    git apply integration/trackc-owner.patch

The backend (Tracks A and B) is the engine of record. It owns cases, hops (cap 2), escalation and the audit log. It calls your
agents; it does not use your cases table, hop loop, adjudicator or 3-hop default. Everything below makes the agents callable
that way. Your own engine, routers and tests still work.

## What the patch changes

| # | Change | Where |
|---|---|---|
| 1 | **Stateless evaluate.** `POST /agents/{dept}/evaluate-inline` takes `{case, transcript, thread_id}` and returns an `AgentMessage`. Nothing is written to `cases` or `messages`. `agents.evaluate()` gains `transcript=` and `persist=` arguments. | `routers/agents.py`, `agents.py`, `schemas.py` |
| 2 | **Shared config by env var.** `MATRIX_PATH` and `ROUTING_SEED_PATH` override the file locations, so both services read one copy. The duplicate `contents/` folder is deleted. | `config.py` |
| 3 | **Timeout, no silent fallback.** A Groq call (`complete_json`) is cut off after `LLM_TIMEOUT_S` (15 s) with no SDK retries. On any failure it raises `LLMUnavailable` and the pipeline returns a message of type `error` with `error_reason: llm_unavailable: ...` and `model_backend: "unavailable"`. The rule stub runs only when `LLM_BACKEND=rules` is set explicitly, and is labelled `model_backend: "rules"`. Gemini is replaced by Groq (`GROQ_API_KEY`, `GROQ_MODEL`, default `openai/gpt-oss-120b`). | `llm.py`, `agents.py`, `config.py`, `requirements.txt` |
| 4 | **Evidence required on reject.** A reject that cites no refs is refused (before, an empty `cite_refs` passed validation). | `validation.py` |
| 5 | **Confidence cap.** A reject backed only by absence, history or a "not my jurisdiction" finding is capped at 0.70 (before, absence plus jurisdiction gave 0.75, while the engine already treated that reject as absence-only). | `validation.py` |

## Also

- `tests/test_integration_patch.py`: 8 tests for the changes above. Your suite goes from 13 to 21 passing.
- `tests/conftest.py` sets `LLM_BACKEND=rules`, because tests no longer fall back to rules silently.
- Four tests in `tests/test_tickets.py` (T4 to T7) fail on the original repo and still fail after the patch. They are
  unrelated to this change and are left alone.

## Needed from you

- Confirm `openai/gpt-oss-120b` (JSON object mode) is acceptable as the agents' model. Any Groq model that supports
  `json_object` works.
- The registries are seeded only for ward W-12 around (13.08, 80.27). The backend uses your scenario points P1 to P4 for its tests.
- `README.md` is empty, and `ARCHITECTURE.md` and `prompt.md`, which the code comments cite, are not in the repo.
