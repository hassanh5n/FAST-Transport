// Small helpers shared by the passenger console, My Transport and Register pages.

// Mirrors Semester.accepts_registrations on the backend: the flag is on, the
// semester is active, and the admin-set deadline (if any) has not passed.
export function acceptsRegistrations(semester) {
  if (!semester?.is_active || !semester?.registration_open) return false;
  if (!semester.registration_deadline) return true;
  return new Date(semester.registration_deadline).getTime() > Date.now();
}

export function openSemesters(semesters) {
  return (Array.isArray(semesters) ? semesters : []).filter(acceptsRegistrations);
}

// Faculty accounts have no roll number. user_type comes from the dashboard
// API; the roll-number check covers older backends that do not send it.
export function isFacultyProfile(profile) {
  if (!profile) return false;
  if (profile.user_type) return profile.user_type === "Faculty";
  return !profile.roll_number;
}

export function feeFor(semester, profile) {
  if (!semester) return null;
  const amount = isFacultyProfile(profile) ? semester.faculty_transport_fee : semester.transport_fee;
  return amount ?? null;
}

export function formatPKR(amount) {
  if (amount === null || amount === undefined || amount === "") return "—";
  const n = Number(amount);
  return Number.isFinite(n) ? `PKR ${n.toLocaleString()}` : `PKR ${amount}`;
}

export function formatDate(value, withTime = false) {
  if (!value) return null;
  return new Date(value).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function fullName(profile) {
  return `${profile?.first_name || ""} ${profile?.last_name || ""}`.trim();
}

// "23K-0769 · CS · Batch 2023" for students, "Faculty · CS" for faculty.
// Skips the "N/A" placeholders the profile model defaults to.
export function profileMeta(profile) {
  const real = (v) => v && v !== "N/A";
  const parts = isFacultyProfile(profile)
    ? ["Faculty", profile?.department]
    : [profile?.roll_number, profile?.department, real(profile?.batch) ? `Batch ${profile.batch}` : null];
  return parts.filter(real).join(" · ");
}

// The four steps every passenger goes through, in order.
export const REGISTRATION_STEPS = [
  { title: "Pick your stop", text: "Choose the semester and the pickup stop closest to you." },
  { title: "Get a route", text: "You are placed on the route that serves that stop, or queued if it is full." },
  { title: "Pay the fee", text: "Pay the transport fee using the challan issued with your seat." },
  { title: "Ride", text: "The transport office verifies payment and confirms your seat." },
];
