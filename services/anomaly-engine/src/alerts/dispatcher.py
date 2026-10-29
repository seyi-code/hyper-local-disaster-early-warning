"""
Production alert dispatcher with escalation policy.

Features:
  - Modes: console | webhook | twilio | multi
  - Per-cell recipient lists + webhooks from GIS config
  - Rate limit (cell+metric)
  - Publishes to alerts:triggered
  - Critical alerts can require human ACK before SMS (escalation policy)
"""

from __future__ import annotations

import os
import time
import json
from typing import Dict, Optional

import structlog
import httpx
import redis

from models.telemetry import AlertEvent
from gis.cells import get_recipients, get_webhooks, lookup_cell
from alerts.escalation import EscalationPolicy

log = structlog.get_logger()


class RateLimiter:
    def __init__(self, cooldown_seconds: float = 60.0):
        self.cooldown = cooldown_seconds
        self._last: Dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        last = self._last.get(key, 0.0)
        if now - last < self.cooldown:
            return False
        self._last[key] = now
        return True


class AlertDispatcher:
    def __init__(self, redis_client: Optional[redis.Redis] = None) -> None:
        self.mode = os.getenv("ALERT_MODE", "console").lower()
        self.webhook_url = os.getenv("WEBHOOK_ALERT_URL", "")
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_FROM_NUMBER", "")
        self.default_recipients = [
            r.strip()
            for r in os.getenv("DEFAULT_ALERT_RECIPIENTS", "").split(",")
            if r.strip()
        ]
        self.rate = RateLimiter(
            cooldown_seconds=float(os.getenv("ALERT_DISPATCH_COOLDOWN", "45"))
        )
        self.redis = redis_client
        self.alerts_stream = os.getenv("ALERTS_STREAM", "alerts:triggered")
        self.escalation = EscalationPolicy(redis_client)

        if self.mode == "twilio" and not all(
            [self.twilio_sid, self.twilio_token, self.twilio_from]
        ):
            log.warning("Twilio credentials incomplete — falling back to console")
            self.mode = "console"

        log.info(
            "Alert dispatcher initialized",
            mode=self.mode,
            require_ack_critical=os.getenv("REQUIRE_ACK_FOR_CRITICAL", "true"),
        )

    def dispatch(self, alert: AlertEvent) -> None:
        key = f"{alert.cell_id}:{alert.metric}"
        if not self.rate.allow(key):
            log.info("Alert suppressed by rate limit", key=key)
            return

        self.escalation.refresh_acks_from_stream()
        self._publish_to_stream(alert)

        if self.mode in ("console", "multi"):
            self._console(alert)
        if self.mode in ("webhook", "multi"):
            self._webhooks(alert)

        if self.mode in ("twilio", "multi"):
            if self.escalation.allow_sms_for(
                alert.severity, alert.cell_id, alert.sensor_id, alert.metric
            ):
                self._twilio(alert)
            else:
                log.info(
                    "SMS deferred pending human ACK or timeout",
                    cell_id=alert.cell_id,
                    severity=alert.severity,
                )

    def _publish_to_stream(self, alert: AlertEvent) -> None:
        if not self.redis:
            return
        try:
            payload = alert.model_dump(mode="json")
            fields = {
                "cell_id": alert.cell_id,
                "sensor_id": alert.sensor_id,
                "metric": alert.metric,
                "value": str(alert.value),
                "direction": alert.direction,
                "score": str(round(alert.score, 3)),
                "severity": alert.severity,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "raw": json.dumps(payload),
            }
            self.redis.xadd(
                self.alerts_stream, fields, maxlen=5000, approximate=True
            )
        except Exception as exc:
            log.error("Failed to publish alert to stream", error=str(exc))

    def _console(self, alert: AlertEvent) -> None:
        cell_meta = lookup_cell(alert.cell_id) or {}
        log.warning(
            "ALERT TRIGGERED",
            cell_id=alert.cell_id,
            cell_name=cell_meta.get("name"),
            sensor_id=alert.sensor_id,
            metric=alert.metric,
            value=alert.value,
            direction=alert.direction,
            score=round(alert.score, 2),
            severity=alert.severity,
            message=alert.message,
        )

    def _webhooks(self, alert: AlertEvent) -> None:
        urls = list(get_webhooks(alert.cell_id))
        if self.webhook_url:
            urls.append(self.webhook_url)
        if not urls:
            return
        payload = alert.model_dump(mode="json")
        for url in urls:
            try:
                with httpx.Client(timeout=8.0) as client:
                    r = client.post(url, json=payload)
                    r.raise_for_status()
                log.info("Webhook delivered", url=url, status=r.status_code)
            except Exception as exc:
                log.error("Webhook failed", url=url, error=str(exc))

    def _twilio(self, alert: AlertEvent) -> None:
        recipients = get_recipients(alert.cell_id) or self.default_recipients
        if not recipients:
            log.warning(
                "No recipients for cell — skipping SMS", cell_id=alert.cell_id
            )
            return
        try:
            from twilio.rest import Client

            client = Client(self.twilio_sid, self.twilio_token)
            cell_meta = lookup_cell(alert.cell_id) or {}
            cell_name = cell_meta.get("name", alert.cell_id)
            body = (
                f"[DISASTER ALERT {alert.severity.upper()}] {cell_name}: "
                f"{alert.message}"
            )
            for to in recipients:
                msg = client.messages.create(
                    body=body[:1600],
                    from_=self.twilio_from,
                    to=to,
                )
                log.info("Twilio SMS sent", sid=msg.sid, to=to)
        except Exception as exc:
            log.error("Twilio send failed", error=str(exc))
            self._console(alert)
