"""Forces a dedicated test DB and the deterministic fallback LLM backend
*before* app.config is ever imported, so tests are reproducible without a
live Gemini key."""
import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent.parent / "loci_test.db"
os.environ["DB_PATH"] = str(TEST_DB)
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reseed_before_each_test():
    """Function-scoped (not session-scoped): each test gets a fully fresh DB.
    This matters now that duplicate-ticket linking (app/engine.py::
    _find_duplicate) persists across every case ever created against this DB
    -- several tests reuse the same seeded points (P1/P2/P3) across different
    test functions, and without per-test isolation a later test's "new" case
    at the same point+category would be (correctly) detected as a duplicate
    of an earlier test's case, not a fresh one."""
    from seed_db import seed

    seed(reset=True)
    yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db_file():
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()
