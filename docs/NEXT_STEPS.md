# Next Concrete Steps — Implemented

## 1. React / Next.js Dashboard
Location: `services/dashboard-next/`

```bash
cd services/dashboard-next
npm install
NEXT_PUBLIC_API_BASE=http://localhost:3000 npm run dev
```

## 2. GIS Cell Mapping
Location: `services/anomaly-engine/src/gis/cells.py`

Named cells from `config/cells.json` plus optional H3 hexagons.

## 3. LoRaWAN Integration
Location: `services/lorawan-adapter/`

Bridge ChirpStack / TTN uplinks to the same MQTT telemetry topics.

## Recommended rollout order
1. Core stack + simulator
2. Real sensors on MQTT
3. Named cells matching wards
4. Next.js dashboard
5. LoRaWAN when needed
6. Twilio + cell recipient lists
7. Human confirmation rules as required
