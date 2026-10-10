// FAST NUCES Karachi Main Campus: where the stop maps open, and the badge that marks it.
import maplibregl from "maplibre-gl";

export const CAMPUS = {
  name: "FAST NUCES Karachi Main Campus",
  center: [67.2646384, 24.8569128], // [lng, lat], from OpenStreetMap
  zoom: 11,
};

export function addCampusMarker(map) {
  // A labelled amber tag with a pointer, so the campus stands out from the round stop pins.
  const element = document.createElement("div");
  element.title = CAMPUS.name;
  element.setAttribute("aria-label", CAMPUS.name);
  element.style.cssText = "display:flex;flex-direction:column;align-items:center;filter:drop-shadow(0 2px 5px rgba(11,45,66,0.45));";
  element.innerHTML =
    '<div style="display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:#f59e0b;border:2px solid #fff;color:#0b2d42;font:700 12px/1 system-ui,sans-serif;white-space:nowrap;">' +
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>' +
    "FAST NUCES</div>" +
    '<div style="width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-top:9px solid #f59e0b;margin-top:-2px;"></div>';
  const marker = new maplibregl.Marker({ element, anchor: "bottom" }).setLngLat(CAMPUS.center).addTo(map);
  element.style.zIndex = "1";
  return marker;
}
