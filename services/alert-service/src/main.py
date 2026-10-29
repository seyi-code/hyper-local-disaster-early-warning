"""
Optional dedicated Alert Service.

In the reference architecture the anomaly-engine can dispatch alerts
directly (console / webhook / Twilio). This service exists so that
you can later:

  - centralize multi-channel fan-out
  - add rate-limiting / deduplication across workers
  - integrate with municipal radio / LoRa / siren gateways

It currently consumes from the Redis stream `alerts:triggered`
(if the anomaly engine is configured to publish there) and re-dispatches.
"""

from __future__ import annotations

import os
import time
import signal
import structlog
import redis
from redis.exceptions import ResponseError

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STREAM = "alerts:triggered"
GROUP = "alert-dispatchers"
CONSUMER = os.getenv("REDIS_CONSUMER_NAME", "alert-1")
running = True


def shutdown(signum, frame):
    global running
    running = False


def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    log.info("Alert service ready", stream=STREAM)

    while running:
        try:
            results = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10, block=5000)
            if not results:
                continue
            for _, messages in results:
                for entry_id, fields in messages:
                    log.warning("Received alert event", **fields)
                    r.xack(STREAM, GROUP, entry_id)
        except Exception as e:
            log.error("Error", error=str(e))
            time.sleep(2)

    log.info("Alert service stopped")


if __name__ == "__main__":
    main()
