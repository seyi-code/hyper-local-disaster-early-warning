# Deployment Guide

## Local

```bash
cp .env.example .env
docker compose up --build -d
cd sensors && pip install -r requirements.txt && python simulator.py
```

## Production VPS

1. Install Docker
2. Clone repo, copy .env.example to .env, set strong passwords
3. ./scripts/generate-mqtt-auth.sh and enable prod mosquitto config
4. docker compose up --build -d
5. TLS reverse proxy (Caddy/Nginx) for ports 3000/8080
6. Do not expose Redis/Postgres publicly

## Alert modes

console | webhook | twilio | multi

Critical SMS can require human ACK (REQUIRE_ACK_FOR_CRITICAL=true).
