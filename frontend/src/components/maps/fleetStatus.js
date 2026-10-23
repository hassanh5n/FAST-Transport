// How a bus's tracker status is shown, shared by the fleet and traffic maps.

export function statusColor(status) {
  if (status === "live") return "#16a34a";
  if (status === "stale" || status === "ping") return "#d97706";
  if (status === "no_tracker") return "#64748b";
  return "#dc2626";
}

export function statusLabel(bus) {
  if (bus.status === "live") return "Live";
  if (bus.status === "stale") return "Stale";
  if (bus.status === "no_tracker") return "No tracker";
  if (bus.status === "ping") return "Last known";
  return "Offline";
}

export function formatUpdated(value) {
  return value ? new Date(value).toLocaleTimeString() : "No position";
}
