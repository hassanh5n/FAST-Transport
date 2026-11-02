// frontend/src/utils/transportStatus.js
// Site user vs transport user. The backend decides (transport_status.py); this is
// only for labels and for hiding pages a passenger cannot use yet.
//
//   none        – site account only, not registered for transport this semester
//   applying    – registered this semester, not confirmed yet (pending, seat held, waitlisted…)
//   registered  – confirmed transport user for this semester
//
// A semester ending turns "registered" back into "none" on the server, so the
// stored value is refreshed with the session on every page load (PageShell), and
// by refreshTransportStatus() right after anything that changes it.

import { getUser } from "../services/transportService";
import { storeUserSession } from "./permissions";

export const TRANSPORT_STATUS = {
  none:       { label: "Site user",      variant: "neutral" },
  applying:   { label: "Applying",       variant: "warning" },
  registered: { label: "Transport user", variant: "success" },
};

export function transportStatusMeta(status) {
  return TRANSPORT_STATUS[status] || TRANSPORT_STATUS.none;
}

// The signed-in passenger's status, as stored by storeUserSession().
export function transportStatus() {
  return localStorage.getItem("transport_status") || "none";
}

// Which statuses may open a passenger page; pages not listed are open to everyone.
const PAGE_ACCESS = {
  "/student/transport":               ["applying", "registered"],
  "/student/challan":                 ["applying", "registered"],
  "/student/route-change":            ["registered"],
  "/student/map":                     ["registered"],
  "/student/incidents":               ["registered"],
  "/student/transport-registrations": ["none", "applying"],
};

export function canOpenPassengerPage(path, status = transportStatus()) {
  const allowed = PAGE_ACCESS[path];
  return !allowed || allowed.includes(status);
}

// Re-read the status from the server: after registering, paying or cancelling,
// and before turning a passenger away from a page. Never rejects.
export function refreshTransportStatus() {
  return getUser().then((res) => storeUserSession(res.data)).catch(() => {});
}
