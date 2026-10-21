// Overview map of every stop: click a stop to open it, click empty map to add one there.
// Stops are one circle layer (not hundreds of DOM pins), so the map stays light and legible.
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CAMPUS, MAP_COLORS, MAP_STYLE, addCampusMarker, escapeHtml } from "./campus";

const lngLatOf = (stop) => {
  const lat = Number(stop.latitude);
  const lng = Number(stop.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return [lng, lat];
};

const featuresOf = (stops) => ({
  type: "FeatureCollection",
  features: stops.flatMap((stop) => {
    const lngLat = lngLatOf(stop);
    if (!lngLat) return [];
    return [{ type: "Feature", id: Number(stop.id), properties: { id: Number(stop.id), name: stop.name || "", active: stop.is_active !== false }, geometry: { type: "Point", coordinates: lngLat } }];
  }),
});

export default function StopsMap({ stops, height = 520, highlightId = null, onStopClick, onMapClick }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const stopsRef = useRef(stops);
  const [ready, setReady] = useState(false);
  const handlersRef = useRef({ onStopClick, onMapClick });

  useEffect(() => {
    handlersRef.current = { onStopClick, onMapClick };
    stopsRef.current = stops;
  }, [onStopClick, onMapClick, stops]);

  useEffect(() => {
    const map = new maplibregl.Map({ container: containerRef.current, style: MAP_STYLE, center: CAMPUS.center, zoom: CAMPUS.zoom });
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
    map.on("load", () => {
      map.addSource("stops", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "stops", type: "circle", source: "stops",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 2.5, 12, 4.5, 15, 7],
          "circle-color": ["case", ["get", "active"], MAP_COLORS.accent, "#cbd5e1"],
          "circle-stroke-color": "#fff",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 13, 1.8],
        },
      });
      map.addLayer({
        id: "stops-highlight", type: "circle", source: "stops", filter: ["==", ["get", "id"], -1],
        paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 7, 15, 12], "circle-color": "#fff", "circle-stroke-color": MAP_COLORS.pin, "circle-stroke-width": 3 },
      });
      map.on("click", (event) => {
        const hit = map.queryRenderedFeatures(event.point, { layers: ["stops"] })[0];
        if (hit) {
          const stop = stopsRef.current.find((item) => Number(item.id) === Number(hit.properties.id));
          if (stop) handlersRef.current.onStopClick?.(stop);
          return; // a stop click opens the stop; it must not also count as a map click
        }
        handlersRef.current.onMapClick?.({ latitude: event.lngLat.lat.toFixed(6), longitude: event.lngLat.lng.toFixed(6) });
      });
      map.on("mouseenter", "stops", (event) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = event.features?.[0];
        if (!feature) return;
        const name = escapeHtml(feature.properties.name);
        const note = feature.properties.active ? "" : ' <span style="color:#8faabb;">(inactive)</span>';
        tip.setLngLat(feature.geometry.coordinates).setHTML(`<div style="font:600 12px 'DM Sans',system-ui,sans-serif;color:#0f1f2d;">${name}${note}</div>`).addTo(map);
      });
      map.on("mouseleave", "stops", () => { map.getCanvas().style.cursor = ""; tip.remove(); });
      setReady(true);
    });
    mapRef.current = map;
    return () => { tip.remove(); map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    if (ready) mapRef.current?.getSource("stops")?.setData(featuresOf(stops));
  }, [stops, ready]);

  useEffect(() => {
    if (ready) mapRef.current?.setFilter("stops-highlight", ["==", ["get", "id"], highlightId == null ? -1 : Number(highlightId)]);
  }, [highlightId, ready]);

  return <div ref={containerRef} style={{ height, borderRadius: 10, overflow: "hidden", border: "1px solid #dbe3ea" }} aria-label="Map of all stops" />;
}
