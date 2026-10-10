// Shared drawing helpers for incident reports on the student and admin maps.

export const SEVERITY_COLORS = { low: "#F59E0B", medium: "#F97316", high: "#EF4444" };
export const REJECTED_COLOR = "#94a3b8";

// Rejected reports are greyed out; everything else is coloured by severity.
export const incidentColor = (incident) =>
  incident.status === "Rejected" ? REJECTED_COLOR : SEVERITY_COLORS[incident.severity] || SEVERITY_COLORS.low;

/** A closed ring of [lng, lat] points approximating a circle of `radiusM` metres. */
export function circleRing(lng, lat, radiusM, steps = 64) {
  const dLat = (radiusM / 6371000) * (180 / Math.PI);
  const dLng = dLat / Math.cos((lat * Math.PI) / 180);
  const ring = [];
  for (let i = 0; i <= steps; i += 1) {
    const angle = (i / steps) * 2 * Math.PI;
    ring.push([lng + dLng * Math.sin(angle), lat + dLat * Math.cos(angle)]);
  }
  return ring;
}
