// Shared look for every map: the campus badge, base style, line widths and colours.
import maplibregl from "maplibre-gl";
import { CAMPUS } from "./campusLocation";

export { CAMPUS };

// One accent for the route being looked at; every other route is drawn in ink, so
// the network reads as coverage and shared corridors darken where routes overlap.
export const MAP_COLORS = {
  ink: "#1a4a68",       // the network
  inkHover: "#0f3a55",  // a network route under the pointer
  accent: "#288dc4",    // the selected route
  casing: "#ffffff",
  pin: "#0b2d42",       // stop pin ring and number
  walk: "#4a6178",      // dashed walk from a stop to where the bus picks up
  yours: "#f59e0b",     // the signed-in student's own stop
};

// Below this zoom the network shows lines only: 300+ stop pins at city scale are noise.
export const STOPS_MIN_ZOOM = 11.5;

export function addCampusMarker(map) {
  const element = document.createElement("div");
  element.title = CAMPUS.name;
  element.setAttribute("aria-label", CAMPUS.name);
  element.style.cssText = "display:flex;flex-direction:column;align-items:center;filter:drop-shadow(0 2px 4px rgba(11,45,66,0.35));";
  element.innerHTML =
    `<div style="display:flex;align-items:center;gap:5px;padding:4px 9px 4px 7px;border-radius:999px;background:${MAP_COLORS.pin};border:2px solid #fff;color:#fff;font:600 11px/1 'DM Sans',system-ui,sans-serif;white-space:nowrap;">` +
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>' +
    "FAST NUCES</div>" +
    `<div style="width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:7px solid ${MAP_COLORS.pin};margin-top:-1px;"></div>`;
  const marker = new maplibregl.Marker({ element, anchor: "bottom" }).setLngLat(CAMPUS.center).addTo(map);
  element.style.zIndex = "1";
  return marker;
}

// The base map on every page: OpenFreeMap's light style, so the routes stand out.
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

// Route line width that grows as you zoom in; `extra` thickens a casing or a selected line.
export const routeWidth = (extra = 0) => [
  "interpolate", ["exponential", 1.5], ["zoom"], 10, 2.5 + extra, 14, 5 + extra, 17, 10 + extra,
];

// The thin network line: present but quiet.
export const networkWidth = (extra = 0) => [
  "interpolate", ["exponential", 1.5], ["zoom"], 9, 1 + extra, 12, 1.8 + extra, 15, 3.5 + extra, 17, 6 + extra,
];

// White chevrons along a line source, pointing the way the bus drives (stop order).
export function addRouteArrows(map, id, source, minzoom = 12) {
  map.addLayer({
    id, type: "symbol", source, minzoom,
    layout: {
      "symbol-placement": "line", "symbol-spacing": 110,
      "text-field": "›", "text-font": ["Noto Sans Bold"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 12, 13, 17, 20],
      "text-keep-upright": false, "text-rotation-alignment": "map",
      "text-allow-overlap": true, "text-ignore-placement": true,
    },
    paint: { "text-color": "#ffffff" },
  });
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

// "07:05:00" -> "7:05 am"
export function clockLabel(value) {
  if (!value) return "";
  const [hours, minutes] = String(value).split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return "";
  const suffix = hours < 12 ? "am" : "pm";
  return `${((hours + 11) % 12) + 1}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

// "Walk 320 m to the main road" for a stop the bus does not drive up to.
export const WALK_SHOWN_FROM_M = 40;
export function walkLabel(walkM) {
  const metres = Number(walkM) || 0;
  if (metres < WALK_SHOWN_FROM_M) return "";
  const rounded = metres < 100 ? Math.round(metres / 10) * 10 : Math.round(metres / 50) * 50;
  return `Walk ${rounded} m to the pickup point on the main road`;
}

// Popup body shared by the route maps.
export function stopPopupHtml({ name, morningEta, eveningEta, walkM, isYours = false }) {
  const rows = [
    morningEta ? `<div>Morning pickup <strong>${escapeHtml(clockLabel(morningEta))}</strong></div>` : "",
    eveningEta ? `<div>Evening drop-off <strong>${escapeHtml(clockLabel(eveningEta))}</strong></div>` : "",
  ].join("");
  const walk = walkLabel(walkM);
  return `
    <div style="font:13px/1.45 'DM Sans',system-ui,sans-serif;color:#0f1f2d;min-width:190px;max-width:240px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:3px;">${escapeHtml(name || "Stop")}</div>
      ${isYours ? `<div style="color:#92650a;font-weight:600;margin-bottom:3px;">Your stop</div>` : ""}
      ${rows || '<div style="color:#8faabb;">No time set</div>'}
      ${walk ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e2e8f0;color:#4a6178;">${escapeHtml(walk)}</div>` : ""}
    </div>`;
}
