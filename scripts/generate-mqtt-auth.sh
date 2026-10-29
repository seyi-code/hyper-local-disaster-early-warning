#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/config/mqtt"
mkdir -p "$OUT"
BROKER_PASS="${MQTT_BROKER_PASSWORD:-ChangeMeBrokerStrong!}"
SENSOR_PASS="${MQTT_SENSOR_PASSWORD:-ChangeMeSensorStrong!}"
echo "Generating Mosquitto password file…"
docker run --rm -v "$OUT":/work eclipse-mosquitto:2 \
  sh -c "mosquitto_passwd -c -b /work/passwd telemetry-broker '$BROKER_PASS' && mosquitto_passwd -b /work/passwd sensor-kampala-01 '$SENSOR_PASS' && mosquitto_passwd -b /work/passwd sensor-kampala-02 '$SENSOR_PASS' && mosquitto_passwd -b /work/passwd lorawan-adapter '$BROKER_PASS' && chmod 0700 /work/passwd"
cat > "$OUT/acl" << 'ACL'
user telemetry-broker
topic read sensors/#
user lorawan-adapter
topic write sensors/#
user sensor-kampala-01
topic write sensors/wl-kampala-01/#
topic write sensors/aq-kampala-01/#
user sensor-kampala-02
topic write sensors/wl-kampala-02/#
ACL
echo "Wrote $OUT/passwd and $OUT/acl"
echo "Set MQTT_USERNAME=telemetry-broker and MQTT_PASSWORD in .env"
