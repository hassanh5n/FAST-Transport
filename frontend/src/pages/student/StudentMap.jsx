import { Suspense, lazy, useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Banner, Spinner } from "../../components/ui";
import { btn, colors, radius } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";
import api from "../../services/api";
import {
  CAMPUS, MAP_COLORS, MAP_STYLE, WALK_SHOWN_FROM_M,
  addCampusMarker, addRouteArrows, routeWidth, stopPopupHtml, walkLabel,
} from "../../components/maps/campus";
import { showTrafficAlerts, useTrafficAlerts } from "../../components/maps/trafficAlerts";
import { rememberMapboxTraffic, savedMapboxTraffic, setMapboxTraffic } from "../../components/maps/mapboxTraffic";
import { TrafficLegend } from "../../components/maps/TrafficControls";
import { ageLabel } from "../../components/maps/fleetStatus";
import { GOOGLE_MAPS_API_KEY, loadGoogleMaps } from "../../components/maps/googleMaps";
import { addMyLocationControl } from "../../components/maps/myLocation";

// Google's live traffic, as on the admin dashboard. Loaded only when the student opens it.
const TrafficMap = lazy(() => import("../../components/maps/TrafficMap"));

const POLL_INTERVAL_MS = 8000;
const INCIDENT_POLL_INTERVAL_MS = 30000;
const CRIME_RISK_REFRESH_MS = 15 * 60 * 1000;
const incidentColor = (severity) => (
  severity === "high" ? "#EF4444" : severity === "medium" ? "#F97316" : "#F59E0B"
);

function incidentGeoJSON(incidents) {
  const earthRadius = 6371000;
  return { type: "FeatureCollection", features: incidents.map((incident) => {
    const points = [];
    const latitudeRadians = (Number(incident.latitude) * Math.PI) / 180;
    const latitudeOffset = (Number(incident.radius_meters) / earthRadius) * (180 / Math.PI);
    const longitudeOffset = latitudeOffset / Math.cos(latitudeRadians);
    for (let index = 0; index <= 64; index += 1) {
      const angle = (index / 64) * 2 * Math.PI;
      points.push([Number(incident.longitude) + longitudeOffset * Math.sin(angle), Number(incident.latitude) + latitudeOffset * Math.cos(angle)]);
    }
    return { type: "Feature", properties: { color: incidentColor(incident.severity), incidentType: incident.incident_type_display, severity: incident.severity, occurredAt: incident.occurred_at, description: incident.description || "" }, geometry: { type: "Polygon", coordinates: [points] } };
  }) };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

export default function StudentMap() {
  const mapContainer = useRef(null);
  const mapRef       = useRef(null);
  const busMarkerRef = useRef(null);
  const markerElRef  = useRef(null);
  const pollRef      = useRef(null);
  const isMobile     = useBreakpoint(768);
  const isMobileRef  = useRef(isMobile);

  const [trackingData, setTrackingData] = useState(null);
  const [liveData, setLiveData]         = useState(null);
  const [error, setError]               = useState("");
  const [lastUpdated, setLastUpdated]   = useState(null);
  const [isStale, setIsStale]           = useState(false);
  const [incidents, setIncidents]       = useState([]);
  const [crimeRiskZones, setCrimeRiskZones] = useState([]);
  const [crimeRiskEnabled, setCrimeRiskEnabled] = useState(true);
  const [crimeRiskStatus, setCrimeRiskStatus] = useState("");
  const [mapReady, setMapReady] = useState(false);  // the map's "load" has fired
  const traffic = useTrafficAlerts();
  const [trafficShown, setTrafficShown] = useState(true);
  // "bus" (our map) or "traffic" (Google). Google counts every map it creates, so the
  // traffic map is created the first time it is opened and then kept, not re-made.
  const [mapView, setMapView] = useState("bus");
  const [trafficOpened, setTrafficOpened] = useState(false);

  const [mapboxOn, setMapboxOn] = useState(savedMapboxTraffic);

  // Shared traffic incidents, redrawn whenever the server's copy changes or they are toggled.
  useEffect(() => {
    if (mapReady && mapRef.current) showTrafficAlerts(mapRef.current, traffic.alerts, trafficShown);
  }, [mapReady, traffic.alerts, trafficShown]);

  // Optional Mapbox traffic lines (off unless this browser turned them on).
  useEffect(() => {
    if (mapReady && mapRef.current) setMapboxTraffic(mapRef.current, mapboxOn);
  }, [mapReady, mapboxOn]);

  useEffect(() => {
    isMobileRef.current = isMobile;
  }, [isMobile]);

  // 1. Load route metadata once
  useEffect(() => {
    api.get("/api/student/bus-tracking/")
      .then(res => setTrackingData(res.data))
      .catch(err => setError(err.response?.data?.detail || "Failed to load route data"));
  }, []);

  // 2. Poll live GPS
  // The server sends the newest position from the bus tracker or the driver's phone,
  // live or last known (up to 12 h), with the time it was actually recorded.
  const fetchLiveLocation = useCallback(() => {
    api.get("/api/student/live-location/")
      .then(res => {
        if (res.data?.lat && res.data?.lng) {
          setLiveData(res.data);
          setLastUpdated(res.data.timestamp ? new Date(res.data.timestamp) : new Date());
          setIsStale(res.data.is_live === false);
        }
      })
      .catch(() => setIsStale(true)); // keep showing whatever was last received
  }, []);

  useEffect(() => {
    fetchLiveLocation();
    pollRef.current = setInterval(fetchLiveLocation, POLL_INTERVAL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchLiveLocation]);

  // 2b. Poll approved incidents
  const fetchIncidents = useCallback(() => {
    api.get("/api/incidents/approved/")
      .then(res => setIncidents(Array.isArray(res.data) ? res.data : []))
      .catch(err => console.error("Failed to load incidents:", err));
  }, []);

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, INCIDENT_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchIncidents]);

  const fetchCrimeRiskZones = useCallback((map) => {
    if (!map) return;
    const bounds = map.getBounds();
    const bbox = [
      bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth(),
    ].join(",");
    api.get(`/api/crime-risk/zones/?bbox=${encodeURIComponent(bbox)}`)
      .then(res => {
        const features = Array.isArray(res.data?.features) ? res.data.features : [];
        setCrimeRiskZones(features);
        setCrimeRiskStatus(res.data?.available ? "" : (res.data?.message || "Crime-risk data is not available yet."));
      })
      .catch(() => setCrimeRiskStatus("Crime-risk overlay is temporarily unavailable."));
  }, []);

  // 3. Init map ONCE on mount
  useEffect(() => {
    if (mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: CAMPUS.center,
      zoom: CAMPUS.zoom,
    });

    mapRef.current = map;

    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    addMyLocationControl(map); // "show my location" button

    map.on("load", () => {
      setMapReady(true);
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

      // Automated crime-risk cells. This is a separate source from student
      // incident reports and is rendered underneath the route and markers.
      map.addSource("crime-risk-zones", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "crime-risk-zones-fill",
        type: "fill",
        source: "crime-risk-zones",
        paint: {
          "fill-color": ["match", ["get", "current_level"],
            "very_high", "#991B1B",
            "high", "#DC2626",
            "elevated", "#F59E0B",
            "low", "#FDE047",
            "#9CA3AF",
          ],
          "fill-opacity": ["match", ["get", "current_level"],
            "very_high", 0.32,
            "high", 0.25,
            "elevated", 0.20,
            "low", 0.12,
            0.08,
          ],
        },
      });
      map.addLayer({
        id: "crime-risk-zones-outline",
        type: "line",
        source: "crime-risk-zones",
        paint: {
          "line-color": ["match", ["get", "current_level"],
            "very_high", "#7F1D1D",
            "high", "#B91C1C",
            "elevated", "#D97706",
            "low", "#CA8A04",
            "#9CA3AF",
          ],
          "line-width": ["match", ["get", "current_level"], "very_high", 2, "high", 1.5, 1],
          "line-opacity": 0.8,
        },
      });

      map.on("click", "crime-risk-zones-fill", (e) => {
        if (!e.features?.[0]) return;
        const props = e.features[0].properties || {};
        const score = props.current_score == null ? "—" : `${Number(props.current_score).toFixed(0)}/100`;
        const updated = props.source_updated_at ? new Date(props.source_updated_at).toLocaleString() : "—";
        new maplibregl.Popup({ closeButton: false })
          .setLngLat(e.lngLat)
          .setHTML(`<div style="font-family:sans-serif;font-size:13px;min-width:180px;">
            <strong style="font-size:14px;">Reported-crime risk</strong>
            <br/><span style="color:#666;">Level:</span> <strong style="text-transform:capitalize;">${escapeHtml(String(props.current_level || "unclassified").replace("_", " "))}</strong>
            <br/><span style="color:#666;">Score:</span> ${escapeHtml(score)}
            <br/><span style="color:#666;">Confidence:</span> <span style="text-transform:capitalize;">${escapeHtml(props.confidence || "none")}</span>
            <br/><span style="color:#666;">Source updated:</span> ${escapeHtml(updated)}
            <div style="margin-top:7px;padding-top:7px;border-top:1px solid #eee;color:#666;font-size:11px;">Aggregated external crime data; not a guarantee of personal safety.</div>
          </div>`)
          .addTo(map);
      });
      map.on("mouseenter", "crime-risk-zones-fill", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "crime-risk-zones-fill", () => { map.getCanvas().style.cursor = ""; });

      // Add incidents source & layers
      map.addSource("incidents", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addLayer({
        id: "incidents-fill",
        type: "fill",
        source: "incidents",
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.4
        }
      });
      map.addLayer({
        id: "incidents-outline",
        type: "line",
        source: "incidents",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 2
        }
      });

      // Incident Popups
      map.on("click", "incidents-fill", (e) => {
        if (!e.features || !e.features[0]) return;
        const props = e.features[0].properties;
        const html = `
          <div style="font-family: sans-serif; font-size: 13px;">
            <strong style="color: ${props.color}; font-size: 14px;">
              ${escapeHtml(props.incidentType)}
            </strong>
            <br/><span style="color: #666;">Occurred:</span> ${new Date(props.occurredAt).toLocaleString()}
            <br/><span style="color: #666;">Severity:</span> <span style="text-transform: capitalize;">${escapeHtml(props.severity)}</span>
            ${props.description ? `<div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #eee;">${escapeHtml(props.description)}</div>` : ""}
          </div>
        `;
        new maplibregl.Popup({ closeButton: false })
          .setLngLat(e.lngLat)
          .setHTML(html)
          .addTo(map);
      });

      map.on("mouseenter", "incidents-fill", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "incidents-fill", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Load only the visible cells; refresh slowly because external crime data is
  // not GPS-like realtime data.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;
    const load = () => fetchCrimeRiskZones(map);
    if (map.isStyleLoaded()) load(); else map.once("load", load);
    const onMove = () => fetchCrimeRiskZones(map);
    map.on("moveend", onMove);
    const interval = setInterval(() => fetchCrimeRiskZones(map), CRIME_RISK_REFRESH_MS);
    return () => {
      map.off("moveend", onMove);
      clearInterval(interval);
    };
  }, [fetchCrimeRiskZones]);

  // 4. Populate route + stops when trackingData loads. Waits on mapReady, not
  // isStyleLoaded(): that is also false while any source (traffic, crime risk) is still
  // loading, and waiting for a "load" that already fired left the route undrawn.
  useEffect(() => {
    if (!trackingData || !mapRef.current || !mapReady) return;

    const validStops = (trackingData.stops || []).filter(s => s.lat && s.lng);
    if (!validStops.length) return;

    const map = mapRef.current;

    const populateMap = () => {

      // The server's main-road line; stop to stop until it has one.
      const routeCoords = trackingData.geometry?.coordinates || validStops.map(s => [s.lng, s.lat]);
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
        // Same look as the route pages: white casing, zoom-scaled line, direction arrows.
        map.addLayer({
          id: "route-casing", type: "line", source: "route",
          paint: { "line-color": MAP_COLORS.casing, "line-width": routeWidth(3.5) },
          layout: { "line-join": "round", "line-cap": "round" },
        });
        map.addLayer({
          id: "route-line", type: "line", source: "route",
          paint: { "line-color": MAP_COLORS.accent, "line-width": routeWidth() },
          layout: { "line-join": "round", "line-cap": "round" },
        });
        addRouteArrows(map, "route-arrows", "route");
      }

      // Stops off the main road: a dashed walk from the stop to where the bus picks up.
      const offRoad = validStops.filter(s => !s.is_campus && Array.isArray(s.boarding) && (s.walk_m || 0) >= WALK_SHOWN_FROM_M);
      const walks = { type: "FeatureCollection", features: offRoad.map(s => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[s.lng, s.lat], s.boarding] } })) };
      const pickups = { type: "FeatureCollection", features: offRoad.map(s => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: s.boarding } })) };
      if (map.getSource("walks")) {
        map.getSource("walks").setData(walks);
        map.getSource("pickups").setData(pickups);
      } else {
        map.addSource("walks", { type: "geojson", data: walks });
        map.addLayer({ id: "walks", type: "line", source: "walks", layout: { "line-cap": "round" }, paint: { "line-color": MAP_COLORS.walk, "line-width": 2, "line-dasharray": [0.6, 2] } });
        map.addSource("pickups", { type: "geojson", data: pickups });
        map.addLayer({ id: "pickups", type: "circle", source: "pickups", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.5, 15, 4.5], "circle-color": "#fff", "circle-stroke-color": MAP_COLORS.accent, "circle-stroke-width": 2 } });
      }

      // Fit map to show all stops
      const bounds = validStops.reduce(
        (b, s) => b.extend([s.lng, s.lat]),
        new maplibregl.LngLatBounds(
          [validStops[0].lng, validStops[0].lat],
          [validStops[0].lng, validStops[0].lat]
        )
      );
      bounds.extend(CAMPUS.center); // keep the campus in frame with the route
      map.fitBounds(bounds, { padding: isMobileRef.current ? 30 : 60, maxZoom: 14 });

      // Numbered stop pins at the real stop locations; the student's own stop is amber.
      let number = 0;
      validStops.forEach(stop => {
        if (stop.is_campus) return; // the campus badge marks the end of the route
        number += 1;
        const isStudentStop = stop.name === trackingData.student_stop_name;
        const el = document.createElement("div");
        const size = isStudentStop ? 26 : 20;
        el.textContent = number;
        el.style.cssText = `
          width: ${size}px; height: ${size}px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          background: ${isStudentStop ? MAP_COLORS.yours : "#fff"};
          color: ${MAP_COLORS.pin};
          font: 700 ${isStudentStop ? 12 : 10.5}px/1 'DM Sans', system-ui, sans-serif;
          border: ${isStudentStop ? "2.5px solid #fff" : `2px solid ${MAP_COLORS.pin}`};
          box-shadow: 0 1px 3px rgba(11,45,66,0.35);
          cursor: pointer;
        `;
        const pin = new maplibregl.Marker({ element: el })
          .setLngLat([stop.lng, stop.lat])
          .setPopup(new maplibregl.Popup({ offset: 14, closeButton: false }).setHTML(stopPopupHtml({
            name: stop.name, morningEta: stop.est_morning_eta, eveningEta: stop.est_evening_eta,
            walkM: stop.walk_m, isYours: isStudentStop,
          })))
          .addTo(map);
        // MapLibre labels every pin "Map marker"; name the stop for screen readers instead.
        pin.getElement().setAttribute("aria-label", `Stop ${number}: ${stop.name}${isStudentStop ? " (your stop)" : ""}`);
      });
    };

    populateMap();
  }, [trackingData, mapReady]);

  // 5. Move bus marker on every GPS update
  const busFramedRef = useRef(false);
  useEffect(() => {
    if (!liveData || !busMarkerRef.current || !mapRef.current) return;
    const { lat, lng, heading } = liveData;
    if (!lat || !lng) return;

    if (markerElRef.current) {
      markerElRef.current.style.display = "flex";
      if (heading) markerElRef.current.style.transform = `rotate(${heading}deg)`;
      markerElRef.current.title = isStale ? `Last seen ${ageLabel(liveData.age_seconds)}` : "Your bus";
    }
    // A last-known position is faded so it does not read as the bus being there now.
    // (MapLibre owns the marker's opacity, so it is set through the marker.)
    busMarkerRef.current.setLngLat([lng, lat]).setOpacity(isStale ? "0.55" : "1");

    // The first time the bus appears, widen the view if it is outside it (once, so the
    // student can still pan freely while the bus moves).
    const map = mapRef.current;
    if (!busFramedRef.current && map.getBounds) {
      busFramedRef.current = true;
      const view = map.getBounds();
      if (!view.contains([lng, lat])) {
        map.fitBounds(view.extend([lng, lat]), { padding: isMobileRef.current ? 30 : 60, maxZoom: 14, duration: 600 });
      }
    }
  }, [liveData, isStale]);

  // 6. Update incidents GeoJSON
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    
    const updateIncidents = () => {
      const src = map.getSource("incidents");
      if (src) {
        src.setData(incidentGeoJSON(incidents));
      }
    };

    if (map.isStyleLoaded()) {
      updateIncidents();
    } else {
      map.once("load", updateIncidents);
    }
  }, [incidents]);

  useEffect(() => {
    const map = mapRef.current;
    const src = map?.getSource("crime-risk-zones");
    if (src) src.setData({ type: "FeatureCollection", features: crimeRiskZones });
  }, [crimeRiskZones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer("crime-risk-zones-fill")) return;
    const visibility = crimeRiskEnabled ? "visible" : "none";
    map.setLayoutProperty("crime-risk-zones-fill", "visibility", visibility);
    map.setLayoutProperty("crime-risk-zones-outline", "visibility", visibility);
  }, [crimeRiskEnabled]);

  const timeSince = (date) => {
    if (!date) return "—";
    return ageLabel(Math.max(0, Math.floor((new Date() - date) / 1000)));
  };

  const speedLabel = () => {
    if (!liveData) return "Waiting for GPS...";
    if (isStale) return "Not moving live";
    if (liveData.speed == null) return "Location from driver's phone";
    if (liveData.ignition === false) return "🔴 Ignition OFF";
    if (liveData.speed === 0) return "🟡 Idling";
    return `🟢 ${liveData.speed} km/h`;
  };

  const mapHeight = isMobile ? Math.max(280, window.innerHeight - 380) : 520;

  const chooseMapView = (view) => {
    setMapView(view);
    if (view === "traffic") setTrafficOpened(true);
    // MapLibre cannot measure itself while hidden; size it again when it comes back.
    else requestAnimationFrame(() => mapRef.current?.resize());
  };
  const warmUpTraffic = () => {
    import("../../components/maps/TrafficMap");
    loadGoogleMaps().catch(() => {});
  };

  // The student's own route and bus, in the shape TrafficMap draws.
  const myRoute = trackingData ? [{
    id: "mine", geometry: trackingData.geometry,
    stops: (trackingData.stops || []).map((s) => ({ longitude: s.lng, latitude: s.lat })),
  }] : [];
  const myBus = liveData?.lat && liveData?.lng ? [{
    bus_id: "mine", bus_number: liveData.bus_number || trackingData?.bus?.bus_number || "Your bus",
    latitude: liveData.lat, longitude: liveData.lng, status: isStale ? "stale" : "live",
    route: { name: trackingData?.route_name }, driver: { name: liveData.driver_name || trackingData?.bus?.driver_name },
    position_timestamp: lastUpdated,
  }] : [];

  return (
    <PageShell role="student" title="Live Bus Tracking">
      <PageTitle sub="Real-time GPS tracking for your assigned bus.">Live Bus Tracking</PageTitle>

      {error && <Banner variant="danger">{error}</Banner>}

      {isStale && (
        <Banner variant="warning">
          {liveData
            ? `Your bus has stopped sharing its location. The map shows where it was last seen, ${timeSince(lastUpdated)}.`
            : "Your bus is not sharing its location right now. It will appear on the map once it does."}
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
        <InfoCard label={isStale && liveData ? "Last seen" : "GPS updated"} value={timeSince(lastUpdated)} warning={isStale} />
      </div>

      {/* Bus map or Google live traffic, as on the admin dashboard */}
      {GOOGLE_MAPS_API_KEY && (
        <div role="group" aria-label="Map view" style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {[["bus", "Bus map"], ["traffic", "Live traffic"]].map(([key, label]) => (
            <button
              key={key} type="button" aria-pressed={mapView === key} onClick={() => chooseMapView(key)}
              // Start fetching Google's script on hover or focus; it is free until a map is made.
              onPointerEnter={key === "traffic" ? warmUpTraffic : undefined}
              onFocus={key === "traffic" ? warmUpTraffic : undefined}
              style={{ ...(mapView === key ? btn.primary : btn.ghost), padding: "7px 14px", fontSize: 12.5 }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {trafficOpened && (
        <div style={{ display: mapView === "traffic" ? "block" : "none", marginBottom: 0 }}>
          <Suspense fallback={<Spinner />}>
            <TrafficMap routes={myRoute} buses={myBus} height={mapHeight} showRoutesInitially />
          </Suspense>
        </div>
      )}

      {/* Map */}
      <div style={{
        display: mapView === "bus" ? "block" : "none",
        position: "relative",
        height: mapHeight,
        minHeight: 280,
        borderRadius: 12,
        border: `1px solid ${colors.borderLight}`,
        overflow: "hidden",
      }}>
        <div
          ref={mapContainer}
          style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, borderRadius: 12 }}
        />
        <div style={{ position: "absolute", top: 12, left: 12, zIndex: 2, background: "rgba(255,255,255,0.96)", borderRadius: 8, padding: "8px 10px", boxShadow: "0 1px 5px rgba(0,0,0,0.2)", fontSize: 12 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer", fontWeight: 600 }}>
            <input type="checkbox" checked={crimeRiskEnabled} onChange={(e) => setCrimeRiskEnabled(e.target.checked)} />
            Reported-crime risk
          </label>
          {crimeRiskEnabled && <div style={{ display: "flex", gap: 7, marginTop: 7, color: "#555", fontSize: 10 }}>
            <span><i style={{ display: "inline-block", width: 9, height: 9, background: "#FDE047", marginRight: 3 }} />Low</span>
            <span><i style={{ display: "inline-block", width: 9, height: 9, background: "#F59E0B", marginRight: 3 }} />Elevated</span>
            <span><i style={{ display: "inline-block", width: 9, height: 9, background: "#DC2626", marginRight: 3 }} />High</span>
          </div>}
        </div>
        <TrafficLegend traffic={traffic} visible={trafficShown} onToggle={setTrafficShown} onOpenLive={() => chooseMapView("traffic")} style={{ bottom: 30 }}
          compact={isMobile} // one row on phones, so the legend does not cover half the map
          mapbox={{ on: mapboxOn, onChange: (on) => { setMapboxOn(on); rememberMapboxTraffic(on); } }} />
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

      {crimeRiskStatus && <p style={{ fontSize: 12, color: colors.textMuted, marginTop: 8 }}>{crimeRiskStatus}</p>}


<p style={{ fontSize: 13, color: colors.textSecondary, marginTop: 10, lineHeight: 1.5 }}>
        {(() => {
          const mine = trackingData?.stops?.find((stop) => stop.name === trackingData.student_stop_name);
          const walk = mine ? walkLabel(mine.walk_m) : "";
          if (!mine) return "Numbered pins are stops in pickup order. The bus position updates every 8 seconds.";
          return walk
            ? `Your stop, ${mine.name}, is marked in amber. ${walk}, shown as the dashed line.`
            : `Your stop, ${mine.name}, is marked in amber. The bus stops right there.`;
        })()}
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
