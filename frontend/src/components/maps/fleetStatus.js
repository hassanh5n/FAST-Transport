// How a bus's tracker status is shown, shared by the fleet and traffic maps.

export function statusColor(status) {
  if (status === "live" || status === "ping") return "#16a34a"; // ping: live from the driver's phone
  if (status === "stale" || status === "last_known") return "#d97706";
  if (status === "no_tracker") return "#64748b";
  return "#dc2626";
}

export function statusLabel(bus) {
  if (bus.status === "live") return "Live";
  if (bus.status === "stale") return "Stale";
  if (bus.status === "no_tracker") return "No tracker";
  if (bus.status === "ping") return "Driver's phone";
  if (bus.status === "last_known") return `Last seen ${ageLabel(bus.position_age_seconds)}`;
  return "Offline";
}

// "just now", "4 min ago", "2 h 5 min ago"
export function ageLabel(seconds) {
  if (seconds == null) return "";
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h${minutes % 60 ? ` ${minutes % 60} min` : ""} ago`;
}

export function formatUpdated(value) {
  return value ? new Date(value).toLocaleTimeString() : "No position";
}
