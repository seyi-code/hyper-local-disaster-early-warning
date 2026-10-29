"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { formatDistanceToNow } from "date-fns";
import { CellMap, type MapPoint } from "@/components/map/CellMap";
import {
  fetchHealth,
  fetchRecentTelemetry,
  fetchRecentAlerts,
  type Health,
  type TelemetryItem,
  type AlertItem,
} from "@/lib/api";

export default function DashboardPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [items, setItems] = useState<TelemetryItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [h, t, a] = await Promise.all([
          fetchHealth(),
          fetchRecentTelemetry(80),
          fetchRecentAlerts(15),
        ]);
        if (!cancelled) {
          setHealth(h);
          setItems(t);
          setAlerts(a);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message || "Failed to load");
      }
    }
    load();
    const id = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const waterSeries = items
    .filter((i) => i.metric === "water_level_cm")
    .slice()
    .reverse()
    .map((i) => ({
      t: (i.timestamp || "").slice(11, 19),
      v: parseFloat(i.value),
      sensor: i.sensor_id,
    }));

  const airSeries = items
    .filter((i) => i.metric === "pm25_ugm3")
    .slice()
    .reverse()
    .map((i) => ({
      t: (i.timestamp || "").slice(11, 19),
      v: parseFloat(i.value),
      sensor: i.sensor_id,
    }));

  const cells = new Set(items.map((i) => i.cell_id)).size;

  return (
    <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Hyper-Local Disaster Early Warning
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Live municipal sensors · CUSUM anomaly detection · cell-scoped alerts
          </p>
        </div>
        <div className="text-right text-sm">
          {health ? (
            <>
              <div
                className={
                  health.status === "ok" ? "text-emerald-400" : "text-amber-400"
                }
              >
                {health.status === "ok" ? "System online" : "Degraded"}
              </div>
              <div className="text-slate-500">
                MQTT {health.mqtt_connected ? "up" : "down"} · Redis{" "}
                {health.redis_connected ? "up" : "down"}
              </div>
            </>
          ) : (
            <span className="text-slate-500">Connecting…</span>
          )}
        </div>
      </header>

      {error && (
        <div className="bg-red-950/50 border border-red-800 text-red-200 rounded-lg px-4 py-3 text-sm">
          {error} — is the telemetry broker running on :3000?
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Messages", value: health?.messages_processed ?? "—" },
          { label: "Uptime", value: health ? `${Math.round(health.uptime_s)}s` : "—" },
          { label: "Active cells", value: cells || "—" },
          {
            label: "Last msg",
            value: health?.last_message_at
              ? formatDistanceToNow(new Date(health.last_message_at), { addSuffix: true })
              : "—",
          },
        ].map((k) => (
          <div
            key={k.label}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4"
          >
            <div className="text-xs uppercase tracking-wide text-slate-500">{k.label}</div>
            <div className="text-xl font-semibold mt-1">{k.value}</div>
          </div>
        ))}
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <h2 className="font-medium mb-3">Cell map</h2>
        <CellMap
          points={items
            .filter((i) => i.lat && i.lon)
            .slice(0, 30)
            .map((i) => ({
              id: i.id,
              lat: parseFloat(i.lat!),
              lon: parseFloat(i.lon!),
              label: i.sensor_id,
              value: i.value,
              metric: i.metric,
            }))}
          cells={[
            { id: "cell-kampala-01", name: "Kampala Central", lat: -0.3136, lon: 32.5811 },
            { id: "cell-kampala-02", name: "Makerere / Wandegeya", lat: -0.335, lon: 32.568 },
            { id: "cell-entebbe-01", name: "Entebbe Lakeshore", lat: 0.0422, lon: 32.4435 },
          ]}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h2 className="font-medium mb-3">Water level (cm)</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={waterSeries}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
                />
                <Line type="monotone" dataKey="v" stroke="#38bdf8" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h2 className="font-medium mb-3">PM2.5 (µg/m³)</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={airSeries}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }}
                />
                <Line type="monotone" dataKey="v" stroke="#a78bfa" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <h2 className="font-medium mb-3">Recent alerts</h2>
        {alerts.length === 0 ? (
          <p className="text-slate-500 text-sm">No alerts yet — run the simulator to generate one.</p>
        ) : (
          <ul className="space-y-2">
            {alerts.map((a) => (
              <li
                key={a.id}
                className="flex flex-wrap gap-2 items-start text-sm border-b border-slate-800 pb-2"
              >
                <span
                  className={
                    a.severity === "critical"
                      ? "text-red-400 font-semibold"
                      : "text-amber-400"
                  }
                >
                  {(a.severity || "warning").toUpperCase()}
                </span>
                <span className="text-slate-400">{a.cell_id}</span>
                <span className="flex-1">{a.message}</span>
                <span className="text-slate-500 text-xs">
                  {(a.timestamp || "").slice(11, 19)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
