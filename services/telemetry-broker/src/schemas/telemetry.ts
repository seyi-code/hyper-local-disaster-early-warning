import { z } from "zod";

export const TelemetrySchema = z.object({
  sensor_id: z
    .string()
    .min(3)
    .max(64)
    .regex(/^[a-zA-Z0-9_-]+$/, "sensor_id must be alphanumeric with _ or -"),
  cell_id: z.string().min(2).max(64),
  metric: z.enum(["water_level_cm", "pm25_ugm3", "temperature_c", "humidity_pct"]),
  value: z.number().finite(),
  unit: z.string().max(16).optional(),
  timestamp: z
    .string()
    .datetime({ offset: true })
    .or(z.number().int().positive())
    .transform((v) => (typeof v === "number" ? new Date(v).toISOString() : v)),
  lat: z.number().min(-90).max(90).optional(),
  lon: z.number().min(-180).max(180).optional(),
  battery_pct: z.number().min(0).max(100).optional(),
  metadata: z.record(z.unknown()).optional(),
});

export type Telemetry = z.infer<typeof TelemetrySchema>;
