"""
GIS / Hyper-local cell helpers — production version.

Loads cell definitions from config/cells.json (or CELLS_CONFIG_PATH).
Supports named cells + optional H3 fallback.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Optional, List, Dict

try:
    import h3
    HAS_H3 = True
except ImportError:
    HAS_H3 = False

_CELL_REGISTRY: Dict[str, dict] = {}
_LOADED = False


def _default_config_path() -> Path:
    candidates = [
        Path(os.getenv("CELLS_CONFIG_PATH", "")),
        Path("/app/config/cells.json"),
        Path(__file__).resolve().parents[4] / "config" / "cells.json",
        Path("config/cells.json"),
    ]
    for p in candidates:
        if p and str(p) != "." and p.is_file():
            return p
    return Path("config/cells.json")


def load_cells(force: bool = False) -> Dict[str, dict]:
    global _CELL_REGISTRY, _LOADED
    if _LOADED and not force:
        return _CELL_REGISTRY

    path = _default_config_path()
    if not path.is_file():
        _CELL_REGISTRY = {
            "cell-kampala-01": {
                "name": "Kampala Central",
                "center": (-0.3136, 32.5811),
                "radius_m": 1200,
                "type": "urban",
                "priority": "high",
                "recipients": [],
                "webhook_urls": [],
            }
        }
        _LOADED = True
        return _CELL_REGISTRY

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    registry: Dict[str, dict] = {}
    for c in data.get("cells", []):
        cid = c["cell_id"]
        center = c.get("center", [0.0, 0.0])
        registry[cid] = {
            "name": c.get("name", cid),
            "center": (float(center[0]), float(center[1])),
            "radius_m": float(c.get("radius_m", 1500)),
            "type": c.get("type", "unknown"),
            "priority": c.get("priority", "medium"),
            "recipients": list(c.get("recipients", [])),
            "webhook_urls": list(c.get("webhook_urls", [])),
        }
    _CELL_REGISTRY = registry
    _LOADED = True
    return _CELL_REGISTRY


def lookup_cell(cell_id: str) -> Optional[dict]:
    load_cells()
    return _CELL_REGISTRY.get(cell_id)


def all_cells() -> Dict[str, dict]:
    return load_cells()


def cells_near(lat: float, lon: float, max_distance_m: float = 3000) -> List[str]:
    load_cells()
    results = []
    for cid, meta in _CELL_REGISTRY.items():
        clat, clon = meta["center"]
        if haversine_m(lat, lon, clat, clon) <= max_distance_m:
            results.append(cid)
    return results


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def latlon_to_h3(lat: float, lon: float, resolution: int = 8) -> str:
    if not HAS_H3:
        raise RuntimeError("h3 package not installed. Run: pip install h3")
    return h3.latlng_to_cell(lat, lon, resolution)


def h3_neighbours(h3_index: str, k: int = 1) -> List[str]:
    if not HAS_H3:
        raise RuntimeError("h3 package not installed")
    return list(h3.grid_disk(h3_index, k))


def suggest_cell_id(lat: float, lon: float, prefer_h3: bool = False, h3_res: int = 8) -> str:
    nearby = cells_near(lat, lon, max_distance_m=1800)
    if nearby and not prefer_h3:
        return nearby[0]
    if HAS_H3:
        return latlon_to_h3(lat, lon, h3_res)
    return f"cell-{lat:.4f}-{lon:.4f}"


def get_recipients(cell_id: str) -> List[str]:
    meta = lookup_cell(cell_id)
    if not meta:
        return []
    return list(meta.get("recipients") or [])


def get_webhooks(cell_id: str) -> List[str]:
    meta = lookup_cell(cell_id)
    if not meta:
        return []
    return list(meta.get("webhook_urls") or [])
