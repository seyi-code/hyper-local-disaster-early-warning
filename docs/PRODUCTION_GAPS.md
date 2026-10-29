# Gaps to Production Readiness (updated)

## Closed in code (this project)

| Area | Implementation |
|------|----------------|
| Durable archive | Postgres archive-service + heartbeats + optional Timescale hypertables |
| Offline sensors | Heartbeat monitor → synthetic alerts |
| Human ACK | POST /alerts/ack + escalation policy for critical SMS |
| Escalation policy | Critical SMS held until ACK or timeout |
| MQTT auth path | scripts/generate-mqtt-auth.sh + mosquitto.conf.prod + ACL |
| Redis hardening | AOF, memory limit, private network |
| API protection | Optional API_KEY on broker |
| Metrics | Prometheus /metrics |
| Resource limits | Compose deploy limits |
| CI | GitHub Actions |
| Backups | scripts/backup/backup.sh |
| Load test | scripts/loadtest/load_sensors.py |
| Runbooks | docs/runbooks/README.md |
| Dashboard map | Leaflet cell + sensor map |
| Cell recipients | config/cells.json |

## Still requires deployment / organisational work

1. Generate and enforce real MQTT credentials + TLS on every field device.
2. Set strong Postgres/Redis passwords; do not expose ports publicly.
3. Put a TLS reverse proxy in front of broker/dashboard.
4. Legal/regulatory acceptance and ops staffing for the pilot.
5. Monthly restore drills from backups.
6. Load test at expected city scale.
7. Stakeholder-signed runbooks and escalation phone tree.
8. Secrets vault integration.

## Pilot bar

Safe for a supervised pilot once items 1–3 are done in your environment. City-wide unattended SMS needs legal sign-off and sustained ops.
