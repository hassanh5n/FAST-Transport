// frontend/src/utils/permissions.js
// Client-side view of the admin's role permissions.
// The backend is the real gate (AdminAccessMiddleware) — this only hides UI
// the admin can't use.

const RANK = { none: 0, view: 1, manage: 2 };

// Save the /api/user/ response after login (or a refresh).
export function storeUserSession(user) {
  localStorage.setItem("is_staff", user.is_staff ? "true" : "false");
  localStorage.setItem("is_super_admin", user.is_super_admin ? "true" : "false");
  localStorage.setItem("admin_role", user.admin_role || "");
  localStorage.setItem("permissions", JSON.stringify(user.permissions || {}));
  localStorage.setItem("username", user.username);
  localStorage.setItem("full_name", `${user.first_name || ""} ${user.last_name || ""}`.trim());
  window.dispatchEvent(new Event("app:permissions-updated"));
}

export function isSuperAdmin() {
  return localStorage.getItem("is_super_admin") === "true";
}

export function getPermissions() {
  try {
    return JSON.parse(localStorage.getItem("permissions") || "{}");
  } catch {
    return {};
  }
}

// can("complaints")            -> may view
// can("complaints", "manage")  -> may reply / edit
// can(["fees", "export"])      -> any of them
export function can(module, level = "view") {
  if (!module) return true;
  if (isSuperAdmin()) return true;
  const perms = getPermissions();
  const modules = Array.isArray(module) ? module : [module];
  return modules.some((m) => (RANK[perms[m]] || 0) >= RANK[level]);
}

export function roleLabel() {
  if (isSuperAdmin()) return "Super Admin";
  return localStorage.getItem("admin_role") || "Admin";
}
