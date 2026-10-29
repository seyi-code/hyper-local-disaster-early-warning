#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi
echo "Starting infrastructure + services…"
docker compose up --build -d
echo ""
echo "Dashboard:        http://localhost:8080"
echo "Broker health:    http://localhost:3000/health"
echo "MQTT:             localhost:1883"
echo ""
echo "Next: cd sensors && python simulator.py"
echo "Watch: docker compose logs -f anomaly-engine"
