// Shared traffic incidents (accidents, closures, construction) on the MapLibre maps.
// The server refreshes them every few minutes for everyone, so every page asks the same
// endpoint and gets the same copy; nothing here calls the traffic provider directly.
import { useEffect, useState } from "react";
import maplibregl from "maplibre-gl";
import { getTrafficAlerts } from "../../services/transportService";

export const TRAFFIC_TYPES = {
  accident:     { label: "Accident",     color: "#dc2626" },
  road_closed:  { label: "Road closed",  color: "#7f1d1d" },
  construction: { label: "Construction", color: "#d97706" },
  incident:     { label: "Slowdown",     color: "#ea580c" },
};

const SOURCE = "traffic-alerts";
const RECHECK_MS = 60 * 1000; // cheap: the server answers from its shared copy

/** Latest shared incidents: { alerts, fetchedAt, stale, error }. Polls only while the tab is visible. */
export function useTrafficAlerts(enabled = true) {
  const [state, setState] = useState({ alerts: [], fetchedAt: null, stale: false, error: "" });

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = () => {
      if (document.visibilityState === "hidden") return;
      getTrafficAlerts()
        .then((res) => {
          if (cancelled) return;
          setState({ alerts: res.data.alerts || [], fetchedAt: res.data.fetched_at * 1000, stale: Boolean(res.data.stale), error: "" });
        })
        .catch((err) => {
          if (!cancelled) setState((current) => ({ ...current, error: err.response?.data?.detail || "Traffic data is unavailable right now." }));
        });
    };
    load();
    const timer = setInterval(load, RECHECK_MS);
    document.addEventListener("visibilitychange", load);
    return () => { cancelled = true; clearInterval(timer); document.removeEventListener("visibilitychange", load); };
  }, [enabled]);

  return state;
}

const toGeoJSON = (alerts) => ({
  type: "FeatureCollection",
  features: alerts.map((alert) => {
    const kind = TRAFFIC_TYPES[alert.type] ? alert.type : "incident";
    return {
      type: "Feature",
      properties: { label: TRAFFIC_TYPES[kind].label, color: TRAFFIC_TYPES[kind].color },
      geometry: { type: "Point", coordinates: [alert.longitude, alert.latitude] },
    };
  }),
});

/** Draws (or updates) the incidents on a loaded map; `visible` hides them without dropping the data. */
export function showTrafficAlerts(map, alerts, visible = true) {
  const data = toGeoJSON(visible ? alerts : []);
  const existing = map.getSource(SOURCE);
  if (existing) {
    existing.setData(data);
    return;
  }
  map.addSource(SOURCE, { type: "geojson", data });
  map.addLayer({
    id: `${SOURCE}-halo`, type: "circle", source: SOURCE,
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 9, 15, 16], "circle-color": ["get", "color"], "circle-opacity": 0.18 },
  });
  map.addLayer({
    id: SOURCE, type: "circle", source: SOURCE,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4.5, 15, 7],
      "circle-color": ["get", "color"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
  map.on("click", SOURCE, (event) => {
    const props = event.features?.[0]?.properties;
    if (!props) return;
    const box = document.createElement("div");
    box.style.cssText = "font:13px/1.45 'DM Sans',system-ui,sans-serif;color:#0f1f2d";
    const title = document.createElement("strong");
    title.textContent = props.label;
    title.style.color = props.color;
    const note = document.createElement("div");
    note.textContent = "Reported on Google Maps traffic";
    note.style.cssText = "color:#4a6178;font-size:12px";
    box.append(title, note);
    new maplibregl.Popup({ closeButton: false }).setLngLat(event.lngLat).setDOMContent(box).addTo(map);
  });
  map.on("mouseenter", SOURCE, () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", SOURCE, () => { map.getCanvas().style.cursor = ""; });
}

/** "Updated 3 min ago" for the shared copy. */
export function trafficAge(fetchedAt) {
  if (!fetchedAt) return "";
  const minutes = Math.max(0, Math.round((Date.now() - fetchedAt) / 60000));
  return minutes < 1 ? "updated just now" : `updated ${minutes} min ago`;
}
