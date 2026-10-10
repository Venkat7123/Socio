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

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "loci.db"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

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
