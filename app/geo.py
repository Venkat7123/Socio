"""Tiny haversine helper -- no need for a GIS dependency at this data scale."""
from __future__ import annotations

import math


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def offset_m(lat: float, lng: float, meters: float, bearing_deg: float) -> tuple[float, float]:
    """Small-distance planar approximation -- fine at the scale of a single ward."""
    bearing = math.radians(bearing_deg)
    dlat = (meters * math.cos(bearing)) / 111320.0
    dlng = (meters * math.sin(bearing)) / (111320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng
