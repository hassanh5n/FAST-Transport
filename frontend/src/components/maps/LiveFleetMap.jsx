import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { colors } from "../../theme";

const DEFAULT_CENTER = [67.0847, 24.9215];
const ROUTE_COLORS = ["#2563EB", "#DC2626", "#16A34A", "#9333EA", "#EA580C", "#0891B2", "#BE123C"];

const colorForRoute = (id) => ROUTE_COLORS[Math.abs(Number(id) || 0) % ROUTE_COLORS.length];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function routeFeatures(routes) {
  return routes.flatMap((route) => {
    const coordinates = route.geometry?.coordinates || (route.stops || []).map((stop) => [stop.longitude, stop.latitude]);
    if (coordinates.length < 2) return [];
    return [{
      type: "Feature",
      properties: { color: colorForRoute(route.id), name: route.name },
      geometry: { type: "LineString", coordinates },
    }];
  });
}

function statusColor(status) {
  if (status === "live") return "#16a34a";
  if (status === "stale" || status === "ping") return "#d97706";
  if (status === "no_tracker") return "#64748b";
  return "#dc2626";
}

function statusLabel(bus) {
  if (bus.status === "live") return "Live";
  if (bus.status === "stale") return "Stale";
  if (bus.status === "no_tracker") return "No tracker";
  if (bus.status === "ping") return "Last known";
  return "Offline";
}

function formatUpdated(value) {
  return value ? new Date(value).toLocaleTimeString() : "No position";
}

export default function LiveFleetMap({ routes = [], buses = [], height = 520, onBusSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(new Map());
  const fittedRef = useRef(false);
  const initialRoutesRef = useRef(routes);

  useEffect(() => {
    const markers = markersRef.current;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: DEFAULT_CENTER,
      zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));
    map.on("load", () => {
      map.addSource("fleet-routes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "fleet-route-casing", type: "line", source: "fleet-routes", paint: { "line-color": "#fff", "line-width": 7, "line-opacity": 0.9 }, layout: { "line-join": "round", "line-cap": "round" } });
      map.addLayer({ id: "fleet-routes", type: "line", source: "fleet-routes", paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.8 }, layout: { "line-join": "round", "line-cap": "round" } });
      mapRef.current = map;
      map.getSource("fleet-routes").setData({ type: "FeatureCollection", features: routeFeatures(initialRoutesRef.current) });
    });
    mapRef.current = map;
    return () => {
      markers.forEach((marker) => marker.remove());
      markers.clear();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const source = map.getSource("fleet-routes");
    if (source) source.setData({ type: "FeatureCollection", features: routeFeatures(routes) });
  }, [routes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const activeIds = new Set();
    buses.forEach((bus) => {
      if (bus.latitude == null || bus.longitude == null) return;
      activeIds.add(bus.bus_id);
      let marker = markersRef.current.get(bus.bus_id);
      if (!marker) {
        const element = document.createElement("button");
        element.type = "button";
        element.setAttribute("aria-label", `Bus ${bus.bus_number}`);
        element.style.cssText = "width:34px;height:34px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;color:#fff;font-size:17px;cursor:pointer;padding:0";
        element.addEventListener("click", () => onBusSelect?.(bus.bus_id));
        marker = new maplibregl.Marker({ element, anchor: "center" }).addTo(map);
        markersRef.current.set(bus.bus_id, marker);
      }
      const element = marker.getElement();
      const iconKey = `${bus.status}:${Number(bus.heading_degrees) || 0}`;
      if (element.dataset.fleetIconKey !== iconKey) {
        element.style.background = statusColor(bus.status);
        element.innerHTML = "<span aria-hidden=\"true\" style=\"display:block;\">&#128652;</span>";
        element.firstChild.style.transform = `rotate(${Number(bus.heading_degrees) || 0}deg)`;
        element.dataset.fleetIconKey = iconKey;
      }
      marker.setLngLat([Number(bus.longitude), Number(bus.latitude)]);
      const routeName = bus.route?.name || "Unassigned";
      const driverName = bus.driver?.name || "No driver";
      const popupKey = `${bus.bus_number}|${routeName}|${driverName}|${bus.status}|${bus.position_timestamp || ""}`;
      if (marker.fleetPopupKey !== popupKey) {
        marker.setPopup(new maplibregl.Popup({ offset: 20, closeButton: false }).setHTML(
          `<div style="font:13px sans-serif;min-width:170px"><strong>${escapeHtml(bus.bus_number)}</strong><br/>${escapeHtml(routeName)}<br/>${escapeHtml(driverName)}<br/><span style="color:${statusColor(bus.status)}">${escapeHtml(statusLabel(bus))}</span> · ${escapeHtml(formatUpdated(bus.position_timestamp))}</div>`
        ));
        marker.fleetPopupKey = popupKey;
      }
    });
    markersRef.current.forEach((marker, id) => {
      if (!activeIds.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    });
    if (!fittedRef.current) {
      const points = buses.filter((bus) => bus.latitude != null && bus.longitude != null).map((bus) => [Number(bus.longitude), Number(bus.latitude)]);
      if (points.length) {
        const bounds = points.reduce((result, point) => result.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
        map.fitBounds(bounds, { padding: 50, maxZoom: 13, duration: 0 });
        fittedRef.current = true;
      }
    }
  }, [buses, onBusSelect]);

  return (
    <div>
      <div ref={containerRef} style={{ height, width: "100%", borderRadius: 10, overflow: "hidden" }} aria-label="Live fleet map" />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 8, marginTop: 12 }}>
        {buses.map((bus) => (
          <button key={bus.bus_id} type="button" onClick={() => onBusSelect?.(bus.bus_id)} style={{ textAlign: "left", border: `1px solid ${colors.borderLight}`, borderLeft: `4px solid ${statusColor(bus.status)}`, borderRadius: 8, padding: "9px 10px", background: "#fff", cursor: "pointer", color: colors.textPrimary }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, fontWeight: 700 }}>
              <span>{bus.bus_number}</span><span style={{ color: statusColor(bus.status), fontSize: 11 }}>{statusLabel(bus)}</span>
            </div>
            <div style={{ marginTop: 4, fontSize: 12, color: colors.textSecondary }}>{bus.route?.name || "Unassigned"} · {bus.driver?.name || "No driver"}</div>
            <div style={{ marginTop: 3, fontSize: 11, color: colors.textMuted }}>{formatUpdated(bus.position_timestamp)}{bus.is_off_route ? " · Off route" : ""}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
