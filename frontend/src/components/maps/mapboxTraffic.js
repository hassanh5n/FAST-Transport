// Optional Mapbox traffic lines on the MapLibre maps, off by default.
//
// Mapbox has almost no live traffic for Karachi: probes at 5:29 am, 5 pm and 8 pm on
// 2026-10-23 found 0% of Karachi road segments with live congestion and nearly every
// traffic line marked "low" (Dubai, the control, showed heavy and severe jams). So the
// layer is labelled as limited and never shown unless a user turns it on. Tiles are
// fetched by each browser (Mapbox's terms do not allow re-serving them from our server);
// the browser caches them, and each map view uses roughly 10-30 of the 200k free
// monthly tile requests. See backend/traffic_probes/ for the probe reports.
export const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || "";

const SOURCE = "mapbox-traffic";
const LAYER = "mapbox-traffic-lines";
const KEY = "maps.mapboxTraffic"; // remembered per browser

export const MAPBOX_TRAFFIC_LEVELS = [
  ["low", "Free flow", "#4ade80"],
  ["moderate", "Moderate", "#fb923c"],
  ["heavy", "Heavy", "#ef4444"],
  ["severe", "Severe", "#7f1d1d"],
];

export function savedMapboxTraffic() {
  try { return Boolean(MAPBOX_TOKEN) && localStorage.getItem(KEY) === "on"; } catch { return false; }
}

export function rememberMapboxTraffic(on) {
  try { localStorage.setItem(KEY, on ? "on" : "off"); } catch { /* the choice just won't persist */ }
}

/** Shows or hides the Mapbox traffic lines on a loaded map. The tiles are only requested while shown. */
export function setMapboxTraffic(map, visible) {
  if (!MAPBOX_TOKEN) return;
  if (!map.getSource(SOURCE)) {
    if (!visible) return; // never fetch a tile for a layer nobody turned on
    map.addSource(SOURCE, {
      type: "vector",
      tiles: [`https://api.mapbox.com/v4/mapbox.mapbox-traffic-v1/{z}/{x}/{y}.vector.pbf?access_token=${MAPBOX_TOKEN}`],
      maxzoom: 16,
      attribution: '<a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noopener">© Mapbox</a>',
    });
    // Under the base map's labels and every route line the app draws on top.
    const firstLabel = map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
    map.addLayer({
      id: LAYER,
      type: "line",
      source: SOURCE,
      "source-layer": "traffic",
      minzoom: 9,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: {
        "line-color": ["match", ["get", "congestion"], ...MAPBOX_TRAFFIC_LEVELS.flatMap(([level, , color]) => [level, color]), "#94a3b8"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1, 13, 2.5, 16, 5],
        "line-opacity": 0.85,
      },
    }, firstLabel);
    return;
  }
  map.setLayoutProperty(LAYER, "visibility", visible ? "visible" : "none");
}
