"""Central configuration. Everything here is overridable via env vars / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(__file__).resolve().parent / "data"
MATRIX_PATH = DATA_DIR / "jurisdiction_matrix.json"
ROUTING_SEED_PATH = DATA_DIR / "routing_seed.json"

# Supabase Postgres connection string, e.g.
# postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
# (Supabase dashboard -> Project Settings -> Database -> Connection string -> URI).
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Postgres schema the app's tables live in. Deliberately NOT "public" -- this
# keeps the app's own tables out of Supabase's default schema (where its
# dashboard/PostgREST conventions and any RLS policies normally live) and
# gives tests (tests/conftest.py overrides this to "loci_test") a disposable,
# fully-isolated namespace inside the SAME Supabase project rather than a
# second project or a throwaway local file.
DB_SCHEMA = os.getenv("DB_SCHEMA", "loci").strip() or "loci"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Not specified in the provided spec fragment (sections 1-2.3 were not
# available) -- chosen as a reasonable demo default. Override via .env.
HOP_CAP = int(os.getenv("HOP_CAP", "3"))
ROUTING_THRESHOLD = float(os.getenv("ROUTING_THRESHOLD", "0.6"))

# Not in the spec fragment either. Two tickets of the same category within
# this many meters of each other are treated as the same physical complaint
# (see app/engine.py::_find_duplicate). Chosen in line with the asset search
# radii already used elsewhere (30m for most asset types).
DUPLICATE_RADIUS_M = float(os.getenv("DUPLICATE_RADIUS_M", "25"))

DEPARTMENTS = ["corporation", "water_board", "electricity", "highways"]
