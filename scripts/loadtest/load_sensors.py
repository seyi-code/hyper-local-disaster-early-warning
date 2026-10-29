#!/usr/bin/env python3
"""Simple load / soak test: N synthetic sensors publishing at fixed rate."""
from __future__ import annotations
import argparse, json, random, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import paho.mqtt.client as mqtt

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def worker(sensor_idx, host, port, hz, duration, user, password):
    sid = f"load-sensor-{sensor_idx:04d}"
    cell = f"cell-load-{(sensor_idx % 10) + 1:02d}"
    metric = "water_level_cm" if sensor_idx % 2 == 0 else "pm25_ugm3"
    base = 40.0 if "water" in metric else 25.0
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"load-{sid}")
    if user:
        client.username_pw_set(user, password)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    topic = f"sensors/{sid}/telemetry"
    interval = 1.0 / hz
    end = time.time() + duration
    ok, fail = 0, 0
    while time.time() < end:
        payload = {"sensor_id": sid, "cell_id": cell, "metric": metric, "value": round(base + random.gauss(0, 2), 2), "timestamp": now_iso(), "battery_pct": 90.0}
        info = client.publish(topic, json.dumps(payload), qos=1)
        try:
            info.wait_for_publish(timeout=2)
            ok += 1 if info.rc == mqtt.MQTT_ERR_SUCCESS else 0
            fail += 0 if info.rc == mqtt.MQTT_ERR_SUCCESS else 1
        except Exception:
            fail += 1
        time.sleep(interval)
    client.loop_stop()
    client.disconnect()
    return sid, ok, fail

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--sensors", type=int, default=20)
    ap.add_argument("--hz", type=float, default=0.5)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--user", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    print(f"Load test: {args.sensors} sensors @ {args.hz} Hz for {args.duration}s")
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, i, args.host, args.port, args.hz, args.duration, args.user, args.password) for i in range(args.sensors)]
        for f in as_completed(futs):
            results.append(f.result())
    ok = sum(r[1] for r in results)
    fail = sum(r[2] for r in results)
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s — ok={ok} fail={fail} rate={ok/max(elapsed,1):.1f} msg/s")

if __name__ == "__main__":
    main()
