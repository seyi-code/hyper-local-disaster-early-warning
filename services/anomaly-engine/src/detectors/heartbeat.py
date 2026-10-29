"""
Sensor heartbeat / offline detection.

Tracks last-seen timestamps in memory (and optionally mirrors to Redis).
If a previously-active sensor goes silent longer than OFFLINE_THRESHOLD_SECONDS,
raises a synthetic offline alert.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional, Callable
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

OFFLINE_THRESHOLD = float(os.getenv("OFFLINE_THRESHOLD_SECONDS", "600"))  # 10 min
CHECK_INTERVAL = float(os.getenv("HEARTBEAT_CHECK_INTERVAL", "60"))


class HeartbeatMonitor:
    def __init__(self, on_offline: Optional[Callable] = None):
        self.last_seen: Dict[str, float] = {}
        self.meta: Dict[str, dict] = {}  # sensor_id → {cell_id, metric}
        self.alerted: Dict[str, bool] = {}
        self.on_offline = on_offline

    def touch(self, sensor_id: str, cell_id: str, metric: str) -> None:
        self.last_seen[sensor_id] = time.time()
        self.meta[sensor_id] = {"cell_id": cell_id, "metric": metric}
        self.alerted[sensor_id] = False

    def check(self) -> list[dict]:
        """Return list of newly offline sensors."""
        now = time.time()
        newly = []
        for sensor_id, ts in list(self.last_seen.items()):
            if now - ts > OFFLINE_THRESHOLD and not self.alerted.get(sensor_id):
                self.alerted[sensor_id] = True
                info = self.meta.get(sensor_id, {})
                event = {
                    "sensor_id": sensor_id,
                    "cell_id": info.get("cell_id", "unknown"),
                    "metric": info.get("metric", "unknown"),
                    "silent_for_s": int(now - ts),
                    "last_seen": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                }
                newly.append(event)
                log.warning("Sensor offline", **event)
                if self.on_offline:
                    self.on_offline(event)
        return newly
