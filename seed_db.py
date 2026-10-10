"""Seeds the SQLite registries with synthetic data for ward W-12.

Per prompt.md 2.5: "Seed one sample ward (W-12), with about 60 to 100 assets
per department. Use invented coordinates and IDs, and mark them synthetic
everywhere." All rows here have synthetic=1; nothing is a real asset.

Also plants the exact scenario fixtures from the "Seed data to plant for the
scenarios" table (2.5) at points P1-P4, so the four worked scenarios in 2.7
reproduce deterministically:
  P1 (S1): corporation road segment through the point.
  P2 (S2): corporation storm drain SD-112 ~18m away, no municipal road at the
           point, handover record HO-07 (road handed to highways); highways
           segment H-07 through the point; water_board has no pipeline/valve
           within 50m.
  P3 (S3): corporation has no lamp within 30m; electricity pole EP-334 ~12m away.
  P4 (S4): corporation has no road segment and no handover record; highways
           has no segment within 50m.

Run directly to force a full reset: `python seed_db.py --reset`
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db
from app.config import DATA_DIR
from app.geo import distance_m, offset_m

RNG_SEED = 42
WARD = "W-12"

with open(DATA_DIR / "seed_points.json", encoding="utf-8") as f:
    _SEED = json.load(f)
BBOX = _SEED["bbox"]
POINTS = _SEED["points"]  # P1..P4 -> {lat, lng, scenario, category}

MIN_CLEARANCE_M = 65.0  # noise assets must stay this far from every P1-P4 point


def _random_point(rng: random.Random) -> tuple[float, float]:
    while True:
        lat = rng.uniform(BBOX["lat_min"], BBOX["lat_max"])
        lng = rng.uniform(BBOX["lng_min"], BBOX["lng_max"])
        if all(distance_m(lat, lng, p["lat"], p["lng"]) >= MIN_CLEARANCE_M for p in POINTS.values()):
            return lat, lng


def _iso_days_ago(rng: random.Random, max_days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=rng.randint(0, max_days))
    return dt.isoformat()


def _insert_noise(conn, table: str, id_prefix: str, n: int, rng: random.Random, extra_cols: dict | None = None) -> None:
    extra_cols = extra_cols or {}
    col_names = ["id", "lat", "lng", "ward", "synthetic"] + list(extra_cols.keys())
    placeholders = ", ".join("?" for _ in col_names)
    for i in range(n):
        lat, lng = _random_point(rng)
        row = [f"{id_prefix}-{i:04d}", lat, lng, WARD, 1] + [v(rng) if callable(v) else v for v in extra_cols.values()]
        conn.execute(f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})", row)


def _insert_history(conn, table: str, id_prefix: str, n: int, rng: random.Random, category_choices: list[str]) -> None:
    outcomes = ["ASSIGNED", "REJECTED", "ESCALATED"]
    for i in range(n):
        lat, lng = _random_point(rng)
        conn.execute(
            f"INSERT INTO {table} (id, lat, lng, category, outcome, created_at, ward, synthetic) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (f"{id_prefix}-{i:04d}", lat, lng, rng.choice(category_choices), rng.choice(outcomes),
             _iso_days_ago(rng, 365), WARD),
        )


def seed(reset: bool = True) -> None:
    db.init_db(reset=reset)
    rng = random.Random(RNG_SEED)

    with db.session() as conn:
        # ---------------- corporation ----------------
        _insert_noise(conn, "corporation_roads", "RD", rng.randint(18, 24), rng, {"length_m": lambda r: r.uniform(50, 400)})
        _insert_noise(conn, "corporation_drains", "SD", rng.randint(18, 24), rng)
        _insert_noise(conn, "corporation_lamps", "LP", rng.randint(18, 24), rng)
        _insert_noise(conn, "corporation_garbage_points", "GB", rng.randint(18, 24), rng)
        _insert_history(conn, "corporation_history", "CH", rng.randint(20, 30), rng,
                         ["pothole", "waterlogging", "drain_block", "garbage", "streetlight"])

        # P1 (S1): municipal road through the point.
        conn.execute(
            "INSERT INTO corporation_roads (id, lat, lng, length_m, ward, synthetic) VALUES (?, ?, ?, ?, ?, 1)",
            ("RD-001", POINTS["P1"]["lat"], POINTS["P1"]["lng"], 180.0, WARD),
        )
        # P2 (S2): storm drain ~18m away; NO road at P2 (handled by clearance); handover HO-07.
        d_lat, d_lng = offset_m(POINTS["P2"]["lat"], POINTS["P2"]["lng"], 18, 40)
        conn.execute(
            "INSERT INTO corporation_drains (id, lat, lng, ward, synthetic) VALUES (?, ?, ?, ?, 1)",
            ("SD-112", d_lat, d_lng, WARD),
        )
        conn.execute(
            "INSERT INTO corporation_handovers (id, lat, lng, asset_type, receiving_department, order_ref, note, ward, synthetic) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            ("HO-07", POINTS["P2"]["lat"], POINTS["P2"]["lng"], "road", "highways", "GO-2024-HWY-07",
             "Road segment transferred to Highways Dept.", WARD),
        )
        # A couple of noise handovers elsewhere, away from all scenario points, for realism.
        for i, recv in enumerate(["highways", "water_board"]):
            lat, lng = _random_point(rng)
            conn.execute(
                "INSERT INTO corporation_handovers (id, lat, lng, asset_type, receiving_department, order_ref, note, ward, synthetic) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (f"HO-{90+i}", lat, lng, "road", recv, f"GO-2023-{90+i}", "Historical handover.", WARD),
            )

        # ---------------- water_board ----------------
        _insert_noise(conn, "water_board_pipelines", "PL", rng.randint(28, 36), rng, {"zone": lambda r: r.choice(["Z1", "Z2", "Z3"])})
        _insert_noise(conn, "water_board_valves", "VL", rng.randint(28, 36), rng, {"zone": lambda r: r.choice(["Z1", "Z2", "Z3"])})
        _insert_history(conn, "water_board_history", "WH", rng.randint(15, 25), rng, ["waterlogging", "water_leak"])
        # P2: explicitly no pipeline/valve within 50m -- satisfied by MIN_CLEARANCE_M (65m) already.

        # ---------------- electricity ----------------
        _insert_noise(conn, "electricity_poles", "EP", rng.randint(22, 28), rng)
        _insert_noise(conn, "electricity_transformers", "TR", rng.randint(22, 28), rng)
        _insert_noise(conn, "electricity_feeders", "FD", rng.randint(22, 28), rng)
        _insert_history(conn, "electricity_history", "EH", rng.randint(15, 25), rng, ["streetlight"])

        # P3: pole EP-334 ~12m away; no lamp within 30m (handled by clearance on corporation_lamps).
        p_lat, p_lng = offset_m(POINTS["P3"]["lat"], POINTS["P3"]["lng"], 12, 200)
        conn.execute(
            "INSERT INTO electricity_poles (id, lat, lng, ward, synthetic) VALUES (?, ?, ?, ?, 1)",
            ("EP-334", p_lat, p_lng, WARD),
        )

        # ---------------- highways ----------------
        _insert_noise(conn, "highways_segments", "HW", rng.randint(28, 36), rng, {"road_name": lambda r: f"SH-{r.randint(10, 99)}"})
        _insert_noise(conn, "highways_bridges", "BR", rng.randint(10, 14), rng)
        _insert_history(conn, "highways_history", "HH", rng.randint(15, 25), rng, ["pothole", "waterlogging"])

        # P2: highway segment H-07 through the point (receives the handed-over road).
        conn.execute(
            "INSERT INTO highways_segments (id, lat, lng, road_name, ward, synthetic) VALUES (?, ?, ?, ?, ?, 1)",
            ("H-07", POINTS["P2"]["lat"], POINTS["P2"]["lng"], "SH-07", WARD),
        )
        # P4: no segment within 50m -- satisfied by MIN_CLEARANCE_M; no road/handover at P4 either.

    print("Seed complete.")
    for table in [
        "corporation_roads", "corporation_drains", "corporation_lamps", "corporation_garbage_points",
        "corporation_handovers", "water_board_pipelines", "water_board_valves",
        "electricity_poles", "electricity_transformers", "electricity_feeders",
        "highways_segments", "highways_bridges",
    ]:
        with db.session() as conn:
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        print(f"  {table}: {n} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete the existing DB file and reseed from scratch.")
    args = parser.parse_args()
    seed(reset=args.reset)
