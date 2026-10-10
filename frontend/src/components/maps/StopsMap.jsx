// Overview map of every stop: click a pin to open that stop, click empty map to add one there.
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CAMPUS, addCampusMarker } from "./campus";

const lngLatOf = (stop) => {
  const lat = Number(stop.latitude);
  const lng = Number(stop.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return [lng, lat];
};

export default function StopsMap({ stops, height = 520, highlightId = null, onStopClick, onMapClick }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const elementsRef = useRef(new Map());
  const handlersRef = useRef({ onStopClick, onMapClick });

  useEffect(() => {
    handlersRef.current = { onStopClick, onMapClick };
  }, [onStopClick, onMapClick]);

  useEffect(() => {
    const map = new maplibregl.Map({ container: containerRef.current, style: "https://tiles.openfreemap.org/styles/liberty", center: CAMPUS.center, zoom: CAMPUS.zoom });
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("click", (event) => handlersRef.current.onMapClick?.({ latitude: event.lngLat.lat.toFixed(6), longitude: event.lngLat.lng.toFixed(6) }));
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;
    const elements = elementsRef.current;
    const markers = stops.flatMap((stop) => {
      const lngLat = lngLatOf(stop);
      if (!lngLat) return [];
      const marker = new maplibregl.Marker({ color: stop.is_active === false ? "#94a3b8" : "#1976b9", scale: 0.75 }).setLngLat(lngLat).addTo(map);
      const element = marker.getElement();
      element.title = stop.is_active === false ? `${stop.name} (inactive)` : stop.name || "";
      element.style.cursor = "pointer";
      element.addEventListener("click", (event) => {
        event.stopPropagation(); // a pin click opens the stop; it must not also count as a map click
        handlersRef.current.onStopClick?.(stop);
      });
      elements.set(stop.id, element);
      return [marker];
    });
    return () => { markers.forEach((marker) => marker.remove()); elements.clear(); };
  }, [stops]);

  useEffect(() => {
    elementsRef.current.forEach((element, id) => {
      const highlighted = id === highlightId;
      element.style.filter = highlighted ? "drop-shadow(0 0 5px #c42828) saturate(2)" : "";
      element.style.zIndex = highlighted ? "2" : "0";
    });
  }, [highlightId, stops]);

  return <div ref={containerRef} style={{ height, borderRadius: 10, overflow: "hidden", border: "1px solid #dbe3ea" }} aria-label="Map of all stops" />;
}
