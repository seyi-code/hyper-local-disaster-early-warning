# Operational Runbooks

## 1. False-positive alert storm
1. Check anomaly-engine logs for CUSUM scores.
2. Raise CUSUM_H and ALERT_DISPATCH_COOLDOWN temporarily.
3. Verify sensor hardware.
4. Acknowledge alerts via POST /alerts/ack.

## 2. Whole cell goes silent
1. Check network path and Mosquitto logs.
2. Verify device credentials.
3. Query sensor_heartbeat in Postgres for last_seen_at.

## 3. Redis memory pressure
1. redis-cli INFO memory
2. XTRIM telemetry:raw MAXLEN ~ 100000
3. Ensure archive-service is ACKing.

## 4. Twilio / SMS failure
1. Check account balance and geo-permissions.
2. Fall back to webhook/console.
3. Do not disable rate limits.

## 5. Postgres / archive lag
1. Check archive-service logs and pg_isready.
2. XPENDING on consumer groups.
3. Restart archive-service.

## 6. Deploying MQTT authentication
1. ./scripts/generate-mqtt-auth.sh
2. Set MQTT_USERNAME/PASSWORD in .env
3. Switch to mosquitto.conf.prod
4. Restart mosquitto + telemetry-broker

## 7. Backup and restore
./scripts/backup/backup.sh
# Restore: pg_restore into postgres container
