// Live road traffic from Google, with the fleet's buses on top.
//
// Each time this component mounts it is one Google "map load" (10,000 free a
// month), so the dashboard keeps it mounted once opened instead of re-creating it.
// Route lines are off by default: drawn on top, they would hide the traffic
// colours on exactly the roads the buses use.
import { useEffect, useRef, useState } from "react";
import { CAMPUS } from "./campusLocation";
import { formatUpdated, statusColor, statusLabel } from "./fleetStatus";
import { loadGoogleMaps, onGoogleMapsAuthFailure } from "./googleMaps";
import { colors } from "../../theme";

// Google's own traffic colours, for the legend.
const TRAFFIC_LEGEND = [
  ["Free flow", "#63d668"],
  ["Slow", "#ff974d"],
  ["Heavy", "#f23c32"],
  ["Standstill", "#811f1f"],
];

const toLatLng = ([lng, lat]) => ({ lat: Number(lat), lng: Number(lng) });

function routeLine(route) {
  const coordinates = route.geometry?.coordinates?.length > 1
    ? route.geometry.coordinates
    : (route.stops || []).map((stop) => [stop.longitude, stop.latitude]);
  return coordinates
    .map(toLatLng)
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
}

function busPopup(bus) {
  const box = document.createElement("div");
  box.style.cssText = "font:13px/1.45 'DM Sans',system-ui,sans-serif;color:#0f1f2d;min-width:160px";
  const rows = [
    [bus.bus_number, "font-weight:700"],
    [bus.route?.name || "Unassigned", ""],
    [bus.driver?.name || "No driver", ""],
    [`${statusLabel(bus)} · ${formatUpdated(bus.position_timestamp)}`, `color:${statusColor(bus.status)}`],
  ];
  rows.forEach(([text, style]) => {
    const line = document.createElement("div");
    line.textContent = text;
    line.style.cssText = style;
    box.appendChild(line);
  });
  return box;
}

// showRoutesInitially: a single student or driver route is the point of the map, so it
// starts drawn there; the fleet view starts without lines so traffic stays readable.
export default function TrafficMap({ routes = [], buses = [], height = 420, showRoutesInitially = false }) {
  const containerRef = useRef(null);
  const googleRef = useRef(null);       // { maps, map, info }
  const busMarkersRef = useRef(new Map());
  const routeLinesRef = useRef([]);
  const fittedRef = useRef(false);
  const [state, setState] = useState("loading"); // loading | ready | error
  const [showRoutes, setShowRoutes] = useState(showRoutesInitially);

  useEffect(() => {
    let cancelled = false;
    const stopListening = onGoogleMapsAuthFailure(() => setState("error"));
    const markers = busMarkersRef.current;
    loadGoogleMaps()
      .then(async (maps) => {
        const [{ Map, TrafficLayer, InfoWindow }, { Marker }] = await Promise.all([
          maps.importLibrary("maps"), maps.importLibrary("marker"),
        ]);
        if (cancelled) return;
        const map = new Map(containerRef.current, {
          center: { lat: 24.88, lng: 67.12 }, // central Karachi to campus
          zoom: 11,
          mapTypeControl: false,
          streetViewControl: false,
          clickableIcons: false,
          gestureHandling: "cooperative",
        });
        new TrafficLayer().setMap(map);
        new Marker({ map, position: toLatLng(CAMPUS.center), title: CAMPUS.name });
        const info = new InfoWindow();
        // Which bus the popup shows, so fleet refreshes can redraw it while it is open.
        info.addListener("closeclick", () => { if (googleRef.current) googleRef.current.openBusId = null; });
        googleRef.current = { maps, map, Marker, info, openBusId: null };
        setState("ready");
      })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => {
      cancelled = true;
      stopListening();
      markers.forEach((marker) => marker.setMap(null));
      markers.clear();
      googleRef.current = null;
    };
  }, []);

  // Route lines, on request; the first time routes arrive the map frames them.
  useEffect(() => {
    const google = googleRef.current;
    if (state !== "ready" || !google) return;
    routeLinesRef.current.forEach((line) => line.setMap(null));
    const lines = routes.map(routeLine).filter((path) => path.length > 1);
    routeLinesRef.current = showRoutes
      ? lines.map((path) => new google.maps.Polyline({
        map: google.map, path, clickable: false,
        // One route (a student's or driver's) is the subject, so it is drawn bolder.
        strokeColor: colors.navyDeep, strokeOpacity: lines.length === 1 ? 0.8 : 0.55, strokeWeight: lines.length === 1 ? 4 : 2,
      }))
      : [];
    if (!fittedRef.current && lines.length) {
      const bounds = new google.maps.LatLngBounds();
      lines.flat().forEach((point) => bounds.extend(point));
      bounds.extend(toLatLng(CAMPUS.center));
      google.map.fitBounds(bounds, 24);
      fittedRef.current = true;
    }
  }, [routes, showRoutes, state]);

  // Buses: one marker each, moved in place on every fleet refresh.
  useEffect(() => {
    const google = googleRef.current;
    if (state !== "ready" || !google) return;
    const seen = new Set();
    buses.forEach((bus) => {
      if (bus.latitude == null || bus.longitude == null) return;
      seen.add(bus.bus_id);
      let marker = busMarkersRef.current.get(bus.bus_id);
      if (!marker) {
        marker = new google.Marker({ map: google.map, zIndex: 10 });
        marker.addListener("click", () => {
          google.info.setContent(busPopup(marker.bus));
          google.info.open({ map: google.map, anchor: marker });
          google.openBusId = marker.bus.bus_id;
        });
        busMarkersRef.current.set(bus.bus_id, marker);
      }
      marker.bus = bus;
      if (google.openBusId === bus.bus_id) google.info.setContent(busPopup(bus));
      marker.setPosition({ lat: Number(bus.latitude), lng: Number(bus.longitude) });
      marker.setTitle(`Bus ${bus.bus_number} · ${statusLabel(bus)}`);
      marker.setIcon({
        // A dark ring keeps a bus apart from the green/orange/red traffic lines under it.
        path: google.maps.SymbolPath.CIRCLE, scale: 10,
        fillColor: statusColor(bus.status), fillOpacity: 1, strokeColor: colors.navyDeep, strokeWeight: 3.5,
      });
    });
    busMarkersRef.current.forEach((marker, id) => {
      if (!seen.has(id)) {
        if (google.openBusId === id) {
          google.info.close();
          google.openBusId = null;
        }
        marker.setMap(null);
        busMarkersRef.current.delete(id);
      }
    });
  }, [buses, state]);

  return (
    <div>
      <div style={{ position: "relative", height, width: "100%", borderRadius: 10, overflow: "hidden", background: colors.pageBg }}>
        <div ref={containerRef} style={{ position: "absolute", inset: 0 }} aria-label="Live traffic map" />
        {state === "ready" && (
          <button
            type="button"
            aria-pressed={showRoutes}
            onClick={() => setShowRoutes((value) => !value)}
            style={{
              position: "absolute", top: 10, left: 10, zIndex: 2, border: `1px solid ${colors.borderMid}`,
              background: showRoutes ? colors.navyDeep : "#fff", color: showRoutes ? "#fff" : colors.textSecondary,
              borderRadius: 8, padding: "6px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              boxShadow: "0 1px 4px rgba(11,45,66,0.18)",
            }}
          >
            {`${showRoutes ? "Hide" : "Show"} ${routes.length === 1 ? "route" : "bus routes"}`}
          </button>
        )}
        {state !== "ready" && (
          <div style={{ position: "absolute", inset: 0, zIndex: 3, background: colors.pageBg, display: "flex", alignItems: "center", justifyContent: "center", padding: 24, textAlign: "center", fontSize: 13, color: state === "error" ? colors.warningText : colors.textMuted }}>
            {state === "error"
              ? "The live traffic map is unavailable. The Google Maps key may be missing or invalid, or today's map limit is used up."
              : "Loading live traffic…"}
          </div>
        )}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "center", marginTop: 10, fontSize: 12, color: colors.textSecondary }}>
        {TRAFFIC_LEGEND.map(([label, color]) => (
          <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span aria-hidden="true" style={{ width: 18, height: 4, borderRadius: 2, background: color }} />
            {label}
          </span>
        ))}
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span aria-hidden="true" style={{ width: 12, height: 12, borderRadius: "50%", background: statusColor("live"), border: `3px solid ${colors.navyDeep}` }} />
          Bus (colour shows tracker status)
        </span>
        <span style={{ color: colors.textMuted }}>Live traffic from Google; it refreshes on its own.</span>
      </div>
    </div>
  );
}
