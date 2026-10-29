# Security Hardening Checklist

## Minimum production requirements

### MQTT (Mosquitto)
- Disable allow_anonymous
- Per-device usernames/passwords or mutual TLS
- Restrict topic ACLs
- Enable TLS (8883)

### Redis
- Strong requirepass
- Private network only
- TLS if crossing boundaries

### HTTP API
- Set API_KEY
- Reverse proxy with TLS
- Rate-limit list endpoints

### Secrets
- Never bake credentials into images
- Use Docker/K8s secrets or a vault

### Alerting
- Human confirmation for highest severity when required
- Cap SMS spend
- Log every dispatch

### Containers
- Run as non-root
- Resource limits
- Keep base images updated
