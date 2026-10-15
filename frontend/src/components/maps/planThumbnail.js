// Map picture of a route plan, for its card. Drawn once on a hidden map, then kept in
// localStorage under the plan's fingerprint, so a card only redraws when its routes change.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CAMPUS, MAP_STYLE } from "./campus";
import { ROUTE_COLORS } from "./routeColors";

const WIDTH = 640;
const HEIGHT = 360;
const TIMEOUT_MS = 20000;
const KEY = "routeplan.thumb.";

export function cachedThumbnail(plan) {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY + plan.id) || "null");
    return saved && saved.v === plan.fingerprint ? saved.img : null;
  } catch {
    return null;
  }
}

/** Drops pictures of plans that no longer exist. */
export function pruneThumbnails(plans) {
  try {
    const keep = new Set(plans.map((plan) => KEY + plan.id));
    Object.keys(localStorage).filter((key) => key.startsWith(KEY) && !keep.has(key)).forEach((key) => localStorage.removeItem(key));
  } catch { /* storage unavailable: nothing to prune */ }
}

function features(routes) {
  const lines = [];
  const stops = [];
  routes.forEach((route, index) => {
    const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
    const points = route.stops.map((stop) => [Number(stop.longitude), Number(stop.latitude)]);
    // Imported plans may have no road geometry yet; stop-to-stop lines still show the shape.
    const coordinates = route.geometry?.coordinates?.length > 1 ? route.geometry.coordinates : points;
    if (coordinates.length > 1) lines.push({ type: "Feature", properties: { color }, geometry: { type: "LineString", coordinates } });
    points.forEach((point) => stops.push({ type: "Feature", properties: { color }, geometry: { type: "Point", coordinates: point } }));
  });
  return { lines, stops };
}

function draw(routes) {
  return new Promise((resolve, reject) => {
    const container = document.createElement("div");
    // Off-screen but laid out: a display:none map has no size to render into.
    container.style.cssText = `position:fixed;left:-10000px;top:0;width:${WIDTH}px;height:${HEIGHT}px;pointer-events:none;`;
    document.body.appendChild(container);
    const map = new maplibregl.Map({
      container,
      style: MAP_STYLE,
      center: CAMPUS.center,
      zoom: CAMPUS.zoom,
      interactive: false,
      attributionControl: false, // the card shows the credit instead
      pixelRatio: 1,
      fadeDuration: 0,
    });
    const finish = (settle, value) => {
      clearTimeout(timer);
      map.remove();
      container.remove();
      settle(value);
    };
    const timer = setTimeout(() => finish(reject, new Error("The map took too long to draw.")), TIMEOUT_MS);
    map.on("error", () => {}); // a missing tile or glyph must not abort the picture
    map.on("load", () => {
      const { lines, stops } = features(routes);
      const collection = (list) => ({ type: "FeatureCollection", features: list });
      const round = { "line-join": "round", "line-cap": "round" };
      map.addSource("lines", { type: "geojson", data: collection(lines) });
      map.addLayer({ id: "casing", type: "line", source: "lines", paint: { "line-color": "#fff", "line-width": 7 }, layout: round });
      map.addLayer({ id: "lines", type: "line", source: "lines", paint: { "line-color": ["get", "color"], "line-width": 4 }, layout: round });
      map.addSource("stops", { type: "geojson", data: collection(stops) });
      map.addLayer({ id: "stops", type: "circle", source: "stops", paint: { "circle-radius": 5, "circle-color": ["get", "color"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      map.addSource("campus", { type: "geojson", data: collection([{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: CAMPUS.center } }]) });
      map.addLayer({ id: "campus", type: "circle", source: "campus", paint: { "circle-radius": 7, "circle-color": "#f59e0b", "circle-stroke-color": "#fff", "circle-stroke-width": 2.5 } });

      const points = stops.map((stop) => stop.geometry.coordinates);
      if (points.length) {
        const bounds = points.reduce((box, point) => box.extend(point), new maplibregl.LngLatBounds(CAMPUS.center, CAMPUS.center));
        map.fitBounds(bounds, { padding: 44, maxZoom: 13, duration: 0 });
      }
      // The WebGL buffer is only readable during a render, so capture inside one once tiles settle.
      map.once("idle", () => {
        map.once("render", () => {
          try {
            finish(resolve, map.getCanvas().toDataURL("image/jpeg", 0.8));
          } catch (err) {
            finish(reject, err);
          }
        });
        map.triggerRepaint();
      });
    });
  });
}

let queue = Promise.resolve(); // one hidden map at a time: browsers cap live WebGL contexts

/** Resolves to a JPEG data URL of the plan's routes. `loadRoutes` fetches them only on a cache miss. */
export function planThumbnail(plan, loadRoutes) {
  const job = queue.then(async () => {
    const cached = cachedThumbnail(plan);
    if (cached) return cached;
    const img = await draw(await loadRoutes());
    try {
      localStorage.setItem(KEY + plan.id, JSON.stringify({ v: plan.fingerprint, img }));
    } catch { /* storage full or blocked: the picture is simply redrawn next visit */ }
    return img;
  });
  queue = job.catch(() => {});
  return job;
}
