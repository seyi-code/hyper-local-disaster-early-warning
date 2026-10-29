#!/usr/bin/env python3
"""Realistic multi-sensor simulator for the Disaster Early Warning Core."""
from __future__ import annotations
import json, os, random, time, math
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
load_dotenv()
MQTT_BROKER = os.getenv("MQTT_BROKER_URL", "mqtt://localhost:1883").replace("mqtt://", "")
if ":" in MQTT_BROKER:
    host, port_str = MQTT_BROKER.split(":")
    port = int(port_str)
else:
    host, port = MQTT_BROKER, 1883
INTERVAL = float(os.getenv("SIMULATOR_INTERVAL_MS", "2000")) / 1000.0
SENSORS = [
    {"sensor_id": "wl-kampala-01", "cell_id": "cell-kampala-01", "metric": "water_level_cm", "base": 42.0, "noise": 1.5},
    {"sensor_id": "wl-kampala-02", "cell_id": "cell-kampala-02", "metric": "water_level_cm", "base": 38.0, "noise": 1.2},
    {"sensor_id": "wl-entebbe-01", "cell_id": "cell-entebbe-01", "metric": "water_level_cm", "base": 55.0, "noise": 2.0},
    {"sensor_id": "aq-kampala-01", "cell_id": "cell-kampala-01", "metric": "pm25_ugm3", "base": 28.0, "noise": 4.0},
    {"sensor_id": "aq-kampala-02", "cell_id": "cell-kampala-02", "metric": "pm25_ugm3", "base": 22.0, "noise": 3.5},
]
FLOOD_START, FLOOD_SENSOR, FLOOD_RISE_RATE, FLOOD_PEAK = 45, "wl-kampala-01", 3.5, 95.0
def now_iso():
    return datetime.now(timezone.utc).isoformat()
def main():
    print(f"[simulator] Connecting to MQTT {host}:{port}")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor-simulator")
    client.connect(host, port, keepalive=60)
    client.loop_start()
    start, flood_value, step = time.time(), None, 0
    try:
        while True:
            elapsed = time.time() - start
            for s in SENSORS:
                if s["sensor_id"] == FLOOD_SENSOR and elapsed >= FLOOD_START:
                    if flood_value is None: flood_value = s["base"]
                    flood_value = min(flood_value + FLOOD_RISE_RATE + random.uniform(-0.3, 0.8), FLOOD_PEAK)
                    value = flood_value
                else:
                    value = s["base"] + random.gauss(0, s["noise"]) + 2.0 * math.sin(elapsed / 120.0 + hash(s["sensor_id"]) % 10)
                payload = {"sensor_id": s["sensor_id"], "cell_id": s["cell_id"], "metric": s["metric"], "value": round(value, 2), "timestamp": now_iso(), "lat": -0.3476, "lon": 32.5825, "battery_pct": 90.0}
                client.publish(f"sensors/{s['sensor_id']}/telemetry", json.dumps(payload), qos=1)
            step += 1
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n[simulator] Stopped")
    finally:
        client.loop_stop(); client.disconnect()
if __name__ == "__main__":
    main()
