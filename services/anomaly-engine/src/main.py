"""
Anomaly Engine — Redis Stream consumer + CUSUM detectors.

Consumes telemetry:raw, maintains per-(cell, metric) CUSUM state,
and fires alerts when a sustained statistical shift is detected.
"""

from __future__ import annotations

import os
import sys
import time
import signal
from datetime import datetime, timezone
from typing import Dict, Tuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structlog
import redis
from redis.exceptions import ResponseError

from detectors.cusum import CusumDetector, CusumConfig
from detectors.heartbeat import HeartbeatMonitor
from models.telemetry import TelemetryEvent, AlertEvent
from alerts.dispatcher import AlertDispatcher
from gis.cells import load_cells

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_STREAM = os.getenv("REDIS_STREAM", "telemetry:raw")
GROUP = os.getenv("REDIS_CONSUMER_GROUP", "anomaly-workers")
CONSUMER = os.getenv("REDIS_CONSUMER_NAME", "worker-1")

CUSUM_K = float(os.getenv("CUSUM_K", "0.5"))
CUSUM_H = float(os.getenv("CUSUM_H", "5.0"))
BASELINE_WINDOW = int(os.getenv("BASELINE_WINDOW", "30"))
MIN_SAMPLES = int(os.getenv("MIN_SAMPLES_BEFORE_DETECT", "15"))
COOLDOWN = float(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))

detectors: Dict[Tuple[str, str], CusumDetector] = {}
dispatcher: AlertDispatcher | None = None
heartbeat = HeartbeatMonitor()
running = True
_last_hb_check = 0.0


def get_detector(cell_id: str, metric: str) -> CusumDetector:
    key = (cell_id, metric)
    if key not in detectors:
        cfg = CusumConfig(
            k=CUSUM_K,
            h=CUSUM_H,
            baseline_window=BASELINE_WINDOW,
            min_samples=MIN_SAMPLES,
            cooldown_seconds=COOLDOWN,
        )
        detectors[key] = CusumDetector(cfg)
        log.info("Created new CUSUM detector", cell_id=cell_id, metric=metric)
    return detectors[key]


def parse_stream_entry(entry_id: str, fields: dict) -> TelemetryEvent | None:
    try:
        ts_raw = fields.get("timestamp")
        if ts_raw and ts_raw.endswith("Z"):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        elif ts_raw:
            ts = datetime.fromisoformat(ts_raw)
        else:
            ts = datetime.now(timezone.utc)

        return TelemetryEvent(
            sensor_id=fields["sensor_id"],
            cell_id=fields["cell_id"],
            metric=fields["metric"],
            value=float(fields["value"]),
            timestamp=ts,
            lat=float(fields["lat"]) if fields.get("lat") else None,
            lon=float(fields["lon"]) if fields.get("lon") else None,
            battery_pct=float(fields["battery_pct"]) if fields.get("battery_pct") else None,
            stream_id=entry_id,
        )
    except Exception as exc:
        log.warning("Failed to parse stream entry", entry_id=entry_id, error=str(exc))
        return None


def process_event(event: TelemetryEvent) -> None:
    heartbeat.touch(event.sensor_id, event.cell_id, event.metric)
    det = get_detector(event.cell_id, event.metric)
    triggered, direction, score = det.update(event.value)

    if not triggered:
        return

    if event.metric == "water_level_cm":
        msg = (
            f"Water level anomaly ({direction}) at sensor {event.sensor_id}: "
            f"{event.value:.1f} cm (CUSUM score {score:.1f})"
        )
        severity = "critical" if direction == "up" and score > CUSUM_H * 1.5 else "warning"
    elif event.metric == "pm25_ugm3":
        msg = (
            f"Air quality (PM2.5) anomaly ({direction}) at sensor {event.sensor_id}: "
            f"{event.value:.1f} µg/m³ (CUSUM score {score:.1f})"
        )
        severity = "critical" if direction == "up" else "warning"
    else:
        msg = (
            f"{event.metric} anomaly ({direction}) at sensor {event.sensor_id}: "
            f"{event.value:.2f} (CUSUM score {score:.1f})"
        )
        severity = "warning"

    alert = AlertEvent(
        cell_id=event.cell_id,
        sensor_id=event.sensor_id,
        metric=event.metric,
        value=event.value,
        direction=direction or "unknown",
        score=score,
        timestamp=datetime.now(timezone.utc),
        message=msg,
        severity=severity,
    )
    if dispatcher:
        dispatcher.dispatch(alert)


def ensure_consumer_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(REDIS_STREAM, GROUP, id="0", mkstream=True)
        log.info("Created consumer group", group=GROUP, stream=REDIS_STREAM)
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.info("Consumer group already exists", group=GROUP)
        else:
            raise


def shutdown(signum, frame):
    global running
    log.info("Shutdown signal received")
    running = False


def main() -> None:
    global dispatcher, _last_hb_check
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    cells = load_cells()
    log.info("Loaded cell registry", count=len(cells), cells=list(cells.keys()))

    log.info(
        "Anomaly engine starting",
        redis=REDIS_URL,
        stream=REDIS_STREAM,
        group=GROUP,
        consumer=CONSUMER,
        cusum_k=CUSUM_K,
        cusum_h=CUSUM_H,
    )

    r = redis.from_url(REDIS_URL, decode_responses=True)
    dispatcher = AlertDispatcher(redis_client=r)
    ensure_consumer_group(r)

    while running:
        try:
            pending = r.xpending_range(REDIS_STREAM, GROUP, min="-", max="+", count=10)
            for p in pending:
                idle_ms = p.get("time_since_delivered", 0)
                if idle_ms > 60_000:
                    claimed = r.xclaim(
                        REDIS_STREAM, GROUP, CONSUMER, min_idle_time=60_000, message_ids=[p["message_id"]]
                    )
                    for entry_id, fields in claimed:
                        if fields:
                            event = parse_stream_entry(entry_id, fields)
                            if event:
                                process_event(event)
                            r.xack(REDIS_STREAM, GROUP, entry_id)

            now = time.time()
            if now - _last_hb_check > 60:
                _last_hb_check = now
                for offline in heartbeat.check():
                    if dispatcher:
                        alert = AlertEvent(
                            cell_id=offline["cell_id"],
                            sensor_id=offline["sensor_id"],
                            metric=offline.get("metric", "heartbeat"),
                            value=0.0,
                            direction="down",
                            score=0.0,
                            timestamp=datetime.now(timezone.utc),
                            message=(
                                f"Sensor {offline['sensor_id']} offline "
                                f"(silent {offline['silent_for_s']}s)"
                            ),
                            severity="warning",
                        )
                        dispatcher.dispatch(alert)

            results = r.xreadgroup(
                GROUP, CONSUMER, {REDIS_STREAM: ">"}, count=20, block=5000
            )
            if not results:
                continue

            for stream_name, messages in results:
                for entry_id, fields in messages:
                    event = parse_stream_entry(entry_id, fields)
                    if event:
                        process_event(event)
                    r.xack(REDIS_STREAM, GROUP, entry_id)

        except redis.ConnectionError as e:
            log.error("Redis connection lost, retrying…", error=str(e))
            time.sleep(3)
        except Exception as e:
            log.exception("Unexpected error in main loop", error=str(e))
            time.sleep(1)

    log.info("Anomaly engine stopped cleanly")


if __name__ == "__main__":
    main()
