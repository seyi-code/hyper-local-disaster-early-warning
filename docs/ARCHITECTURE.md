# Architecture Deep Dive

## Data Flow

1. Field sensor publishes JSON to MQTT topic `sensors/<sensor_id>/telemetry`.
2. Telemetry Broker validates with Zod and writes to Redis Stream `telemetry:raw`.
3. Anomaly Engine (consumer group) runs per-cell CUSUM and fires AlertEvents.
4. Alerts go to console/webhook/Twilio (with optional ACK for critical SMS).
5. Archive service persists telemetry and alerts to Postgres.

## Why CUSUM?

Detects sustained mean shifts with constant memory — ideal for streaming water level and PM2.5.

## Hyper-local cells

Every reading has a `cell_id` (ward, catchment, or H3 index). Alerts are scoped to that cell.

## Scaling

Multiple anomaly-engine workers join the same Redis consumer group for parallel processing.
