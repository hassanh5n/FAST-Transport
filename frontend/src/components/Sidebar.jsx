// frontend/src/components/Sidebar.jsx
import { NavLink, useNavigate } from "react-router-dom";
import { colors, fonts } from "../theme";

// ── Inline SVG icons (no library needed) ────────────────────────────────────
const Icon = ({ name, size = 17 }) => {
  const icons = {
    dashboard: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
        <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
      </svg>
    ),
    students: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
    bus: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="11" rx="2"/><path d="M2 11h20"/><path d="M7 7V3"/><path d="M17 7V3"/>
        <circle cx="7" cy="20" r="1.5"/><circle cx="17" cy="20" r="1.5"/>
      </svg>
    ),
    driver: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
        <path d="M12 12v2"/><path d="M10 14h4"/>
      </svg>
    ),
    route: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 17h3a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H3"/><path d="M21 7h-3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/>
        <line x1="9" y1="12" x2="15" y2="12"/>
      </svg>
    ),
    stop: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2a7 7 0 0 1 7 7c0 4.9-7 13-7 13S5 13.9 5 9a7 7 0 0 1 7-7z"/>
        <circle cx="12" cy="9" r="2.5"/>
      </svg>
    ),
    routeStop: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/>
        <path d="M6 8v2a6 6 0 0 0 6 6h2"/><path d="M14 4h4v4"/>
      </svg>
    ),
    semester: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/>
        <path d="M3 10h18"/><path d="M8 14h8"/>
      </svg>
    ),
    assignment: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
        <rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6"/><path d="M9 16h4"/>
      </svg>
    ),
    complaint: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        <path d="M12 8v4"/><circle cx="12" cy="15" r="0.5" fill="currentColor"/>
      </svg>
    ),
    seat: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 9V5a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v4"/><rect x="3" y="9" width="18" height="6" rx="1"/>
        <path d="M5 15v4"/><path d="M19 15v4"/><path d="M8 19h8"/>
      </svg>
    ),
    fee: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>
        <circle cx="12" cy="15" r="2"/>
      </svg>
    ),
    routeChange: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 3l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
        <path d="M7 21l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
      </svg>
    ),
    transport: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="8" width="20" height="10" rx="2"/>
        <circle cx="7" cy="20" r="2"/><circle cx="17" cy="20" r="2"/>
        <path d="M2 12h20"/><path d="M7 8V4"/><path d="M17 8V4"/>
      </svg>
    ),
    register: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <path d="M14 2v6h6"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
      </svg>
    ),
    challan: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/>
        <path d="M8 9h8"/><path d="M8 13h6"/><path d="M8 17h4"/>
      </svg>
    ),
    map: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="3,6 9,3 15,6 21,3 21,18 15,21 9,18 3,21"/>
        <line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>
      </svg>
    ),
    viewRoute: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="2"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/>
      </svg>
    ),
    logout: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/>
      </svg>
    ),
    export: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
    ),
  };
  return icons[name] || null;
};

// ── Nav link definitions ─────────────────────────────────────────────────────
const adminGroups = [
  {
    label: "Overview",
    links: [
      { to: "/admin/dashboard",               label: "Dashboard",           icon: "dashboard"  },
      { to: "/admin/students",                label: "Students",            icon: "students"   },
    ],
  },
  {
    label: "Fleet",
    links: [
      { to: "/admin/buses",                   label: "Buses",               icon: "bus"        },
      { to: "/admin/drivers",                 label: "Drivers",             icon: "driver"     },
      { to: "/admin/routes",                  label: "Routes",              icon: "route"      },
      { to: "/admin/stops",                   label: "Stops",               icon: "stop"       },
      { to: "/admin/routestop",               label: "Route Stops",         icon: "routeStop"  },
      { to: "/admin/assignments",             label: "Assignments",         icon: "assignment" },
    ],
  },
  {
    label: "Operations",
    links: [
      { to: "/admin/semesters",               label: "Semesters",           icon: "semester"   },
      { to: "/admin/student-bus-assignments", label: "Bus Assignments",     icon: "seat"       },
      { to: "/admin/feeverifications",        label: "Fee Verifications",   icon: "fee"        },
      { to: "/admin/routechangerequests",     label: "Route Requests",      icon: "routeChange"},
      { to: "/admin/complaints",              label: "Complaints",          icon: "complaint"  },
      { to: "/admin/export",                  label: "Export Data",         icon: "export"     },
    ],
  },
];

const studentGroups = [
  {
    label: "My Portal",
    links: [
      { to: "/student/dashboard",               label: "Dashboard",         icon: "dashboard"  },
      { to: "/student/transport",               label: "My Transport",      icon: "transport"  },
      { to: "/student/transport-registrations", label: "Register",          icon: "register"   },
      { to: "/student/challan",                 label: "View Challan",      icon: "challan"    },
    ],
  },
  {
    label: "Routes & Map",
    links: [
      { to: "/student/routes",                  label: "View Routes",       icon: "viewRoute"  },
      { to: "/student/route-change",            label: "Route Change",      icon: "routeChange"},
      { to: "/student/map",                     label: "Live Bus Map",      icon: "map"        },
    ],
  },
  {
    label: "Support",
    links: [
      { to: "/student/complaints",              label: "Complaints",        icon: "complaint"  },
    ],
  },
];

// ── Component ────────────────────────────────────────────────────────────────
// Props:
//   role      – "student" | "staff"
//   isMobile  – boolean (injected by PageShell)
//   isOpen    – boolean, controls drawer visibility on mobile
//   onClose   – callback to close the drawer
function Sidebar({ role = "student", isMobile = false, isOpen = false, onClose }) {
  const navigate = useNavigate();
  const groups = role === "staff" ? adminGroups : studentGroups;

  const handleLogout = () => {
    localStorage.clear();
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

// ── Inner content (shared between desktop and drawer) ─────────────────────────
function SidebarContent({ groups, role, handleLogout, isMobile, onClose }) {
  return (
    <>
      {/* Brand */}
      <div style={styles.brand}>
        <div style={styles.logoMark}>
          <svg width="20" height="20" viewBox="0 0 28 28" fill="none">
            <rect x="2" y="8" width="24" height="12" rx="2" stroke="white" strokeWidth="1.6"/>
            <circle cx="8" cy="22" r="2.5" fill="white"/>
            <circle cx="20" cy="22" r="2.5" fill="white"/>
            <path d="M2 12h6l2-4h8l2 4" stroke="white" strokeWidth="1.6" strokeLinejoin="round"/>
          </svg>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={styles.brandSub}>FAST NUCES</p>
          <p style={styles.brandName}>Transport</p>
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
        {role === "staff" ? "Admin Panel" : "Student Portal"}
      </div>

      {/* Nav groups */}
      <nav style={styles.nav}>
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
    overflowY:    "auto",
    scrollbarWidth:"none",
  },
  brand: {
    display:      "flex",
    alignItems:   "center",
    gap:          "12px",
    padding:      "22px 20px 16px",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
  },
  logoMark: {
    width:           "38px",
    height:          "38px",
    borderRadius:    "10px",
    background:      colors.accent,
    display:         "flex",
    alignItems:      "center",
    justifyContent:  "center",
    flexShrink:      0,
    boxShadow:       `0 4px 12px rgba(40,141,196,0.35)`,
  },
  brandSub: {
    margin:        0,
    fontSize:      "9px",
    letterSpacing: "0.15em",
    textTransform: "uppercase",
    color:         "rgba(255,255,255,0.35)",
    fontWeight:    500,
  },
  brandName: {
    margin:        "2px 0 0",
    fontSize:      "15px",
    fontWeight:    "700",
    color:         "#fff",
    letterSpacing: "-0.02em",
    fontFamily:    fonts.heading,
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
    scrollbarWidth:"none",
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