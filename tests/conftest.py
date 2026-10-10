"""Forces a dedicated Postgres schema and the deterministic fallback LLM
backend *before* app.config is ever imported, so tests are reproducible
without a live Groq key and never touch the dev/demo data living in the
app's normal DB_SCHEMA (default "loci") inside the same Supabase project.
DATABASE_URL itself is left untouched -- tests run against the same Supabase
project as the app, just in their own schema."""
import os

os.environ["DB_SCHEMA"] = "loci_test"
os.environ["GROQ_API_KEY"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reseed_before_each_test():
    """Function-scoped (not session-scoped): each test gets a fully fresh
    schema. This matters now that duplicate-ticket linking (app/engine.py::
    _find_duplicate) persists across every case ever created against this DB
    -- several tests reuse the same seeded points (P1/P2/P3) across different
    test functions, and without per-test isolation a later test's "new" case
    at the same point+category would be (correctly) detected as a duplicate
    of an earlier test's case, not a fresh one."""
    from seed_db import seed

    seed(reset=True)
    yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_schema():
    yield
    from app.config import DB_SCHEMA
    from app.db import session as db_session

    with db_session() as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{DB_SCHEMA}" CASCADE')
