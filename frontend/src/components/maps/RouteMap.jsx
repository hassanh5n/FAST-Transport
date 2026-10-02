import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const DEFAULT_CENTER = [67.0847, 24.9215];
const ROUTE_COLORS = ["#2563EB", "#DC2626", "#16A34A", "#9333EA", "#EA580C", "#0891B2", "#BE123C"];

const colorFor = (id) => {
  const numericId = Number(id);
  return ROUTE_COLORS[Number.isFinite(numericId) ? Math.abs(numericId) % ROUTE_COLORS.length : 0];
};

function makeFeatures(routes) {
  const lines = [];
  const stops = [];
  routes.forEach((route) => {
    const color = colorFor(route.id);
    const coordinates = route.geometry?.coordinates || route.stops.map((stop) => [stop.longitude, stop.latitude]);
    if (coordinates.length > 1) {
      lines.push({
        type: "Feature",
        properties: { routeId: route.id, name: route.name, color },
        geometry: { type: "LineString", coordinates },
      });
    }
    route.stops.forEach((stop) => {
      stops.push({
        type: "Feature",
        properties: {
          routeId: route.id, routeStopId: stop.route_stop_id, name: stop.name,
          address: stop.address || "", stopOrder: stop.stop_order, color,
          morningEta: stop.morning_eta || "", eveningEta: stop.evening_eta || "",
        },
        geometry: { type: "Point", coordinates: [Number(stop.longitude), Number(stop.latitude)] },
      });
    });
  });
  return {
    routes: { type: "FeatureCollection", features: lines },
    stops: { type: "FeatureCollection", features: stops },
  };
}

function makeSelectedRouteFeatures(routes, selectedRouteId) {
  const selectedId = Number(selectedRouteId);
  if (!Number.isFinite(selectedId)) {
    return { routes: { type: "FeatureCollection", features: [] }, stops: { type: "FeatureCollection", features: [] } };
  }
  const route = routes.find((item) => Number(item.id) === selectedId);
  if (!route) {
    return { routes: { type: "FeatureCollection", features: [] }, stops: { type: "FeatureCollection", features: [] } };
  }
  const color = colorFor(route.id);
  const coordinates = route.geometry?.coordinates || route.stops.map((stop) => [stop.longitude, stop.latitude]);
  const lines = coordinates.length > 1 ? [{
    type: "Feature",
    properties: { routeId: route.id, name: route.name, color },
    geometry: { type: "LineString", coordinates },
  }] : [];
  const stops = route.stops.map((stop) => ({
    type: "Feature",
    properties: {
      routeId: route.id, routeStopId: stop.route_stop_id, name: stop.name,
      address: stop.address || "", stopOrder: stop.stop_order, color,
      morningEta: stop.morning_eta || "", eveningEta: stop.evening_eta || "",
    },
    geometry: { type: "Point", coordinates: [Number(stop.longitude), Number(stop.latitude)] },
  }));
  return {
    routes: { type: "FeatureCollection", features: lines },
    stops: { type: "FeatureCollection", features: stops },
  };
}

// White bus glyph for the live-position marker (same shape as the dashboard bus icon).
const BUS_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6v6"/><path d="M16 6v6"/><path d="M2 12h20"/><path d="M18 18h2a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/><circle cx="8" cy="18" r="2"/><circle cx="16" cy="18" r="2"/></svg>';

export default function RouteMap({ routes = [], selectedRouteId, onRouteSelect, onStopSelect, height = 480, livePosition = null }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const liveMarkerRef = useRef(null);
  const callbackRef = useRef({ onRouteSelect, onStopSelect });

  useEffect(() => {
    callbackRef.current = { onRouteSelect, onStopSelect };
  }, [onRouteSelect, onStopSelect]);

  useEffect(() => {
    if (mapRef.current) return undefined;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: DEFAULT_CENTER,
      zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));
    map.on("load", () => {
      map.addSource("network-routes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "network-route-casing", type: "line", source: "network-routes", paint: { "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.9 }, layout: { "line-join": "round", "line-cap": "round" } });
      map.addLayer({ id: "network-routes", type: "line", source: "network-routes", paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.75 }, layout: { "line-join": "round", "line-cap": "round" } });
      map.addSource("network-stops", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "network-stops", type: "circle", source: "network-stops", paint: { "circle-radius": 7, "circle-color": ["get", "color"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      map.addLayer({ id: "network-stop-numbers", type: "symbol", source: "network-stops", layout: { "text-field": ["get", "stopOrder"], "text-size": 10, "text-allow-overlap": true }, paint: { "text-color": "#fff", "text-halo-color": "#111827", "text-halo-width": 1.25 } });

      map.addSource("selected-route-lines", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "selected-route-casing", type: "line", source: "selected-route-lines", paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 1 }, layout: { "line-join": "round", "line-cap": "round" } });
      map.addLayer({ id: "selected-route-lines", type: "line", source: "selected-route-lines", paint: { "line-color": ["get", "color"], "line-width": 6, "line-opacity": 1 }, layout: { "line-join": "round", "line-cap": "round" } });
      map.addSource("selected-route-stops", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "selected-route-stops", type: "circle", source: "selected-route-stops", paint: { "circle-radius": 9, "circle-color": ["get", "color"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      map.addLayer({ id: "selected-route-stop-numbers", type: "symbol", source: "selected-route-stops", layout: { "text-field": ["get", "stopOrder"], "text-size": 12, "text-font": ["Open Sans Bold"], "text-allow-overlap": true }, paint: { "text-color": "#ffffff", "text-halo-color": "#0f172a", "text-halo-width": 2 } });

      const showStopPopup = (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties;
        const etaHtml = [
          props.morningEta ? `<div><strong>Morning ETA:</strong> ${props.morningEta}</div>` : "",
          props.eveningEta ? `<div><strong>Evening ETA:</strong> ${props.eveningEta}</div>` : "",
        ].filter(Boolean).join("");
        const content = `
          <div style="font-size:12px; line-height:1.5; color:#1f2937; min-width:180px;">
            <div style="font-weight:700; font-size:13px; margin-bottom:4px;">${props.name || "Stop"}</div>
            ${props.address ? `<div>${props.address}</div>` : ""}
            ${etaHtml ? `<div style="margin-top:6px;">${etaHtml}</div>` : "<div style=\"margin-top:6px; color:#6b7280;\">No ETA added</div>"}
          </div>
        `;
        if (!popupRef.current) {
          popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });
        }
        popupRef.current
          .setLngLat(event.lngLat)
          .setHTML(content)
          .addTo(map);
      };

      const hideStopPopup = () => {
        popupRef.current?.remove();
      };

      map.on("click", "network-routes", (event) => {
        const feature = event.features?.[0];
        if (feature) callbackRef.current.onRouteSelect?.(Number(feature.properties.routeId));
      });
      map.on("click", "network-stops", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        callbackRef.current.onRouteSelect?.(Number(feature.properties.routeId));
        callbackRef.current.onStopSelect?.({ ...feature.properties, coordinates: feature.geometry.coordinates });
      });
      map.on("mousemove", "network-stops", showStopPopup);
      map.on("mouseleave", "network-stops", hideStopPopup);
      ["network-routes", "network-stops"].forEach((layer) => {
        map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; hideStopPopup(); });
      });
    });
    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      liveMarkerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const features = makeFeatures(routes);
      const selectedFeatures = makeSelectedRouteFeatures(routes, selectedRouteId);
      map.getSource("network-routes")?.setData(features.routes);
      map.getSource("network-stops")?.setData(features.stops);
      map.getSource("selected-route-lines")?.setData(selectedFeatures.routes);
      map.getSource("selected-route-stops")?.setData(selectedFeatures.stops);
      const allCoordinates = features.stops.features.map((feature) => feature.geometry.coordinates);
      if (allCoordinates.length) {
        const bounds = allCoordinates.reduce((result, point) => result.extend(point), new maplibregl.LngLatBounds(allCoordinates[0], allCoordinates[0]));
        map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 0 });
      }
    };
    if (map.isStyleLoaded()) update(); else map.once("load", update);
  }, [routes, selectedRouteId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const selectedId = Number(selectedRouteId);
    const hasSelected = Number.isFinite(selectedId);
    map.setLayoutProperty("selected-route-lines", "visibility", hasSelected ? "visible" : "none");
    map.setLayoutProperty("selected-route-casing", "visibility", hasSelected ? "visible" : "none");
    map.setLayoutProperty("selected-route-stops", "visibility", hasSelected ? "visible" : "none");
    map.setLayoutProperty("selected-route-stop-numbers", "visibility", hasSelected ? "visible" : "none");
    map.setPaintProperty(
      "network-routes",
      "line-width",
      hasSelected ? ["case", ["==", ["get", "routeId"], selectedId], 6, 4] : 4
    );
  }, [selectedRouteId]);

  // Live bus position (driver pages) — one marker, moved in place.
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
    el.style.cssText = "width:34px;height:34px;border-radius:50%;background:#0b2d42;border:3px solid #fff;"
      + "box-shadow:0 0 0 6px rgba(40,141,196,0.22),0 3px 10px rgba(11,45,66,0.45);"
      + "display:flex;align-items:center;justify-content:center;";
    el.innerHTML = BUS_SVG;
    liveMarkerRef.current = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(lngLat).addTo(map);
  }, [liveLat, liveLng]);

  return <div ref={containerRef} style={{ height, width: "100%", borderRadius: 12, overflow: "hidden" }} aria-label="Transport route map" />;
}