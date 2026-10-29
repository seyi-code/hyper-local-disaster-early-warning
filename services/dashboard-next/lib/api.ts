const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:3000";

export interface TelemetryItem {
  id: string;
  sensor_id: string;
  cell_id: string;
  metric: string;
  value: string;
  timestamp: string;
  lat?: string;
  lon?: string;
}

export interface AlertItem {
  id: string;
  cell_id: string;
  sensor_id: string;
  metric: string;
  value: string;
  direction: string;
  score: string;
  severity: string;
  message: string;
  timestamp: string;
}

export interface Health {
  status: string;
  uptime_s: number;
  mqtt_connected: boolean;
  redis_connected: boolean;
  messages_processed: number;
  last_message_at: string | null;
}

async function apiFetch(path: string) {
  const headers: Record<string, string> = {};
  const res = await fetch(`${API_BASE}${path}`, { headers, next: { revalidate: 2 } });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export async function fetchHealth(): Promise<Health> {
  return apiFetch("/health");
}

export async function fetchRecentTelemetry(count = 80): Promise<TelemetryItem[]> {
  const data = await apiFetch(`/telemetry/recent?count=${count}`);
  return data.items || [];
}

export async function fetchRecentAlerts(count = 20): Promise<AlertItem[]> {
  try {
    const data = await apiFetch(`/alerts/recent?count=${count}`);
    return data.items || [];
  } catch {
    return [];
  }
}
