"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";

export type MapPoint = {
  id: string;
  lat: number;
  lon: number;
  label: string;
  value?: string;
  metric?: string;
};

type Props = {
  points: MapPoint[];
  cells?: { id: string; name: string; lat: number; lon: number }[];
};

function MapInner({ points, cells = [] }: Props) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    let map: any;
    let L: any;

    (async () => {
      L = (await import("leaflet")).default;
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const el = document.getElementById("ew-map");
      if (!el || (el as any)._leaflet_id) return;

      const center: [number, number] =
        points.length > 0
          ? [points[0].lat, points[0].lon]
          : cells.length > 0
            ? [cells[0].lat, cells[0].lon]
            : [0.3, 32.5];

      map = L.map(el).setView(center, 11);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 18,
      }).addTo(map);

      cells.forEach((c) => {
        L.circle([c.lat, c.lon], {
          radius: 1200,
          color: "#38bdf8",
          fillColor: "#0ea5e9",
          fillOpacity: 0.15,
          weight: 1,
        })
          .bindPopup(`<b>${c.name}</b><br/>${c.id}`)
          .addTo(map);
      });

      points.forEach((p) => {
        L.marker([p.lat, p.lon])
          .bindPopup(`<b>${p.label}</b><br/>${p.metric || ""} ${p.value ?? ""}`)
          .addTo(map);
      });
    })();

    return () => {
      if (map) map.remove();
    };
  }, [ready, points, cells]);

  return (
    <div
      id="ew-map"
      className="h-72 w-full rounded-lg overflow-hidden border border-slate-800 bg-slate-950"
    />
  );
}

export const CellMap = dynamic(() => Promise.resolve(MapInner), {
  ssr: false,
  loading: () => (
    <div className="h-72 w-full rounded-lg bg-slate-900 border border-slate-800 animate-pulse" />
  ),
});
