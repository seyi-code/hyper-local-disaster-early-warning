"""
LoRaWAN → MQTT bridge (reference adapter)

Receives uplink payloads from a LoRaWAN Network Server via MQTT,
decodes binary / CayenneLPP / custom payloads, and publishes normalised
Telemetry JSON to sensors/<sensor_id>/telemetry.
"""

from __future__ import annotations

import json
import os
import struct
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

OUT_MQTT_HOST = os.getenv("OUT_MQTT_HOST", "localhost")
OUT_MQTT_PORT = int(os.getenv("OUT_MQTT_PORT", "1883"))
IN_MQTT_HOST = os.getenv("IN_MQTT_HOST", "localhost")
IN_MQTT_PORT = int(os.getenv("IN_MQTT_PORT", "1883"))
IN_TOPIC = os.getenv("IN_TOPIC", "application/+/device/+/event/up")

DEVICE_MAP: Dict[str, dict] = {
    "0004a30b001c0536": {
        "sensor_id": "wl-kampala-01",
        "cell_id": "cell-kampala-01",
        "metric": "water_level_cm",
        "scale": 0.1,
        "offset": 0.0,
    },
    "0004a30b001c0537": {
        "sensor_id": "aq-kampala-01",
        "cell_id": "cell-kampala-01",
        "metric": "pm25_ugm3",
        "scale": 1.0,
        "offset": 0.0,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def decode_cayenne_lpp(payload_hex: str) -> Dict[str, float]:
    data = bytes.fromhex(payload_hex)
    result = {}
    i = 0
    while i < len(data):
        channel = data[i]
        typ = data[i + 1]
        i += 2
        if typ == 0x67:  # temperature
            raw = struct.unpack(">h", data[i : i + 2])[0]
            result["temperature_c"] = raw / 10.0
            i += 2
        elif typ == 0x68:  # humidity
            result["humidity_pct"] = data[i] / 2.0
            i += 1
        elif typ == 0x02:  # analogue input
            raw = struct.unpack(">h", data[i : i + 2])[0]
            result["analogue"] = raw / 100.0
            i += 2
        else:
            break
    return result


def decode_custom_water_level(payload_hex: str) -> float:
    data = bytes.fromhex(payload_hex)
    if len(data) < 2:
        raise ValueError("payload too short")
    return struct.unpack(">H", data[0:2])[0] / 10.0


def normalise_uplink(msg: dict) -> Optional[dict]:
    deveui = (
        msg.get("devEUI")
        or msg.get("deviceInfo", {}).get("devEui")
        or msg.get("end_device_ids", {}).get("dev_eui")
        or ""
    ).lower()

    mapping = DEVICE_MAP.get(deveui)
    if not mapping:
        print(f"[lorawan] unknown device {deveui}")
        return None

    object_data = msg.get("object") or {}
    raw_payload = None

    if "data" in msg:
        import base64
        raw_payload = base64.b64decode(msg["data"]).hex()
    elif "frm_payload" in msg.get("uplink_message", {}):
        import base64
        raw_payload = base64.b64decode(msg["uplink_message"]["frm_payload"]).hex()

    value = None
    if mapping["metric"] in object_data:
        value = float(object_data[mapping["metric"]])
    elif raw_payload:
        try:
            if mapping["metric"] == "water_level_cm":
                value = decode_custom_water_level(raw_payload)
            else:
                decoded = decode_cayenne_lpp(raw_payload)
                value = decoded.get(mapping["metric"])
        except Exception as e:
            print(f"[lorawan] decode error: {e}")
            return None

    if value is None:
        return None

    value = value * mapping.get("scale", 1.0) + mapping.get("offset", 0.0)

    lat = lon = None
    rx = (msg.get("rxInfo") or [{}])[0]
    if "location" in rx:
        lat = rx["location"].get("latitude")
        lon = rx["location"].get("longitude")

    return {
        "sensor_id": mapping["sensor_id"],
        "cell_id": mapping["cell_id"],
        "metric": mapping["metric"],
        "value": round(value, 2),
        "timestamp": now_iso(),
        "lat": lat,
        "lon": lon,
        "metadata": {"deveui": deveui, "source": "lorawan"},
    }


def main():
    print("[lorawan-adapter] starting")

    out_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lorawan-out")
    out_client.connect(OUT_MQTT_HOST, OUT_MQTT_PORT)
    out_client.loop_start()

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            telemetry = normalise_uplink(payload)
            if telemetry:
                topic = f"sensors/{telemetry['sensor_id']}/telemetry"
                out_client.publish(topic, json.dumps(telemetry), qos=1)
                print(f"[lorawan] → {topic}  value={telemetry['value']}")
        except Exception as e:
            print(f"[lorawan] error handling uplink: {e}")

    in_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lorawan-in")
    in_client.on_message = on_message
    in_client.connect(IN_MQTT_HOST, IN_MQTT_PORT)
    in_client.subscribe(IN_TOPIC)
    in_client.loop_forever()


if __name__ == "__main__":
    main()
