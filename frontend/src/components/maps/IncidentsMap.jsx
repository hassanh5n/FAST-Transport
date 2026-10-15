// Admin map of every incident report: each is drawn as its affected area plus a centre dot.
// The selected report is outlined, framed and labelled; clicking a report selects it.
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CAMPUS, addCampusMarker, MAP_STYLE } from "./campus";
import { circleRing, incidentColor } from "./incidents";

const IF_SELECTED = (yes, no) => ["case", ["get", "selected"], yes, no];

const lngLatOf = (incident) => {
  const lng = Number(incident.longitude);
  const lat = Number(incident.latitude);
  return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
};

function toFeatures(incidents, selectedId) {
  const areas = [];
  const points = [];
  incidents.forEach((incident) => {
    const lngLat = lngLatOf(incident);
    if (!lngLat) return;
    const properties = { id: incident.id, color: incidentColor(incident), selected: incident.id === selectedId };
    areas.push({ type: "Feature", properties, geometry: { type: "Polygon", coordinates: [circleRing(lngLat[0], lngLat[1], incident.radius_meters || 200)] } });
    points.push({ type: "Feature", properties, geometry: { type: "Point", coordinates: lngLat } });
  });
  return { areas: { type: "FeatureCollection", features: areas }, points: { type: "FeatureCollection", features: points } };
}

// Built from text nodes, never HTML: the description is whatever a student typed.
function popupContent(incident) {
  const box = document.createElement("div");
  box.style.cssText = "font:13px system-ui,sans-serif;max-width:220px;";
  const title = document.createElement("strong");
  title.textContent = `${incident.incident_type_display || "Incident"} · ${incident.severity_display || incident.severity || ""}`;
  const detail = document.createElement("div");
  detail.style.cssText = "margin-top:4px;color:#4a6178;";
  detail.textContent = incident.description || "No description given.";
  box.append(title, detail);
  return box;
}

export default function IncidentsMap({ incidents, selectedId = null, onSelect, height = 380 }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const latestRef = useRef({ incidents, onSelect });

  useEffect(() => {
    latestRef.current = { incidents, onSelect };
  }, [incidents, onSelect]);

  useEffect(() => {
    const map = new maplibregl.Map({ container: containerRef.current, style: MAP_STYLE, center: CAMPUS.center, zoom: CAMPUS.zoom });
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      const empty = { type: "FeatureCollection", features: [] };
      map.addSource("incident-areas", { type: "geojson", data: empty });
      map.addSource("incident-points", { type: "geojson", data: empty });
      map.addLayer({ id: "incident-areas-fill", type: "fill", source: "incident-areas", paint: { "fill-color": ["get", "color"], "fill-opacity": IF_SELECTED(0.35, 0.18) } });
      map.addLayer({ id: "incident-areas-line", type: "line", source: "incident-areas", paint: { "line-color": ["get", "color"], "line-width": IF_SELECTED(3, 1.5) } });
      // The dot keeps a report findable when zoomed out too far to see its area.
      map.addLayer({
        id: "incident-points", type: "circle", source: "incident-points",
        paint: { "circle-color": ["get", "color"], "circle-radius": IF_SELECTED(9, 6), "circle-stroke-color": IF_SELECTED("#0b2d42", "#fff"), "circle-stroke-width": IF_SELECTED(3, 2) },
      });
      ["incident-points", "incident-areas-fill"].forEach((layer) => {
        map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
      });
      map.on("click", (event) => {
        const [hit] = map.queryRenderedFeatures(event.point, { layers: ["incident-points", "incident-areas-fill"] });
        if (hit) latestRef.current.onSelect?.(hit.properties.id);
      });
    });
    mapRef.current = map;
    return () => { popupRef.current?.remove(); map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const data = toFeatures(incidents, selectedId);
      map.getSource("incident-areas")?.setData(data.areas);
      map.getSource("incident-points")?.setData(data.points);
    };
    if (map.isStyleLoaded()) update(); else map.once("load", update);
  }, [incidents, selectedId]);

  // Frame and label the selected report. Keyed on the selection only, so the background
  // refresh after approving or rejecting does not yank the map back.
  useEffect(() => {
    const map = mapRef.current;
    popupRef.current?.remove();
    popupRef.current = null;
    const incident = latestRef.current.incidents.find((item) => item.id === selectedId);
    const lngLat = incident && lngLatOf(incident);
    if (!map || !lngLat) return;
    const ring = circleRing(lngLat[0], lngLat[1], incident.radius_meters || 200);
    const bounds = ring.reduce((result, point) => result.extend(point), new maplibregl.LngLatBounds(ring[0], ring[0]));
    map.fitBounds(bounds, { padding: 90, maxZoom: 15, duration: 600 });
    popupRef.current = new maplibregl.Popup({ offset: 14, closeOnClick: false }).setLngLat(lngLat).setDOMContent(popupContent(incident)).addTo(map);
  }, [selectedId]);

  return <div ref={containerRef} style={{ height, borderRadius: 10, overflow: "hidden", border: "1px solid #dbe3ea" }} aria-label="Map of incident reports" />;
}
