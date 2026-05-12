import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Banner } from "../../components/ui";
import { colors, fonts, radius } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";
import api from "../../services/api";

const POLL_INTERVAL_MS = 8000;

async function fetchRoadRoute(stops) {
  const coords = stops.map(s => `${s.lng},${s.lat}`).join(";");
  try {
    const res = await fetch(
      `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`
    );
    const data = await res.json();
    if (data.code === "Ok" && data.routes.length > 0) {
      return data.routes[0].geometry.coordinates;
    }
  } catch (e) {
    console.warn("OSRM routing failed, falling back to straight lines:", e);
  }
  return stops.map(s => [s.lng, s.lat]);
}

export default function StudentMap() {
  const mapContainer = useRef(null);
  const mapRef       = useRef(null);
  const busMarkerRef = useRef(null);
  const markerElRef  = useRef(null);
  const pollRef      = useRef(null);
  const isMobile     = useBreakpoint(768);

  const [trackingData, setTrackingData] = useState(null);
  const [liveData, setLiveData]         = useState(null);
  const [error, setError]               = useState("");
  const [lastUpdated, setLastUpdated]   = useState(null);
  const [isStale, setIsStale]           = useState(false);

  // 1. Load route metadata once
  useEffect(() => {
    api.get("/api/student/bus-tracking/")
      .then(res => setTrackingData(res.data))
      .catch(err => setError(err.response?.data?.detail || "Failed to load route data"));
  }, []);

  // 2. Poll live GPS
  const fetchLiveLocation = useCallback(() => {
    api.get("/api/student/live-location/")
      .then(res => {
        if (res.data?.lat && res.data?.lng) {
          setLiveData(res.data);
          setLastUpdated(new Date());
          setIsStale(false);
        }
      })
      .catch(() => setIsStale(true));
  }, []);

  useEffect(() => {
    fetchLiveLocation();
    pollRef.current = setInterval(fetchLiveLocation, POLL_INTERVAL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchLiveLocation]);

  // 3. Init map ONCE on mount
  useEffect(() => {
    if (mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [67.0847, 24.9215],
      zoom: 12,
    });

    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      const busEl = document.createElement("div");
      busEl.style.cssText = `width: 36px; height: 36px;
      background: #c42828; border-radius: 50%;
      border: 3px solid white;
      box-shadow: 0 2px 8px rgba(0,0,0,0.5);
      display: none; align-items: center;
      justify-content: center; font-size: 18px;
      cursor: pointer;`;
      busEl.innerHTML = "🚌";
      markerElRef.current = busEl;
      busMarkerRef.current = new maplibregl.Marker({ element: busEl, anchor: "center" })
        .setLngLat([67.0847, 24.9215])
        .addTo(map);
    });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // 4. Populate route + stops when trackingData loads
  useEffect(() => {
    if (!trackingData || !mapRef.current) return;

    const validStops = (trackingData.stops || []).filter(s => s.lat && s.lng);
    if (!validStops.length) return;

    const map = mapRef.current;

    const populateMap = async () => {
      if (!map.isStyleLoaded()) {
        map.once("load", () => populateMap());
        return;
      }

      // Draw road-following route
      const routeCoords = await fetchRoadRoute(validStops);
      if (map.getSource("route")) {
        map.getSource("route").setData({
          type: "Feature",
          geometry: { type: "LineString", coordinates: routeCoords },
        });
      } else {
        map.addSource("route", {
          type: "geojson",
          data: {
            type: "Feature",
            geometry: { type: "LineString", coordinates: routeCoords },
          },
        });
        map.addLayer({
          id: "route-line", type: "line", source: "route",
          paint: { "line-color": "#3B82F6", "line-width": 4, "line-opacity": 0.85 },
          layout: { "line-join": "round", "line-cap": "round" },
        });
      }

      // Fit map to show all stops
      const bounds = validStops.reduce(
        (b, s) => b.extend([s.lng, s.lat]),
        new maplibregl.LngLatBounds(
          [validStops[0].lng, validStops[0].lat],
          [validStops[0].lng, validStops[0].lat]
        )
      );
      map.fitBounds(bounds, { padding: isMobile ? 30 : 60, maxZoom: 14 });

      // Add stop markers
      validStops.forEach(stop => {
        const isStudentStop = stop.name === trackingData.student_stop_name;
        const el = document.createElement("div");
        el.style.cssText = `
          width: ${isStudentStop ? "18px" : "12px"};
          height: ${isStudentStop ? "18px" : "12px"};
          border-radius: 50%;
          background: ${isStudentStop ? "#F59E0B" : "#6B7280"};
          border: 2px solid white;
          box-shadow: 0 1px 4px rgba(0,0,0,0.5);
          cursor: pointer;
        `;
        new maplibregl.Marker({ element: el })
          .setLngLat([stop.lng, stop.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 12 }).setHTML(
              `<strong>${stop.name}</strong>
              ${stop.morning_eta ? `<br/>🕐 Morning ETA: ${stop.morning_eta}` : ""}
              ${isStudentStop ? "<br/><em style='color:#F59E0B'>📍 Your stop</em>" : ""}`
            )
          )
          .addTo(map);
      });
    };

    populateMap();
  }, [trackingData]);

  // 5. Move bus marker on every GPS update
  useEffect(() => {
    if (!liveData || !busMarkerRef.current || !mapRef.current) return;
    const { lat, lng, heading } = liveData;
    if (!lat || !lng) return;

    if (markerElRef.current) {
      markerElRef.current.style.display = "flex";
      if (heading) markerElRef.current.style.transform = `rotate(${heading}deg)`;
    }
    busMarkerRef.current.setLngLat([lng, lat]);
  }, [liveData]);

  const timeSince = (date) => {
    if (!date) return "—";
    const secs = Math.floor((new Date() - date) / 1000);
    if (secs < 60) return `${secs}s ago`;
    return `${Math.floor(secs / 60)}m ago`;
  };

  const speedLabel = () => {
    if (!liveData) return "Waiting for GPS...";
    if (liveData.ignition === false) return "🔴 Ignition OFF";
    if (liveData.speed === 0) return "🟡 Idling";
    return `🟢 ${liveData.speed} km/h`;
  };

  return (
    <PageShell role="student" title="Live Bus Tracking">
      <PageTitle sub="Real-time GPS tracking for your assigned bus.">Live Bus Tracking</PageTitle>

      {error && <Banner variant="danger">{error}</Banner>}

      {isStale && (
        <Banner variant="warning">
          GPS signal lost or bus is offline. Showing last known position.
        </Banner>
      )}

      {/* Info cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile
          ? "repeat(auto-fit, minmax(130px, 1fr))"
          : "repeat(auto-fit, minmax(160px, 1fr))",
        gap: 12, marginBottom: 16,
      }}>
        <InfoCard label="Route"       value={trackingData?.route_name ?? "—"} />
        <InfoCard label="Bus"         value={liveData?.bus_number ?? trackingData?.bus?.bus_number ?? "—"} />
        <InfoCard label="Driver"      value={liveData?.driver_name ?? trackingData?.bus?.driver_name ?? "—"} />
        <InfoCard label="Speed"       value={speedLabel()} accent={liveData?.speed > 0} />
        <InfoCard label="GPS Updated" value={timeSince(lastUpdated)} warning={isStale} />
      </div>

      {/* Map */}
      <div style={{
        position: "relative",
        height: isMobile ? "calc(100vh - 380px)" : 520,
        minHeight: 280,
        borderRadius: 12,
        border: `1px solid ${colors.borderLight}`,
        overflow: "hidden",
      }}>
        <div
          ref={mapContainer}
          style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, borderRadius: 12 }}
        />
        {!trackingData && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255,255,255,0.8)", borderRadius: 12, zIndex: 10 }}>
            <div style={{
              width: "28px", height: "28px", borderRadius: "50%",
              border: `3px solid ${colors.borderLight}`,
              borderTopColor: colors.accent,
              animation: "spin 0.7s linear infinite",
            }} />
          </div>
        )}
      </div>

      <p style={{ fontSize: 12, color: colors.textMuted, marginTop: 8 }}>
        🟡 Your stop &nbsp;·&nbsp; ⚫ Other stops &nbsp;·&nbsp; 🔵 Route &nbsp;·&nbsp; 🚌 Live bus position (updates every 8s)
      </p>
    </PageShell>
  );
}

function InfoCard({ label, value, accent, warning }) {
  return (
    <div style={{
      background: "#fff",
      border: warning ? "1px solid #fcd34d" : `1px solid ${colors.borderLight}`,
      borderRadius: radius.lg,
      padding: "12px 16px",
      boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
    }}>
      <div style={{ fontSize: 11, color: colors.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{
        fontSize: 15, fontWeight: 600,
        color: accent ? colors.successText : warning ? colors.warningText : colors.textPrimary,
        wordBreak: "break-word",
      }}>
        {value}
      </div>
    </div>
  );
}