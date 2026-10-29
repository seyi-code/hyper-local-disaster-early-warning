# Hyper-Local Municipal Disaster Sensor & Early Warning Core

**Autonomous, event-driven early warning system for flash floods, mudslides, and localized air-quality / wildfire events.**

Municipalities and community groups can deploy low-cost IoT sensors (ultrasonic water-level, PM2.5, temperature/humidity) that stream continuous telemetry. The system detects statistical anomalies in real time using CUSUM (Cumulative Sum) change-point detection and immediately triggers hyper-local alerts via SMS, voice calls, webhooks, and optional mesh notifications.

This is a **production-oriented reference implementation** focused on correctness, observability, and deployability.

See full documentation in the repository: docs/, docker-compose.yml, and scripts/.

## Quick Start

```bash
cp .env.example .env
docker compose up --build -d
cd sensors && pip install -r requirements.txt && python simulator.py
```

- Dashboard: http://localhost:8080
- Broker health: http://localhost:3000/health
- Next.js dashboard: `cd services/dashboard-next && npm i && npm run dev`

## Architecture

Sensors → MQTT → Telemetry Broker → Redis Streams → Anomaly Engine (CUSUM) → Alerts → Postgres archive + Dashboard

MIT License.
