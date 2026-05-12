// frontend/src/pages/admin/dashboard.jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell from "../../components/PageShell";
import { Spinner } from "../../components/ui";
import { getDashboard } from "../../services/transportService";
import { colors, fonts } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";

// SVG icon components
const Icons = {
  Students: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  ),
  Bus: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6v6"/><path d="M16 6v6"/>
      <path d="M2 12h20"/>
      <path d="M18 18h2a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>
      <circle cx="8" cy="18" r="2"/><circle cx="16" cy="18" r="2"/>
      <path d="M8 20h8"/>
    </svg>
  ),
  Route: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/>
      <path d="M12 19h4.5a3.5 3.5 0 0 0 0-7h-8a3.5 3.5 0 0 1 0-7H12"/>
    </svg>
  ),
  Clipboard: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="4" rx="1"/>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
      <path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>
    </svg>
  ),
  MessageCircle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  ),
  RefreshCw: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
      <path d="M21 3v5h-5"/>
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
      <path d="M8 16H3v5"/>
    </svg>
  ),
  CreditCard: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
      <line x1="1" y1="10" x2="23" y2="10"/>
    </svg>
  ),
  // Quick action icons
  PlusCircle: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="16"/>
      <line x1="8" y1="12" x2="16" y2="12"/>
    </svg>
  ),
  UserPlus: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="8.5" cy="7" r="4"/>
      <line x1="20" y1="8" x2="20" y2="14"/>
      <line x1="23" y1="11" x2="17" y2="11"/>
    </svg>
  ),
  Calendar: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/>
      <line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
  CheckSquare: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4"/>
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
};

const STAT_CONFIG = [
  { key: "total_students",             label: "Total Students",     Icon: Icons.Students,     path: "/admin/students",            variant: "blue"   },
  { key: "active_buses",               label: "Active Buses",       Icon: Icons.Bus,          path: "/admin/buses",               variant: "teal"   },
  { key: "active_routes",              label: "Active Routes",      Icon: Icons.Route,        path: "/admin/routes",              variant: "teal"   },
  { key: "active_route_assignments",   label: "Assignments",        Icon: Icons.Clipboard,    path: "/admin/assignments",         variant: "blue"   },
  { key: "pending_complaints",         label: "Pending Complaints", Icon: Icons.MessageCircle,path: "/admin/complaints",          variant: "amber"  },
  { key: "open_route_change_requests", label: "Route Requests",     Icon: Icons.RefreshCw,    path: "/admin/routechangerequests", variant: "amber"  },
  { key: "unverified_fees",            label: "Unverified Fees",    Icon: Icons.CreditCard,   path: "/admin/feeverifications",    variant: "danger" },
];

const VARIANT_STYLES = {
  blue:   { accent: colors.accent,       bg: colors.infoBg,    text: colors.infoText    },
  teal:   { accent: "#0d9488",           bg: "#f0fdfa",        text: "#115e59"          },
  amber:  { accent: "#d97706",           bg: colors.warningBg, text: colors.warningText },
  danger: { accent: colors.dangerText,   bg: colors.dangerBg,  text: colors.dangerText  },
};

function StatCard({ label, value, Icon, path, variant }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  const v = VARIANT_STYLES[variant] || VARIANT_STYLES.blue;

  return (
    <div
      onClick={() => navigate(path)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? v.bg : "#fff",
        border: `1px solid ${hovered ? v.accent + "40" : colors.borderLight}`,
        borderRadius: "14px",
        padding: "20px",
        cursor: "pointer",
        transition: "all 0.15s",
        boxShadow: hovered
          ? `0 4px 16px ${v.accent}18`
          : "0 1px 3px rgba(11,45,66,0.06)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
        <div style={{
          width: "40px", height: "40px", borderRadius: "10px",
          background: v.bg, border: `1px solid ${v.accent}30`,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: v.accent,
        }}>
          <Icon />
        </div>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={hovered ? v.accent : colors.textMuted} strokeWidth="2" strokeLinecap="round">
          <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
        </svg>
      </div>
      <div style={{ fontSize: "30px", fontWeight: "800", color: hovered ? v.accent : colors.textPrimary, fontFamily: fonts.heading, lineHeight: 1, marginBottom: "6px" }}>
        {value ?? "—"}
      </div>
      <div style={{ fontSize: "12.5px", fontWeight: "500", color: colors.textSecondary }}>{label}</div>
    </div>
  );
}

function AdminDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const isMobile = useBreakpoint(768);

  useEffect(() => {
    getDashboard()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load dashboard data."));
  }, []);

  if (error) return (
    <PageShell role="staff" title="Admin Dashboard">
      <div style={{ padding: "48px 0", textAlign: "center", color: colors.dangerText }}>{error}</div>
    </PageShell>
  );

  if (!data) return (
    <PageShell role="staff" title="Admin Dashboard"><Spinner /></PageShell>
  );

  const { stats } = data;
  const fullName = localStorage.getItem("full_name") || localStorage.getItem("username") || "Admin";

  return (
    <PageShell role="staff" title="Admin Dashboard">
      {/* Welcome header */}
      <div style={styles.welcomeRow}>
        <div>
          <h2 style={styles.welcomeHeading}>Welcome, {fullName}</h2>
          <p style={styles.welcomeSub}>Here's an overview of the transport system for the current semester.</p>
        </div>
        {!isMobile && (
          <div className="welcome-row-date">
            {new Date().toLocaleDateString("en-PK", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </div>
        )}
      </div>

      {/* Stat grid */}
      <div style={styles.grid}>
        {STAT_CONFIG.map((cfg) => (
          <StatCard
            key={cfg.key}
            label={cfg.label}
            value={stats?.[cfg.key]}
            Icon={cfg.Icon}
            path={cfg.path}
            variant={cfg.variant}
          />
        ))}
      </div>

      {/* Quick actions */}
      <div style={styles.quickActionsCard}>
        <h3 style={styles.sectionHeading}>Quick Actions</h3>
        <div className="quick-actions-grid">
          {[
            { label: "Add New Bus",      path: "/admin/buses",            Icon: Icons.PlusCircle  },
            { label: "Add Driver",       path: "/admin/drivers",          Icon: Icons.UserPlus    },
            { label: "Manage Semesters", path: "/admin/semesters",        Icon: Icons.Calendar    },
            { label: "Verify Fees",      path: "/admin/feeverifications", Icon: Icons.CheckSquare },
          ].map((a) => <QuickAction key={a.path} {...a} />)}
        </div>
      </div>
    </PageShell>
  );
}

function QuickAction({ label, path, Icon }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={() => navigate(path)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: "10px",
        padding: "12px 16px", background: hovered ? colors.pageBg : "#fff",
        border: `1px solid ${hovered ? colors.accent + "50" : colors.borderLight}`,
        borderRadius: "10px", cursor: "pointer", fontSize: "13px", fontWeight: "600",
        color: hovered ? colors.accent : colors.textPrimary,
        transition: "all 0.15s", fontFamily: fonts.body,
      }}
    >
      <span style={{ color: hovered ? colors.accent : colors.textMuted, display: "flex" }}>
        <Icon />
      </span>
      {label}
    </button>
  );
}

const styles = {
  welcomeRow: {
    display: "flex", alignItems: "flex-start", justifyContent: "space-between",
    flexWrap: "wrap", gap: "12px", marginBottom: "24px",
  },
  welcomeHeading: {
    margin: 0, fontSize: "22px", fontWeight: "800",
    color: colors.textPrimary, fontFamily: fonts.heading, letterSpacing: "-0.02em",
  },
  welcomeSub: { margin: "5px 0 0", fontSize: "13.5px", color: colors.textSecondary },
  dateBadge: {
    fontSize: "12px", fontWeight: "500", color: colors.textMuted,
    background: "#fff", border: `1px solid ${colors.borderLight}`,
    borderRadius: "999px", padding: "6px 14px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: "14px", marginBottom: "24px",
  },
  quickActionsCard: {
    background: "#fff", borderRadius: "14px",
    border: `1px solid ${colors.borderLight}`,
    padding: "20px 24px",
    boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
  },
  sectionHeading: {
    margin: "0 0 14px", fontSize: "14px", fontWeight: "700",
    color: colors.textPrimary, fontFamily: fonts.heading,
  },
  // quickActionsGrid is now a CSS class (.quick-actions-grid) in index.css
};

export default AdminDashboard;