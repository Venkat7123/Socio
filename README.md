# DevFest civic case engine (Track A + B)

    pip install -r backend/requirements.txt
    cd backend && uvicorn app.main:app --reload     # http://localhost:8000/docs
    cd backend && python -m pytest -q               # engine and API tests
    python scripts/export_contracts.py              # regenerate /contracts after editing backend/app/models.py

- `contracts/` schemas, OpenAPI, endpoint list and sample messages (shared with F and C)
- `backend/app/intake.py` intake agent (Whisper speech to text plus a Llama vision model via Groq; copy backend/.env.example to backend/.env and set GROQ_API_KEY), `backend/app/llm.py` the Groq wrapper (timeouts, errors, model names)
- `backend/app/verification.py` verification agent (GPS radius plus Llama vision same-spot/resolved check; VERIFY_RADIUS_M, default 50)
- `backend/app/models.py` contract models (source of truth)
- `backend/app/main.py` engine in `engine.py`, endpoints in `main.py` (only analytics is still a stub); `backend/app/db.py` SQLite schema (cases, media, messages, audit_log)

## Accuracy measurement

    python scripts/build_synthetic_testset.py     # synthetic smoke set (testset/synthetic)
    python scripts/evaluate.py synthetic          # runs real Groq calls, resumable, writes testset/<set>/report.md
    python scripts/evaluate.py real               # the set the pitch number comes from; see testset/README.md

Model calls time out after 15 s (`MODEL_TIMEOUT_S`) and fall back to a retry message; see `contracts/endpoints.md`.
