import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CAMPUS, MAP_STYLE, addCampusMarker, escapeHtml, networkWidth } from "./campus";
import { routeColors } from "./routeColors";
import { formatUpdated, statusColor, statusLabel } from "./fleetStatus";
import { rememberMapboxTraffic, savedMapboxTraffic, setMapboxTraffic } from "./mapboxTraffic";
import { MapboxTrafficToggle } from "./TrafficControls";
import Icon from "../Icon";
import "./LiveFleetMap.css";
import { colors } from "../../theme";


function routeFeatures(routes) {
  const colors = routeColors(routes);
  return routes.flatMap((route) => {
    const coordinates = route.geometry?.coordinates || (route.stops || []).map((stop) => [stop.longitude, stop.latitude]);
    if (coordinates.length < 2) return [];
    return [{
      type: "Feature",
      properties: { name: route.name, color: colors.get(route.id) },
      geometry: { type: "LineString", coordinates },
    }];
  });
}

export default function LiveFleetMap({ routes = [], buses = [], height = 520, onBusSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef(new Map());
  const fittedRef = useRef(false);
  const initialRoutesRef = useRef(routes);
  const [ready, setReady] = useState(false);
  const [mapboxOn, setMapboxOn] = useState(savedMapboxTraffic);

  useEffect(() => {
    const markers = markersRef.current;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: CAMPUS.center,
      zoom: CAMPUS.zoom,
    });
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));
    map.on("load", () => {
      map.addSource("fleet-routes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      // Thin and a little faded: the buses are the subject here.
      map.addLayer({ id: "fleet-routes", type: "line", source: "fleet-routes", paint: { "line-color": ["get", "color"], "line-width": networkWidth(0.4), "line-opacity": 0.6 }, layout: { "line-join": "round", "line-cap": "round" } });
      mapRef.current = map;
      map.getSource("fleet-routes").setData({ type: "FeatureCollection", features: routeFeatures(initialRoutesRef.current) });
      setReady(true);
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
        bounds.extend(CAMPUS.center); // keep the campus in frame with the buses
        map.fitBounds(bounds, { padding: 50, maxZoom: 13, duration: 0 });
        fittedRef.current = true;
      }
    }
  }, [buses, onBusSelect]);

  useEffect(() => {
    if (ready && mapRef.current) setMapboxTraffic(mapRef.current, mapboxOn);
  }, [ready, mapboxOn]);

  // A bus picked in the list: fly to it and open its popup.
  const pickBus = (bus) => {
    const map = mapRef.current;
    const marker = markersRef.current.get(bus.bus_id);
    if (map && marker) {
      map.flyTo({ center: marker.getLngLat(), zoom: Math.max(map.getZoom(), 13.5), duration: 700 });
      if (!marker.getPopup()?.isOpen()) marker.togglePopup();
    }
    onBusSelect?.(bus.bus_id);
  };

  return (
    <div>
      <div style={{ position: "relative" }}>
        <div ref={containerRef} style={{ height, width: "100%", borderRadius: 10, overflow: "hidden" }} aria-label="Live fleet map" />
        <div style={{ position: "absolute", top: 10, left: 10, zIndex: 2, background: "rgba(255,255,255,0.97)", borderRadius: 8, padding: "7px 10px", boxShadow: "0 1px 5px rgba(11,45,66,0.2)", fontSize: 12 }}>
          <MapboxTrafficToggle on={mapboxOn} onChange={(on) => { setMapboxOn(on); rememberMapboxTraffic(on); }} />
        </div>
      </div>
      <BusList buses={buses} onPick={pickBus} />
    </div>
  );
}

// Live first, then last known, stale, offline, and buses with no tracker at all.
const STATUS_ORDER = ["live", "ping", "stale", "offline", "no_tracker"];
const FILTERS = [["all", "All"], ["live", "Live"], ["ping", "Last known"], ["stale", "Stale"], ["offline", "Offline"], ["no_tracker", "No tracker"]];
const rank = (status) => { const i = STATUS_ORDER.indexOf(status); return i === -1 ? STATUS_ORDER.length : i; };

function BusList({ buses, onPick }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const counts = buses.reduce((all, bus) => ({ ...all, [bus.status]: (all[bus.status] || 0) + 1 }), { all: buses.length });
  const query = search.trim().toLowerCase();
  const shown = buses
    .filter((bus) => filter === "all" || bus.status === filter)
    .filter((bus) => !query || [bus.bus_number, bus.route?.name, bus.driver?.name].some((text) => text?.toLowerCase().includes(query)))
    .sort((a, b) => rank(a.status) - rank(b.status) || String(a.bus_number).localeCompare(String(b.bus_number), undefined, { numeric: true }));

  return (
    <div className="fleet-list">
      <div className="fleet-list-head">
        <div role="group" aria-label="Show buses" style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          {FILTERS.map(([key, label]) => (
            <button
              key={key} type="button" className="fleet-chip" aria-pressed={filter === key}
              onClick={() => setFilter(key)} disabled={key !== "all" && !counts[key]}
            >
              {key !== "all" && <i className="fleet-dot" style={{ background: statusColor(key) }} />}
              {label} <span className="fleet-chip-n">{counts[key] || 0}</span>
            </button>
          ))}
        </div>
        <label className="fleet-search">
          <Icon name="search" size={13} color={colors.textMuted} />
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Bus, route or driver" aria-label="Search buses" />
        </label>
      </div>
      {shown.length ? (
        <ul className="fleet-rows">
          {shown.map((bus) => {
            const located = bus.latitude != null && bus.longitude != null;
            return (
              <li key={bus.bus_id}>
                <button
                  type="button" className="fleet-row" disabled={!located} onClick={() => onPick(bus)}
                  title={located ? `Show ${bus.bus_number} on the map` : `${bus.bus_number} has no position to show`}
                >
                  <i className="fleet-dot" style={{ background: statusColor(bus.status) }} aria-hidden="true" />
                  <span className="fleet-bus">{bus.bus_number}</span>
                  <span className="fleet-who">
                    {bus.route?.name || "Unassigned"} · {bus.driver?.name || "No driver"}
                    {bus.is_off_route && <span style={{ color: colors.dangerText, fontWeight: 600 }}> · Off route</span>}
                  </span>
                  <span className="fleet-when">
                    <span style={{ color: statusColor(bus.status), fontWeight: 600 }}>{statusLabel(bus)}</span>
                    {located && <span style={{ color: colors.textMuted }}> · {formatUpdated(bus.position_timestamp)}</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="fleet-empty">{query ? `No bus, route or driver matches “${search}”.` : "No buses in this view."}</p>
      )}
    </div>
  );
}
