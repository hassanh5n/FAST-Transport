// The route network and one route in detail.
//
// Network: every route as a thin ink line (lines only at city zoom; small stop dots
// once zoomed in). Hovering a line names it. Selected route: the accent line with
// numbered stop pins at the real stop locations and, where a stop is off the main
// road, a dashed walk to the pickup point on the line.
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  CAMPUS, MAP_COLORS, MAP_STYLE, STOPS_MIN_ZOOM, WALK_SHOWN_FROM_M,
  addCampusMarker, addRouteArrows, escapeHtml, networkWidth, routeWidth, stopPopupHtml,
} from "./campus";

const EMPTY = { type: "FeatureCollection", features: [] };
const collection = (features) => ({ type: "FeatureCollection", features });

const pinOf = (stop) => [Number(stop.longitude), Number(stop.latitude)];

// Where the bus picks this stop up: from the API, or from a route preview's geometry.
function boardingOf(route, stop, index) {
  if (Array.isArray(stop.boarding)) return { at: stop.boarding.map(Number), walk: Number(stop.walk_m) || 0 };
  const saved = route.geometry?.stops;
  if (Array.isArray(saved) && saved.length === route.stops.length && saved[index]?.at) {
    return { at: saved[index].at.map(Number), walk: Number(saved[index].walk_m) || 0 };
  }
  return { at: pinOf(stop), walk: 0 };
}

const lineOf = (route) => (route.geometry?.coordinates?.length > 1
  ? route.geometry.coordinates
  : route.stops.map(pinOf));

function networkFeatures(routes) {
  const lines = [];
  const stops = [];
  routes.forEach((route) => {
    const coordinates = lineOf(route);
    if (coordinates.length > 1) {
      lines.push({ type: "Feature", properties: { routeId: route.id, name: route.name }, geometry: { type: "LineString", coordinates } });
    }
    route.stops.forEach((stop, index) => {
      if (stop.is_campus) return;
      stops.push({
        type: "Feature",
        properties: {
          routeId: route.id, routeStopId: stop.route_stop_id, name: stop.name, stopOrder: stop.stop_order,
          morningEta: stop.est_morning_eta || "", eveningEta: stop.est_evening_eta || "",
          walkM: boardingOf(route, stop, index).walk, isCampus: false,
        },
        geometry: { type: "Point", coordinates: pinOf(stop) },
      });
    });
  });
  return { lines: collection(lines), stops: collection(stops) };
}

function selectedFeatures(route) {
  if (!route) return { line: EMPTY, stops: EMPTY, walks: EMPTY, pickups: EMPTY };
  const coordinates = lineOf(route);
  const stops = [];
  const walks = [];
  const pickups = [];
  let number = 0;
  route.stops.forEach((stop, index) => {
    if (stop.is_campus) return; // the campus badge marks the end of every route
    number += 1;
    const { at, walk } = boardingOf(route, stop, index);
    stops.push({
      type: "Feature",
      properties: {
        routeId: route.id, routeStopId: stop.route_stop_id, name: stop.name, number,
        morningEta: stop.est_morning_eta || "", eveningEta: stop.est_evening_eta || "", walkM: walk, isCampus: false,
      },
      geometry: { type: "Point", coordinates: pinOf(stop) },
    });
    if (walk >= WALK_SHOWN_FROM_M) {
      walks.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [pinOf(stop), at] } });
      pickups.push({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: at } });
    }
  });
  return {
    line: coordinates.length > 1 ? collection([{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } }]) : EMPTY,
    stops: collection(stops),
    walks: collection(walks),
    pickups: collection(pickups),
  };
}

function boundsOf(points) {
  if (!points.length) return null;
  const bounds = points.reduce((result, point) => result.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
  bounds.extend(CAMPUS.center); // keep the campus in frame
  return bounds;
}

// White chip with a bus glyph for the live-position marker (driver pages).
const BUS_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6v6"/><path d="M16 6v6"/><path d="M2 12h20"/><path d="M18 18h2a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/><circle cx="8" cy="18" r="2"/><circle cx="16" cy="18" r="2"/></svg>';

function Legend({ showWalk }) {
  const item = { display: "flex", alignItems: "center", gap: 7 };
  return (
    <div style={{
      position: "absolute", left: 10, bottom: 30, zIndex: 2, display: "flex", flexWrap: "wrap", gap: "6px 14px",
      background: "rgba(255,255,255,0.94)", borderRadius: 8, padding: "7px 10px", boxShadow: "0 1px 4px rgba(11,45,66,0.18)",
      font: "500 11.5px/1.2 'DM Sans', system-ui, sans-serif", color: "#4a6178", maxWidth: "calc(100% - 20px)",
    }}>
      <span style={item}>
        <svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke={MAP_COLORS.accent} strokeWidth="4" strokeLinecap="round" /></svg>
        Bus route
      </span>
      <span style={item}>
        <svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" fill="#fff" stroke={MAP_COLORS.pin} strokeWidth="2" /></svg>
        Stop
      </span>
      {showWalk && (
        <span style={item}>
          <svg width="30" height="10" aria-hidden="true">
            <line x1="1" y1="5" x2="22" y2="5" stroke={MAP_COLORS.walk} strokeWidth="2" strokeDasharray="2 3" strokeLinecap="round" />
            <circle cx="25" cy="5" r="3.2" fill="#fff" stroke={MAP_COLORS.accent} strokeWidth="2" />
          </svg>
          Walk to pickup
        </span>
      )}
    </div>
  );
}

export default function RouteMap({ routes = [], selectedRouteId, onRouteSelect, onStopSelect, height = 480, livePosition = null }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const hoverPopupRef = useRef(null);
  const liveMarkerRef = useRef(null);
  const fittedKeyRef = useRef("");
  const [ready, setReady] = useState(false);
  const [focusedId, setFocusedId] = useState(null); // a clicked route when the page does not track selection
  const callbackRef = useRef({ onRouteSelect, onStopSelect });

  useEffect(() => {
    callbackRef.current = { onRouteSelect, onStopSelect };
  }, [onRouteSelect, onStopSelect]);

  // One route on the map is always shown in detail; otherwise the page's choice,
  // or the route the user clicked when the page leaves that to the map.
  const selected = useMemo(() => {
    if (routes.length === 1) return routes[0];
    const wanted = selectedRouteId ?? (onRouteSelect ? null : focusedId);
    if (wanted == null) return null;
    return routes.find((route) => Number(route.id) === Number(wanted)) || null;
  }, [routes, selectedRouteId, focusedId, onRouteSelect]);

  useEffect(() => {
    if (mapRef.current) return undefined;
    const map = new maplibregl.Map({ container: containerRef.current, style: MAP_STYLE, center: CAMPUS.center, zoom: CAMPUS.zoom });
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 100, unit: "metric" }));
    map.on("load", () => {
      const line = { "line-join": "round", "line-cap": "round" };
      map.addSource("network-routes", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "network-routes", type: "line", source: "network-routes", layout: line, paint: { "line-color": MAP_COLORS.ink, "line-width": networkWidth(), "line-opacity": 0.4 } });
      map.addLayer({ id: "network-hit", type: "line", source: "network-routes", layout: line, paint: { "line-color": "#000", "line-width": 12, "line-opacity": 0 } });
      map.addLayer({ id: "network-hover", type: "line", source: "network-routes", layout: line, filter: ["==", ["get", "routeId"], -1], paint: { "line-color": MAP_COLORS.inkHover, "line-width": networkWidth(1.5), "line-opacity": 0.95 } });
      map.addSource("network-stops", { type: "geojson", data: EMPTY });
      map.addLayer({
        id: "network-stops", type: "circle", source: "network-stops", minzoom: STOPS_MIN_ZOOM,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], STOPS_MIN_ZOOM, 1.8, 14, 4, 16, 5.5],
          "circle-color": "#fff", "circle-stroke-color": MAP_COLORS.ink, "circle-stroke-width": 1.4,
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], STOPS_MIN_ZOOM, 0, STOPS_MIN_ZOOM + 0.5, 1],
          "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], STOPS_MIN_ZOOM, 0, STOPS_MIN_ZOOM + 0.5, 1],
        },
      });

      map.addSource("selected-line", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "selected-casing", type: "line", source: "selected-line", layout: line, paint: { "line-color": MAP_COLORS.casing, "line-width": routeWidth(3.5) } });
      map.addLayer({ id: "selected-line", type: "line", source: "selected-line", layout: line, paint: { "line-color": MAP_COLORS.accent, "line-width": routeWidth() } });
      addRouteArrows(map, "selected-arrows", "selected-line");
      map.addSource("selected-walks", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "selected-walks", type: "line", source: "selected-walks", layout: { "line-cap": "round" }, paint: { "line-color": MAP_COLORS.walk, "line-width": 2, "line-dasharray": [0.6, 2] } });
      map.addSource("selected-pickups", { type: "geojson", data: EMPTY });
      map.addLayer({ id: "selected-pickups", type: "circle", source: "selected-pickups", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.5, 15, 4.5], "circle-color": "#fff", "circle-stroke-color": MAP_COLORS.accent, "circle-stroke-width": 2 } });
      map.addSource("selected-stops", { type: "geojson", data: EMPTY });
      map.addLayer({
        id: "selected-stops", type: "circle", source: "selected-stops",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 7.5, 14, 10.5],
          "circle-color": "#fff", "circle-stroke-color": MAP_COLORS.pin, "circle-stroke-width": 2.2,
        },
      });
      map.addLayer({
        id: "selected-stop-numbers", type: "symbol", source: "selected-stops",
        layout: {
          "text-field": ["to-string", ["get", "number"]], "text-font": ["Noto Sans Bold"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 10, 9.5, 14, 12],
          "text-allow-overlap": true, "text-ignore-placement": true,
        },
        paint: { "text-color": MAP_COLORS.pin },
      });

      const showStopPopup = (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties;
        if (!popupRef.current) popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14 });
        popupRef.current
          .setLngLat(feature.geometry.coordinates)
          .setHTML(stopPopupHtml({ name: props.name, morningEta: props.morningEta, eveningEta: props.eveningEta, walkM: props.walkM }))
          .addTo(map);
      };
      const hideStopPopup = () => popupRef.current?.remove();

      const pickStop = (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties;
        callbackRef.current.onRouteSelect?.(Number(props.routeId));
        setFocusedId(Number(props.routeId));
        callbackRef.current.onStopSelect?.({ ...props, coordinates: feature.geometry.coordinates });
      };
      map.on("click", "selected-stops", pickStop);
      map.on("click", "network-stops", pickStop);
      map.on("click", "network-hit", (event) => {
        if (map.queryRenderedFeatures(event.point, { layers: ["selected-stops", "network-stops"] }).length) return;
        const feature = event.features?.[0];
        if (!feature) return;
        callbackRef.current.onRouteSelect?.(Number(feature.properties.routeId));
        setFocusedId(Number(feature.properties.routeId));
      });

      map.on("mousemove", "network-hit", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        map.getCanvas().style.cursor = "pointer";
        map.setFilter("network-hover", ["==", ["get", "routeId"], feature.properties.routeId]);
        if (!hoverPopupRef.current) hoverPopupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: "route-name-tip" });
        hoverPopupRef.current.setLngLat(event.lngLat)
          .setHTML(`<div style="font:600 12px 'DM Sans',system-ui,sans-serif;color:#0f1f2d;">${escapeHtml(feature.properties.name)}</div>`)
          .addTo(map);
      });
      map.on("mouseleave", "network-hit", () => {
        map.getCanvas().style.cursor = "";
        map.setFilter("network-hover", ["==", ["get", "routeId"], -1]);
        hoverPopupRef.current?.remove();
      });
      ["selected-stops", "network-stops"].forEach((layer) => {
        map.on("mouseenter", layer, (event) => { map.getCanvas().style.cursor = "pointer"; hoverPopupRef.current?.remove(); showStopPopup(event); });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; hideStopPopup(); });
      });
      setReady(true);
    });
    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      hoverPopupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      liveMarkerRef.current = null;
    };
  }, []);

  // Data. The network is everything except the selected route, which is drawn on top.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const others = selected && routes.length > 1 ? routes.filter((route) => route.id !== selected.id) : routes;
    const network = networkFeatures(selected && routes.length === 1 ? [] : others);
    const detail = selectedFeatures(selected);
    map.getSource("network-routes").setData(network.lines);
    map.getSource("network-stops").setData(network.stops);
    map.getSource("selected-line").setData(detail.line);
    map.getSource("selected-walks").setData(detail.walks);
    map.getSource("selected-pickups").setData(detail.pickups);
    map.getSource("selected-stops").setData(detail.stops);
    // With a route selected the rest of the network steps back.
    map.setPaintProperty("network-routes", "line-opacity", selected ? 0.16 : 0.4);
    map.setLayoutProperty("network-stops", "visibility", selected ? "none" : "visible");

    // Fit when what is shown changes, not on every refresh of the same data.
    const key = selected ? `route:${selected.id}` : `network:${routes.map((route) => route.id).join(",")}`;
    if (fittedKeyRef.current === key) return;
    const points = selected
      ? [...lineOf(selected), ...selected.stops.map(pinOf)]
      : routes.flatMap((route) => lineOf(route));
    const bounds = boundsOf(points.filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat)));
    if (!bounds) return;
    map.fitBounds(bounds, { padding: { top: 40, right: 50, bottom: 50, left: 40 }, maxZoom: selected ? 14 : 12.5, duration: fittedKeyRef.current ? 500 : 0 });
    fittedKeyRef.current = key;
  }, [routes, selected, ready]);

  // Live bus position (driver pages): one marker, moved in place.
  const liveLat = livePosition?.lat;
  const liveLng = livePosition?.lng;
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (liveLat == null || liveLng == null) {
      liveMarkerRef.current?.remove();
      liveMarkerRef.current = null;
      return;
    }
    const lngLat = [Number(liveLng), Number(liveLat)];
    if (liveMarkerRef.current) {
      liveMarkerRef.current.setLngLat(lngLat);
      return;
    }
    const el = document.createElement("div");
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", "Bus position");
    el.style.cssText = `width:32px;height:32px;border-radius:50%;background:${MAP_COLORS.pin};border:3px solid #fff;`
      + "box-shadow:0 0 0 6px rgba(40,141,196,0.22),0 3px 10px rgba(11,45,66,0.45);"
      + "display:flex;align-items:center;justify-content:center;";
    el.innerHTML = BUS_SVG;
    liveMarkerRef.current = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(lngLat).addTo(map);
  }, [liveLat, liveLng]);

  const showWalk = Boolean(selected?.stops?.some((stop, index) => boardingOf(selected, stop, index).walk >= WALK_SHOWN_FROM_M));

  return (
    <div style={{ position: "relative", height, width: "100%", borderRadius: 12, overflow: "hidden" }}>
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} aria-label="Transport route map" />
      {selected && <Legend showWalk={showWalk} />}
    </div>
  );
}
