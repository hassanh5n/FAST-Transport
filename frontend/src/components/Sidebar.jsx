// frontend/src/components/Sidebar.jsx
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clearQueryCache } from "../services/queryClient";
import { NavLink, useNavigate } from "react-router-dom";
import { can, isSuperAdmin, roleLabel, passengerLabel } from "../utils/permissions";
import { colors, fonts } from "../theme";
import { BrandMark, BrandWordmark } from "./Brand";

// ── Inline SVG icons (no library needed) ────────────────────────────────────
// One distinct glyph per destination, all on a 24px grid with the same stroke.
const ICON_PATHS = {
  dashboard: <><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></>,
  // People
  students: <><path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2.5 9 2.5 12 0v-5"/><path d="M22 10v6"/></>,
  passengers: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></>,
  driver: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M12 14v7"/><path d="M10.1 11.4 3.4 9.6"/><path d="M13.9 11.4l6.7-1.8"/></>,
  // Fleet
  bus: <><rect x="4" y="3" width="16" height="14" rx="2"/><path d="M4 11h16"/><path d="M8 14.5h.01"/><path d="M16 14.5h.01"/><path d="M7 17v3"/><path d="M17 17v3"/><path d="M2 8v3"/><path d="M22 8v3"/></>,
  route: <><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></>,
  routePlans: <><path d="m12 2 10 5-10 5L2 7z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/></>,
  stop: <><path d="M12 2a7 7 0 0 1 7 7c0 4.9-7 13-7 13S5 13.9 5 9a7 7 0 0 1 7-7z"/><circle cx="12" cy="9" r="2.5"/></>,
  assignment: <><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></>,
  // Operations
  semester: <><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/></>,
  seat: <><path d="M19 9V6a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v3"/><path d="M3 16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v1.5a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5V11a2 2 0 0 0-4 0z"/><path d="M5 18v2"/><path d="M19 18v2"/></>,
  waitlist: <><path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22"/><path d="M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2"/></>,
  fee: <><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/><path d="m9 12 2 2 4-4"/></>,
  challan: <><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/></>,
  routeChange: <><path d="M17 3l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 21l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></>,
  incident: <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></>,
  complaint: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/></>,
  export: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></>,
  // Administration
  shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></>,
  log: <><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></>,
  // Student / driver
  register: <><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11v6"/><path d="M9 14h6"/></>,
  liveMap: <><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2v3"/><path d="M12 19v3"/><path d="M2 12h3"/><path d="M19 12h3"/></>,
  trip: <path d="m3 11 19-9-9 19-2-8-8-2z"/>,
  logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></>,
};

const Icon = ({ name, size = 17 }) => (ICON_PATHS[name] ? (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {ICON_PATHS[name]}
  </svg>
) : null);

// ── Nav link definitions ─────────────────────────────────────────────────────
const adminGroups = [
  {
    label: "Overview",
    links: [
      { to: "/admin/dashboard",               label: "Console",             icon: "dashboard"  },
      { to: "/admin/students",                label: "Students",            icon: "students",   module: "students" },
    ],
  },
  {
    label: "Fleet",
    links: [
      { to: "/admin/buses",                   label: "Buses",               icon: "bus",        module: "fleet" },
      { to: "/admin/drivers",                 label: "Drivers",             icon: "driver",     module: "fleet" },
      { to: "/admin/routes",                  label: "Routes",              icon: "route",      module: "routes" },
      { to: "/admin/route-plans",             label: "Route Plans",         icon: "routePlans",      module: "routes" },
      { to: "/admin/stops",                   label: "Stops",               icon: "stop",       module: "routes" },
      { to: "/admin/assignments",             label: "Assignments",         icon: "assignment", module: "fleet" },
    ],
  },
  {
    label: "Operations",
    links: [
      { to: "/admin/semesters",               label: "Semesters",           icon: "semester",   module: "semesters" },
      { to: "/admin/student-bus-assignments", label: "Bus Assignments",     icon: "seat",       module: "seats" },
      { to: "/admin/waitlist",                label: "Waiting List",        icon: "waitlist",   module: "seats" },
      { to: "/admin/feeverifications",        label: "Fee Verifications",   icon: "fee",        module: "fees" },
      { to: "/admin/routechangerequests",     label: "Route Requests",      icon: "routeChange",module: "route_requests" },
      { to: "/admin/incidents",               label: "Incidents",           icon: "incident",   module: "incidents" },
      { to: "/admin/complaints",              label: "Complaints",          icon: "complaint",  module: "complaints" },
      { to: "/admin/export",                  label: "Export Data",         icon: "export",     module: "export" },
    ],
  },
];

// Only rendered for the super admin
const superAdminGroup = {
  label: "Administration",
  links: [
    { to: "/admin/admins",        label: "Admins & Roles", icon: "shield" },
    { to: "/admin/activity-logs", label: "Activity Logs",  icon: "log"    },
  ],
};

// Hide links the admin's role can't open, and drop groups left empty.
function visibleAdminGroups() {
  const groups = adminGroups
    .map((g) => ({ ...g, links: g.links.filter((l) => can(l.module)) }))
    .filter((g) => g.links.length > 0);
  return isSuperAdmin() ? [...groups, superAdminGroup] : groups;
}

const studentGroups = [
  {
    label: "My Portal",
    links: [
      { to: "/student/dashboard",               label: "Console",           icon: "dashboard"  },
      { to: "/student/transport",               label: "My Transport",      icon: "bus"  },
      { to: "/student/transport-registrations", label: "Register",          icon: "register"   },
      { to: "/student/challan",                 label: "View Challan",      icon: "challan"    },
    ],
  },
  {
    label: "Routes & Map",
    links: [
      { to: "/student/routes",                  label: "Routes",            icon: "route"        },
      { to: "/student/route-change",            label: "Route Change",      icon: "routeChange"},
      { to: "/student/incidents",               label: "Report Incident",   icon: "incident"   },
      { to: "/student/map",                     label: "Live Bus Map",      icon: "liveMap"        },
    ],
  },
  {
    label: "Support",
    links: [
      { to: "/student/complaints",              label: "Complaints",        icon: "complaint"  },
    ],
  },
];

const driverGroups = [
  {
    label: "My Duty",
    links: [
      { to: "/driver/dashboard",  label: "Console",    icon: "dashboard" },
      { to: "/driver/trip",       label: "Live Trip",  icon: "trip"       },
      { to: "/driver/passengers", label: "Passengers", icon: "passengers"  },
    ],
  },
];

// ── Component ────────────────────────────────────────────────────────────────
// Props:
//   role      – "student" | "staff" | "driver"
//   isMobile  – boolean (injected by PageShell)
//   isOpen    – boolean, controls drawer visibility on mobile
//   onClose   – callback to close the drawer
function Sidebar({ role = "student", isMobile = false, isOpen = false, onClose }) {
  const navigate = useNavigate();
  // Re-render when permissions are refreshed from the server (see PageShell).
  const [, setPermVersion] = useState(0);
  useEffect(() => {
    const bump = () => setPermVersion((v) => v + 1);
    window.addEventListener("app:permissions-updated", bump);
    return () => window.removeEventListener("app:permissions-updated", bump);
  }, []);
  const groups = role === "staff" ? visibleAdminGroups() : role === "driver" ? driverGroups : studentGroups;

  const handleLogout = () => {
    localStorage.clear();
    clearQueryCache();
    navigate("/login");
  };

  // On desktop: always visible. On mobile: slide-out drawer.
  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        {isOpen && (
          <div onClick={onClose} style={styles.backdrop} />
        )}

        {/* Drawer */}
        <aside style={{
          ...styles.aside,
          position:   "fixed",
          top:        0,
          left:       0,
          height:     "100vh",
          zIndex:     300,
          transform:  isOpen ? "translateX(0)" : "translateX(-100%)",
          transition: "transform 0.25s ease",
          boxShadow:  isOpen ? "4px 0 24px rgba(0,0,0,0.18)" : "none",
        }}>
          <SidebarContent
            groups={groups}
            role={role}
            onClose={onClose}
            isMobile={isMobile}
            handleLogout={handleLogout}
          />
        </aside>
      </>
    );
  }

  return (
    <aside style={styles.aside}>
      <SidebarContent
        groups={groups}
        role={role}
        handleLogout={handleLogout}
      />
    </aside>
  );
}

// Every page renders its own PageShell, so the sidebar remounts on each navigation.
// The menu's scroll position is kept here, outside React, to survive that.
let savedNavScroll = null; // null until the menu has been shown once since the page loaded

// ── Inner content (shared between desktop and drawer) ─────────────────────────
function SidebarContent({ groups, role, handleLogout, isMobile, onClose }) {
  const navRef = useRef(null);
  // Layout effect: restore before paint, so the menu never flashes at the top.
  useLayoutEffect(() => {
    const nav = navRef.current;
    if (savedNavScroll !== null) {
      nav.scrollTop = savedNavScroll;
      return;
    }
    // First show after a full reload: nothing to restore, so bring the current page's link
    // into view. Centred, so it stays visible if late-loading fonts shift the layout a little.
    nav.querySelector('a[aria-current="page"]')?.scrollIntoView({ block: "center" });
    savedNavScroll = nav.scrollTop;
  }, []);

  return (
    <>
      {/* Brand */}
      <div style={styles.brand}>
        <BrandMark size={25} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <BrandWordmark height={15} style={{ maxWidth: "100%" }} />
        </div>

        {/* Close button — only inside mobile drawer */}
        {isMobile && (
          <button onClick={onClose} style={styles.closeBtn} aria-label="Close menu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        )}
      </div>

      {/* Role pill */}
      <div style={styles.rolePill}>
        <span style={styles.roleDot} />
        {role === "staff" ? roleLabel() : role === "driver" ? "Driver Console" : `${passengerLabel()} Portal`}
      </div>

      {/* Nav groups */}
      <nav ref={navRef} className="sidebar-nav" style={styles.nav} onScroll={(e) => { savedNavScroll = e.currentTarget.scrollTop; }}>
        {groups.map((group) => (
          <div key={group.label} style={styles.group}>
            <p style={styles.groupLabel}>{group.label}</p>
            {group.links.map(({ to, label, icon }) => (
              <NavLink key={to} to={to} style={navLinkStyle} onClick={isMobile ? onClose : undefined}>
                {({ isActive }) => (
                  <span style={isActive ? styles.linkInnerActive : styles.linkInner}>
                    <span style={{ color: isActive ? colors.accent : "inherit", flexShrink: 0 }}>
                      <Icon name={icon} />
                    </span>
                    <span style={styles.linkLabel}>{label}</span>
                    {isActive && <span style={styles.activeDot} />}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Spacer + Logout */}
      <div style={styles.footer}>
        <button onClick={handleLogout} style={styles.logoutBtn}>
          <Icon name="logout" size={15} />
          <span>Sign Out</span>
        </button>
      </div>
    </>
  );
}

// ── NavLink style function ────────────────────────────────────────────────────
const navLinkStyle = () => ({ textDecoration: "none", display: "block" });

// ── Styles ───────────────────────────────────────────────────────────────────
const styles = {
  backdrop: {
    position:   "fixed",
    inset:      0,
    background: "rgba(0,0,0,0.45)",
    zIndex:     299,
  },
  aside: {
    width:        "236px",
    minHeight:    "100vh",
    background:   colors.navyDeep,
    flexShrink:   0,
    display:      "flex",
    flexDirection:"column",
    fontFamily:   fonts.body,
    position:     "sticky",
    top:          0,
    height:       "100vh",
    overflow:     "hidden", // the nav list is the one scroll area; brand and Sign Out stay put
  },
  brand: {
    display:      "flex",
    alignItems:   "center",
    gap:          "12px",
    padding:      "22px 20px 16px",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
  },
  closeBtn: {
    background:   "transparent",
    border:       "none",
    color:        "rgba(255,255,255,0.5)",
    cursor:       "pointer",
    padding:      "4px",
    display:      "flex",
    alignItems:   "center",
    justifyContent:"center",
    borderRadius: "6px",
    flexShrink:   0,
  },
  rolePill: {
    margin:        "14px 16px 6px",
    padding:       "6px 12px",
    background:    "rgba(40,141,196,0.1)",
    border:        "1px solid rgba(40,141,196,0.18)",
    borderRadius:  "999px",
    fontSize:      "11px",
    fontWeight:    "600",
    color:         colors.accentLight,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    display:       "flex",
    alignItems:    "center",
    gap:           "7px",
  },
  roleDot: {
    width:        "6px",
    height:       "6px",
    borderRadius: "50%",
    background:   colors.accent,
    flexShrink:   0,
    boxShadow:    `0 0 6px ${colors.accent}`,
  },
  nav: {
    flex:          1,
    padding:       "8px 0 12px",
    overflowY:     "auto",
    minHeight:     0,
  },
  group: {
    marginBottom: "4px",
  },
  groupLabel: {
    margin:        "16px 20px 4px",
    fontSize:      "9.5px",
    fontWeight:    "700",
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color:         "rgba(255,255,255,0.25)",
  },
  linkInner: {
    display:    "flex",
    alignItems: "center",
    gap:        "11px",
    padding:    "9px 16px",
    margin:     "1px 8px",
    borderRadius:"9px",
    color:      "rgba(255,255,255,0.55)",
    fontSize:   "13px",
    fontWeight: "500",
    cursor:     "pointer",
    transition: "all 0.15s",
    position:   "relative",
  },
  linkInnerActive: {
    display:    "flex",
    alignItems: "center",
    gap:        "11px",
    padding:    "9px 16px",
    margin:     "1px 8px",
    borderRadius:"9px",
    color:      "#ffffff",
    fontSize:   "13px",
    fontWeight: "600",
    cursor:     "pointer",
    background: "rgba(40,141,196,0.14)",
    border:     "1px solid rgba(40,141,196,0.2)",
    position:   "relative",
  },
  linkLabel: {
    flex:         1,
    whiteSpace:   "nowrap",
    overflow:     "hidden",
    textOverflow: "ellipsis",
  },
  activeDot: {
    width:        "5px",
    height:       "5px",
    borderRadius: "50%",
    background:   colors.accent,
    flexShrink:   0,
  },
  footer: {
    padding:     "12px 16px 20px",
    borderTop:   "1px solid rgba(255,255,255,0.06)",
  },
  logoutBtn: {
    display:      "flex",
    alignItems:   "center",
    gap:          "9px",
    width:        "100%",
    padding:      "9px 14px",
    background:   "rgba(239,68,68,0.08)",
    border:       "1px solid rgba(239,68,68,0.15)",
    borderRadius: "9px",
    color:        "#f87171",
    fontSize:     "13px",
    fontWeight:   "600",
    cursor:       "pointer",
    textAlign:    "left",
    fontFamily:   fonts.body,
  },
};

export default Sidebar;