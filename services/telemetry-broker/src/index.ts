/**
 * Telemetry Broker — MQTT → Redis Stream with Zod validation.
 * Also exposes HTTP health, recent telemetry, alerts, and ACK endpoints.
 */
import Fastify from "fastify";
import cors from "@fastify/cors";
import mqtt, { MqttClient } from "mqtt";
import Redis from "ioredis";
import { TelemetrySchema, Telemetry } from "./schemas/telemetry.js";

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379/0";
const REDIS_STREAM = process.env.REDIS_STREAM || "telemetry:raw";
const ALERTS_STREAM = process.env.ALERTS_STREAM || "alerts:triggered";
const MQTT_BROKER_URL = process.env.MQTT_BROKER_URL || "mqtt://localhost:1883";
const MQTT_TOPIC = process.env.MQTT_TOPIC || "sensors/+/telemetry";
const MQTT_CLIENT_ID = process.env.MQTT_CLIENT_ID || "telemetry-broker";
const MQTT_USERNAME = process.env.MQTT_USERNAME || "";
const MQTT_PASSWORD = process.env.MQTT_PASSWORD || "";
const PORT = parseInt(process.env.BROKER_PORT || "3000", 10);
const API_KEY = process.env.API_KEY || "";

const startedAt = Date.now();
let messagesProcessed = 0;
let lastMessageAt: string | null = null;
let mqttConnected = false;

const redis = new Redis(REDIS_URL, { maxRetriesPerRequest: null });
let mqttClient: MqttClient;

const app = Fastify({ logger: true });
await app.register(cors, { origin: true });

app.addHook("onRequest", async (req, reply) => {
  if (!API_KEY) return;
  if (req.url.startsWith("/health") || req.url.startsWith("/metrics")) return;
  const key = req.headers["x-api-key"];
  if (key !== API_KEY) {
    return reply.code(401).send({ error: "unauthorized" });
  }
});

app.get("/health", async () => ({
  status: mqttConnected && redis.status === "ready" ? "ok" : "degraded",
  uptime_s: Math.round((Date.now() - startedAt) / 1000),
  mqtt_connected: mqttConnected,
  redis_connected: redis.status === "ready",
  messages_processed: messagesProcessed,
  last_message_at: lastMessageAt,
}));

app.get("/metrics", async (_req, reply) => {
  const lines = [
    `# HELP ew_messages_processed Total telemetry messages written to Redis`,
    `# TYPE ew_messages_processed counter`,
    `ew_messages_processed ${messagesProcessed}`,
    `# HELP ew_mqtt_connected MQTT connection status`,
    `# TYPE ew_mqtt_connected gauge`,
    `ew_mqtt_connected ${mqttConnected ? 1 : 0}`,
    `# HELP ew_uptime_seconds Process uptime`,
    `# TYPE ew_uptime_seconds gauge`,
    `ew_uptime_seconds ${Math.round((Date.now() - startedAt) / 1000)}`,
  ];
  reply.type("text/plain").send(lines.join("\n") + "\n");
});

app.get<{ Querystring: { count?: string } }>("/telemetry/recent", async (req) => {
  const count = Math.min(parseInt(req.query.count || "50", 10), 200);
  const entries = await redis.xrevrange(REDIS_STREAM, "+", "-", "COUNT", count);
  const items = entries.map(([id, fields]) => {
    const obj: Record<string, string> = { id };
    for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
    return obj;
  });
  return { items };
});

app.get<{ Querystring: { count?: string } }>("/alerts/recent", async (req) => {
  const count = Math.min(parseInt(req.query.count || "20", 10), 100);
  try {
    const entries = await redis.xrevrange(ALERTS_STREAM, "+", "-", "COUNT", count);
    const items = entries.map(([id, fields]) => {
      const obj: Record<string, string> = { id };
      for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
      return obj;
    });
    return { items };
  } catch {
    return { items: [] };
  }
});

app.post<{ Body: { cell_id: string; sensor_id?: string } }>("/alerts/ack", async (req) => {
  const { cell_id, sensor_id } = req.body || ({} as any);
  if (!cell_id) return { ok: false, error: "cell_id required" };
  await redis.xadd(
    "alerts:acked",
    "*",
    "cell_id",
    cell_id,
    "sensor_id",
    sensor_id || "",
    "acked_at",
    new Date().toISOString()
  );
  return { ok: true };
});

function connectMqtt() {
  const opts: mqtt.IClientOptions = {
    clientId: MQTT_CLIENT_ID,
    reconnectPeriod: 3000,
  };
  if (MQTT_USERNAME) {
    opts.username = MQTT_USERNAME;
    opts.password = MQTT_PASSWORD;
  }
  mqttClient = mqtt.connect(MQTT_BROKER_URL, opts);

  mqttClient.on("connect", () => {
    mqttConnected = true;
    app.log.info({ topic: MQTT_TOPIC }, "MQTT connected");
    mqttClient.subscribe(MQTT_TOPIC, { qos: 1 });
  });

  mqttClient.on("close", () => {
    mqttConnected = false;
  });

  mqttClient.on("error", (err) => {
    app.log.error({ err }, "MQTT error");
  });

  mqttClient.on("message", async (_topic, payload) => {
    try {
      const raw = JSON.parse(payload.toString());
      const parsed: Telemetry = TelemetrySchema.parse(raw);
      const fields: string[] = [
        "sensor_id", parsed.sensor_id,
        "cell_id", parsed.cell_id,
        "metric", parsed.metric,
        "value", String(parsed.value),
        "timestamp", String(parsed.timestamp),
      ];
      if (parsed.lat != null) fields.push("lat", String(parsed.lat));
      if (parsed.lon != null) fields.push("lon", String(parsed.lon));
      if (parsed.battery_pct != null) fields.push("battery_pct", String(parsed.battery_pct));

      await redis.xadd(REDIS_STREAM, "*", ...fields);
      messagesProcessed += 1;
      lastMessageAt = new Date().toISOString();
    } catch (err) {
      app.log.warn({ err }, "Invalid telemetry dropped");
    }
  });
}

async function main() {
  connectMqtt();
  await app.listen({ port: PORT, host: "0.0.0.0" });
  app.log.info(`Telemetry broker listening on :${PORT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
