/**
 * Telemetry Broker — MQTT → Redis Stream with Zod validation.
 * HTTP: health, metrics, telemetry, alerts, ACK, cells.
 */
import Fastify from "fastify";
import cors from "@fastify/cors";
import mqtt, { MqttClient } from "mqtt";
import Redis from "ioredis";
import { TelemetrySchema, type Telemetry } from "./schemas/telemetry.js";
import { pino } from "pino";
import fs from "node:fs";
import path from "node:path";

const log = pino({
  level: process.env.LOG_LEVEL || "info",
  transport:
    process.env.NODE_ENV !== "production"
      ? { target: "pino-pretty", options: { colorize: true } }
      : undefined,
});

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379/0";
const REDIS_STREAM = process.env.REDIS_STREAM || "telemetry:raw";
const ALERTS_STREAM = process.env.ALERTS_STREAM || "alerts:triggered";
const MQTT_BROKER_URL = process.env.MQTT_BROKER_URL || "mqtt://localhost:1883";
const MQTT_TOPIC = process.env.MQTT_TOPIC || "sensors/+/telemetry";
const MQTT_CLIENT_ID = process.env.MQTT_CLIENT_ID || "telemetry-broker";
const BROKER_PORT = Number(process.env.BROKER_PORT || 3000);

let mqttClient: MqttClient | null = null;
let redis: Redis | null = null;
let messagesProcessed = 0;
let lastMessageAt: string | null = null;
const startedAt = Date.now();

async function connectRedis(): Promise<Redis> {
  const client = new Redis(REDIS_URL, { maxRetriesPerRequest: 3, lazyConnect: true });
  await client.connect();
  log.info({ url: REDIS_URL }, "Redis connected");
  return client;
}

function connectMqtt(): MqttClient {
  const client = mqtt.connect(MQTT_BROKER_URL, {
    clientId: MQTT_CLIENT_ID,
    username: process.env.MQTT_USERNAME || undefined,
    password: process.env.MQTT_PASSWORD || undefined,
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 10_000,
  });
  client.on("connect", () => {
    log.info({ broker: MQTT_BROKER_URL, topic: MQTT_TOPIC }, "MQTT connected");
    client.subscribe(MQTT_TOPIC, { qos: 1 });
  });
  client.on("error", (err) => log.error({ err }, "MQTT error"));
  client.on("message", async (topic, payload) => {
    await handleTelemetry(topic, payload);
  });
  return client;
}

async function handleTelemetry(topic: string, payload: Buffer): Promise<void> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload.toString("utf8"));
  } catch {
    log.warn({ topic }, "Invalid JSON — dropped");
    return;
  }
  const result = TelemetrySchema.safeParse(parsed);
  if (!result.success) {
    log.warn({ topic, errors: result.error.flatten() }, "Schema validation failed");
    return;
  }
  const data: Telemetry = result.data;
  if (!redis) return;
  try {
    await redis.xadd(
      REDIS_STREAM, "*",
      "sensor_id", data.sensor_id,
      "cell_id", data.cell_id,
      "metric", data.metric,
      "value", String(data.value),
      "timestamp", data.timestamp,
      "lat", data.lat != null ? String(data.lat) : "",
      "lon", data.lon != null ? String(data.lon) : "",
      "battery_pct", data.battery_pct != null ? String(data.battery_pct) : "",
      "raw", JSON.stringify(data)
    );
    messagesProcessed += 1;
    lastMessageAt = new Date().toISOString();
  } catch (err) {
    log.error({ err }, "Failed to write Redis Stream");
  }
}

async function main() {
  redis = await connectRedis();
  mqttClient = connectMqtt();
  const app = Fastify({ logger: false });
  await app.register(cors, { origin: true });
  const API_KEY = process.env.API_KEY || "";

  app.addHook("onRequest", async (req, reply) => {
    if (!API_KEY) return;
    if (req.url.startsWith("/health") || req.url.startsWith("/metrics")) return;
    const key = (req.headers["x-api-key"] as string) || (req.query as any).api_key;
    if (key !== API_KEY) return reply.code(401).send({ error: "Unauthorized" });
  });

  app.get("/health", async () => ({
    status: "ok",
    uptime_s: Math.floor((Date.now() - startedAt) / 1000),
    mqtt_connected: mqttClient?.connected ?? false,
    redis_connected: redis?.status === "ready",
    messages_processed: messagesProcessed,
    last_message_at: lastMessageAt,
  }));

  app.get("/metrics", async (_req, reply) => {
    const body = [
      `telemetry_messages_processed_total ${messagesProcessed}`,
      `telemetry_mqtt_connected ${mqttClient?.connected ? 1 : 0}`,
      `telemetry_redis_connected ${redis?.status === "ready" ? 1 : 0}`,
      `telemetry_uptime_seconds ${Math.floor((Date.now() - startedAt) / 1000)}`,
    ].join("\n");
    return reply.type("text/plain").send(body + "\n");
  });

  app.get("/telemetry/recent", async (req, reply) => {
    if (!redis) return reply.code(503).send({ error: "Redis unavailable" });
    const count = Number((req.query as any).count || 50);
    const entries = await redis.xrevrange(REDIS_STREAM, "+", "-", "COUNT", count);
    const items = entries.map(([id, fields]) => {
      const obj: Record<string, string> = { id };
      for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
      return obj;
    });
    return { count: items.length, items };
  });

  app.get("/alerts/recent", async (req, reply) => {
    if (!redis) return reply.code(503).send({ error: "Redis unavailable" });
    const count = Number((req.query as any).count || 30);
    try {
      const entries = await redis.xrevrange(ALERTS_STREAM, "+", "-", "COUNT", count);
      const items = entries.map(([id, fields]) => {
        const obj: Record<string, string> = { id };
        for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
        return obj;
      });
      return { count: items.length, items };
    } catch {
      return { count: 0, items: [] };
    }
  });

  app.post("/alerts/ack", async (req, reply) => {
    if (!redis) return reply.code(503).send({ error: "Redis unavailable" });
    const body = (req.body || {}) as Record<string, string>;
    if (!body.cell_id) return reply.code(400).send({ error: "cell_id required" });
    const ack = {
      cell_id: body.cell_id,
      sensor_id: body.sensor_id || "",
      acknowledged_by: body.by || "operator",
      acknowledged_at: new Date().toISOString(),
      note: body.note || "",
    };
    await redis.xadd(
      "alerts:acked", "*",
      "cell_id", ack.cell_id,
      "sensor_id", ack.sensor_id,
      "acknowledged_by", ack.acknowledged_by,
      "acknowledged_at", ack.acknowledged_at,
      "note", ack.note
    );
    log.info(ack, "Alert acknowledged");
    return { ok: true, ...ack };
  });

  app.get("/cells", async () => {
    const candidates = [
      process.env.CELLS_CONFIG_PATH,
      path.join(process.cwd(), "config", "cells.json"),
      "/app/config/cells.json",
    ].filter(Boolean) as string[];
    for (const p of candidates) {
      try {
        if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, "utf8"));
      } catch { /* next */ }
    }
    return {
      cells: [
        { cell_id: "cell-kampala-01", name: "Kampala Central", center: [-0.3136, 32.5811], priority: "high" },
        { cell_id: "cell-kampala-02", name: "Makerere / Wandegeya", center: [-0.335, 32.568], priority: "high" },
        { cell_id: "cell-entebbe-01", name: "Entebbe Lakeshore", center: [0.0422, 32.4435], priority: "medium" },
      ],
    };
  });

  app.get("/alerts/acked", async (req, reply) => {
    if (!redis) return reply.code(503).send({ error: "Redis unavailable" });
    const count = Number((req.query as any).count || 20);
    try {
      const entries = await redis.xrevrange("alerts:acked", "+", "-", "COUNT", count);
      const items = entries.map(([id, fields]) => {
        const obj: Record<string, string> = { id };
        for (let i = 0; i < fields.length; i += 2) obj[fields[i]] = fields[i + 1];
        return obj;
      });
      return { count: items.length, items };
    } catch {
      return { count: 0, items: [] };
    }
  });

  await app.listen({ port: BROKER_PORT, host: "0.0.0.0" });
  log.info({ port: BROKER_PORT }, "Telemetry broker HTTP server listening");
}

main().catch((err) => {
  log.fatal({ err }, "Fatal startup error");
  process.exit(1);
});

process.on("SIGTERM", () => {
  mqttClient?.end(true);
  redis?.disconnect();
  process.exit(0);
});
