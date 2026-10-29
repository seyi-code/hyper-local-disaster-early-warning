# Secrets

Do not commit real secrets.

1. Local/Compose: keep secrets only in .env (gitignored).
2. Generate MQTT auth with ./scripts/generate-mqtt-auth.sh
3. Docker Swarm secrets or Kubernetes sealed secrets for production.
4. Rotate Twilio tokens and MQTT device passwords on a schedule.
