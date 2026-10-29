"""
Archive Service — durable storage for telemetry and alerts.

Tails Redis streams `telemetry:raw` and `alerts:triggered` and writes
into Postgres (works with plain Postgres or TimescaleDB).
"""

from __future__ import annotations

import os
import time
import signal
import json
from datetime import datetime, timezone

import structlog
import redis
from redis.exceptions import ResponseError
import psycopg2
from psycopg2.extras import execute_values

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TELEMETRY_STREAM = os.getenv("REDIS_STREAM", "telemetry:raw")
ALERTS_STREAM = os.getenv("ALERTS_STREAM", "alerts:triggered")
GROUP = os.getenv("ARCHIVE_CONSUMER_GROUP", "archive-workers")
CONSUMER = os.getenv("REDIS_CONSUMER_NAME", "archive-1")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://earlywarn:earlywarn@localhost:5432/earlywarn"
)
running = True

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id              BIGSERIAL PRIMARY KEY,
    stream_id       TEXT,
    sensor_id       TEXT NOT NULL,
    cell_id         TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    battery_pct     DOUBLE PRECISION,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_telemetry_cell_time ON telemetry (cell_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_sensor_time ON telemetry (sensor_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    stream_id       TEXT,
    cell_id         TEXT NOT NULL,
    sensor_id       TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           DOUBLE PRECISION,
    direction       TEXT,
    score           DOUBLE PRECISION,
    severity        TEXT NOT NULL DEFAULT 'warning',
    message         TEXT,
    recorded_at     TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_cell_time ON alerts (cell_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS sensor_heartbeat (
    sensor_id       TEXT PRIMARY KEY,
    cell_id         TEXT,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    last_metric     TEXT,
    last_value      DOUBLE PRECISION,
    offline_alerted BOOLEAN NOT NULL DEFAULT FALSE
);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('telemetry', 'recorded_at', if_not_exists => TRUE, migrate_data => TRUE);
    PERFORM create_hypertable('alerts', 'recorded_at', if_not_exists => TRUE, migrate_data => TRUE);
  END IF;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'Timescale hypertable setup skipped: %', SQLERRM;
END $$;

CREATE OR REPLACE FUNCTION retain_telemetry(days integer DEFAULT 90) RETURNS void AS $$
BEGIN
  DELETE FROM telemetry WHERE recorded_at < NOW() - make_interval(days => days);
END;
$$ LANGUAGE plpgsql;
"""


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
    log.info("Schema ensured")


def ensure_group(r: redis.Redis, stream: str) -> None:
    try:
        r.xgroup_create(stream, GROUP, id="0", mkstream=True)
        log.info("Created consumer group", stream=stream, group=GROUP)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def archive_telemetry(conn, entry_id: str, fields: dict) -> None:
    try:
        ts = fields.get("timestamp") or datetime.now(timezone.utc).isoformat()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO telemetry
                   (stream_id, sensor_id, cell_id, metric, value, recorded_at, lat, lon, battery_pct)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    entry_id,
                    fields.get("sensor_id"),
                    fields.get("cell_id"),
                    fields.get("metric"),
                    float(fields.get("value", 0)),
                    ts,
                    float(fields["lat"]) if fields.get("lat") else None,
                    float(fields["lon"]) if fields.get("lon") else None,
                    float(fields["battery_pct"]) if fields.get("battery_pct") else None,
                ),
            )
            cur.execute(
                """INSERT INTO sensor_heartbeat (sensor_id, cell_id, last_seen_at, last_metric, last_value, offline_alerted)
                   VALUES (%s,%s,%s,%s,%s,FALSE)
                   ON CONFLICT (sensor_id) DO UPDATE SET
                     cell_id=EXCLUDED.cell_id, last_seen_at=EXCLUDED.last_seen_at,
                     last_metric=EXCLUDED.last_metric, last_value=EXCLUDED.last_value,
                     offline_alerted=FALSE""",
                (
                    fields.get("sensor_id"),
                    fields.get("cell_id"),
                    ts,
                    fields.get("metric"),
                    float(fields.get("value", 0)),
                ),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("Failed to archive telemetry", error=str(e), entry_id=entry_id)


def archive_alert(conn, entry_id: str, fields: dict) -> None:
    try:
        ts = fields.get("timestamp") or datetime.now(timezone.utc).isoformat()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO alerts
                   (stream_id, cell_id, sensor_id, metric, value, direction, score, severity, message, recorded_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    entry_id,
                    fields.get("cell_id"),
                    fields.get("sensor_id"),
                    fields.get("metric"),
                    float(fields["value"]) if fields.get("value") else None,
                    fields.get("direction"),
                    float(fields["score"]) if fields.get("score") else None,
                    fields.get("severity", "warning"),
                    fields.get("message"),
                    ts,
                ),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error("Failed to archive alert", error=str(e), entry_id=entry_id)


def shutdown(signum, frame):
    global running
    running = False


def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    conn = get_conn()
    ensure_schema(conn)

    r = redis.from_url(REDIS_URL, decode_responses=True)
    ensure_group(r, TELEMETRY_STREAM)
    ensure_group(r, ALERTS_STREAM)

    log.info("Archive service ready", telemetry=TELEMETRY_STREAM, alerts=ALERTS_STREAM)

    while running:
        try:
            results = r.xreadgroup(
                GROUP, CONSUMER,
                {TELEMETRY_STREAM: ">", ALERTS_STREAM: ">"},
                count=50, block=5000,
            )
            if not results:
                continue
            for stream_name, messages in results:
                for entry_id, fields in messages:
                    if stream_name == TELEMETRY_STREAM:
                        archive_telemetry(conn, entry_id, fields)
                    else:
                        archive_alert(conn, entry_id, fields)
                    r.xack(stream_name, GROUP, entry_id)
        except redis.ConnectionError as e:
            log.error("Redis connection lost", error=str(e))
            time.sleep(3)
        except Exception as e:
            log.exception("Archive loop error", error=str(e))
            time.sleep(2)

    log.info("Archive service stopped")


if __name__ == "__main__":
    main()
