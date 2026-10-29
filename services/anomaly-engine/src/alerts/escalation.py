"""
Escalation / human-in-the-loop policy.

Rules (configurable via env):
  - warning  → dispatch immediately on all configured channels
  - critical → dispatch to console + webhook immediately;
               SMS/voice only after ACK timeout OR if REQUIRE_ACK_FOR_CRITICAL=false

ACK records are read from Redis stream `alerts:acked`.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional, Set
from datetime import datetime, timezone

import structlog
import redis

log = structlog.get_logger()

REQUIRE_ACK = os.getenv("REQUIRE_ACK_FOR_CRITICAL", "true").lower() in ("1", "true", "yes")
ACK_TIMEOUT_S = float(os.getenv("CRITICAL_ACK_TIMEOUT_SECONDS", "300"))  # 5 min


class EscalationPolicy:
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self.pending_critical: Dict[str, float] = {}
        self.acked_keys: Set[str] = set()

    def _key(self, cell_id: str, sensor_id: str, metric: str) -> str:
        return f"{cell_id}:{sensor_id}:{metric}"

    def record_ack(self, cell_id: str, sensor_id: str = "") -> None:
        prefix = f"{cell_id}:"
        for k in list(self.pending_critical.keys()):
            if k.startswith(prefix):
                if not sensor_id or f":{sensor_id}:" in f":{k}:":
                    self.acked_keys.add(k)
                    self.pending_critical.pop(k, None)
        log.info("ACK applied to pending critical", cell_id=cell_id, sensor_id=sensor_id)

    def refresh_acks_from_stream(self) -> None:
        if not self.redis:
            return
        try:
            entries = self.redis.xrevrange("alerts:acked", "+", "-", count=50)
            for _id, fields in entries:
                cell = fields.get("cell_id", "")
                sensor = fields.get("sensor_id", "")
                if cell:
                    self.record_ack(cell, sensor)
        except Exception as e:
            log.debug("Could not refresh acks", error=str(e))

    def allow_sms_for(self, severity: str, cell_id: str, sensor_id: str, metric: str) -> bool:
        """Return True if SMS/voice channels may fire for this alert."""
        if severity != "critical":
            return True
        if not REQUIRE_ACK:
            return True

        key = self._key(cell_id, sensor_id, metric)
        now = time.time()

        if key in self.acked_keys:
            return True

        if key not in self.pending_critical:
            self.pending_critical[key] = now
            log.warning(
                "Critical alert held for human ACK",
                key=key,
                timeout_s=ACK_TIMEOUT_S,
            )
            return False

        if now - self.pending_critical[key] >= ACK_TIMEOUT_S:
            log.warning("Critical ACK timeout — escalating SMS", key=key)
            return True

        return False
