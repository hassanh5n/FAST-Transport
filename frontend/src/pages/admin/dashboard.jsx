// frontend/src/pages/admin/dashboard.jsx
import { useEffect, useState } from "react";
import { lazy, Suspense } from "react";
import { useNavigate } from "react-router-dom";
import PageShell from "../../components/PageShell";
import { Spinner } from "../../components/ui";
import { getActivityLogs, getAdminLiveFleet, getDashboard, getRoutesMap } from "../../services/transportService";
import { can, isSuperAdmin } from "../../utils/permissions";
import { colors, fonts } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";
import LiveFleetMap from "../../components/maps/LiveFleetMap";
const DashboardCharts = lazy(() => import("../../components/DashboardCharts"));

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
  { key: "total_students",             label: "Total Students",     Icon: Icons.Students,     path: "/admin/students",            variant: "blue",   module: "students" },
  { key: "active_buses",               label: "Active Buses",       Icon: Icons.Bus,          path: "/admin/buses",               variant: "teal",   module: "fleet" },
  { key: "active_routes",              label: "Active Routes",      Icon: Icons.Route,        path: "/admin/routes",              variant: "teal",   module: "routes" },
  { key: "active_route_assignments",   label: "Assignments",        Icon: Icons.Clipboard,    path: "/admin/assignments",         variant: "blue",   module: "fleet" },
  { key: "pending_complaints",         label: "Pending Complaints", Icon: Icons.MessageCircle,path: "/admin/complaints",          variant: "amber",  module: "complaints" },
  { key: "open_route_change_requests", label: "Route Requests",     Icon: Icons.RefreshCw,    path: "/admin/routechangerequests", variant: "amber",  module: "route_requests" },
  { key: "unverified_fees",             label: "Unverified Fees",    Icon: Icons.CreditCard,   path: "/admin/feeverifications",    variant: "danger", module: "fees" },
];

const VARIANT_STYLES = {
  blue:   { accent: colors.accent,       bg: colors.infoBg },
  teal:   { accent: "#0d9488",           bg: "#f0fdfa" },
  amber:  { accent: "#d97706",           bg: colors.warningBg },
  danger: { accent: colors.dangerText,   bg: colors.dangerBg },
};

function StatCard({ label, value, icon, path, variant }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  const style = VARIANT_STYLES[variant] || VARIANT_STYLES.blue;
  return (
    <button
      type="button"
      onClick={() => navigate(path)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        textAlign: "left", background: hovered ? style.bg : "#fff",
        border: `1px solid ${hovered ? style.accent + "40" : colors.borderLight}`,
        borderRadius: "14px", padding: "20px", cursor: "pointer",
        transition: "all 0.15s", boxShadow: hovered ? `0 4px 16px ${style.accent}18` : "0 1px 3px rgba(11,45,66,0.06)",
        fontFamily: fonts.body,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
        <span style={{ width: "40px", height: "40px", borderRadius: "10px", background: style.bg, border: `1px solid ${style.accent}30`, display: "flex", alignItems: "center", justifyContent: "center", color: style.accent }}>
          {icon()}
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={hovered ? style.accent : colors.textMuted} strokeWidth="2" strokeLinecap="round">
          <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
        </svg>
      </div>
      <div style={{ fontSize: "30px", fontWeight: "800", color: hovered ? style.accent : colors.textPrimary, fontFamily: fonts.heading, lineHeight: 1, marginBottom: "6px" }}>
        {value ?? "—"}
      </div>
      <div style={{ fontSize: "12.5px", fontWeight: "500", color: colors.textSecondary }}>{label}</div>
    </button>
  );
}

function AdminDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [fleetData, setFleetData] = useState(null);
  const [fleetRoutes, setFleetRoutes] = useState([]);
  const [fleetError, setFleetError] = useState("");
  const [fleetUpdatedAt, setFleetUpdatedAt] = useState(null);
  const isMobile = useBreakpoint(768);

  useEffect(() => {
    getDashboard()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load dashboard data."));
  }, []);

  useEffect(() => {
    if (!can("fleet")) return undefined;
    let cancelled = false;
    getRoutesMap()
      .then((response) => { if (!cancelled) setFleetRoutes(response.data?.routes || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!can("fleet")) return undefined;
    let cancelled = false;
    let requestActive = false;
    let timer;

    const loadFleet = async () => {
      if (cancelled || document.visibilityState === "hidden" || requestActive) return;
      requestActive = true;
      try {
        const response = await getAdminLiveFleet();
        if (!cancelled) {
          setFleetData(response.data);
          setFleetUpdatedAt(new Date());
          setFleetError("");
        }
      } catch {
        if (!cancelled) setFleetError("Live fleet data is temporarily unavailable.");
      } finally {
        requestActive = false;
        if (!cancelled && document.visibilityState !== "hidden") timer = setTimeout(loadFleet, 8000);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        clearTimeout(timer);
        loadFleet();
      }
    };

    loadFleet();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  if (error) return (
    <PageShell role="staff" title="Admin Dashboard">
      <div style={{ padding: "48px 0", textAlign: "center", color: colors.dangerText }}>{error}</div>
    </PageShell>
  );

  if (!data) return (
    <PageShell role="staff" title="Admin Dashboard">
      <Spinner />
    </PageShell>
  );

  const { stats } = data;
  const fullName = localStorage.getItem("full_name") || localStorage.getItem("username") || "Admin";
  const quickActions = [
    { label: "Add New Bus",      path: "/admin/buses",            Icon: Icons.PlusCircle,  module: "fleet" },
    { label: "Add Driver",       path: "/admin/drivers",          Icon: Icons.UserPlus,    module: "fleet" },
    { label: "Manage Semesters", path: "/admin/semesters",        Icon: Icons.Calendar,    module: "semesters" },
    { label: "Verify Fees",      path: "/admin/feeverifications", Icon: Icons.CheckSquare, module: "fees" },
    { label: "Complaints",       path: "/admin/complaints",       Icon: Icons.MessageCircle, module: "complaints" },
  ].filter((action) => can(action.module, "manage"));

  return (
    <PageShell role="staff" title="Admin Dashboard">
      {/* Welcome header */}
      <div style={styles.welcomeRow}>
        <div>
          <h2 style={styles.welcomeHeading}>Welcome, {fullName}</h2>
          <p style={styles.welcomeSub}>
            Here's an overview of the transport system for the current semester.
          </p>
        </div>
        {!isMobile && (
          <div className="welcome-row-date">
            {new Date().toLocaleDateString("en-PK", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div style={{ ...styles.quickActionsCard, ...(isMobile ? { gridTemplateColumns: "1fr" } : {}) }}>
        <div>
          <h3 style={{ ...styles.sectionHeading, marginBottom: 2 }}>Quick actions</h3>
          <span style={styles.actionHint}>{quickActions.length} available</span>
        </div>
        <div className="quick-actions-grid">
          {quickActions.map((action) => <QuickAction key={action.path} label={action.label} path={action.path} Icon={action.Icon} />)}
        </div>
      </div>

      <div style={styles.grid}>
        {STAT_CONFIG.filter((config) => can(config.module)).map((config) => (
          <StatCard key={config.key} label={config.label} value={stats?.[config.key]} icon={config.Icon} path={config.path} variant={config.variant} />
        ))}
      </div>

      {can("fleet") && (
        <div style={{ ...styles.fleetActivityRow, ...(isMobile ? { gridTemplateColumns: "1fr" } : {}) }}>
          <div style={styles.fleetCard}>
            <div style={styles.fleetHeader}>
              <div>
                <h3 style={{ ...styles.sectionHeading, margin: 0 }}>Live Fleet</h3>
                <div style={styles.fleetSummary}>
                  {fleetData ? `${fleetData.buses?.length || 0} active buses · ${fleetData.buses?.filter((bus) => bus.status === "live").length || 0} live` : "Loading active bus locations..."}
                  {fleetUpdatedAt && ` · Updated ${fleetUpdatedAt.toLocaleTimeString()}`}
                </div>
              </div>
              {fleetError && <span style={{ color: colors.warningText, fontSize: 12 }}>{fleetError}</span>}
            </div>
            {fleetData ? (
              fleetData.buses?.length ? (
                <LiveFleetMap routes={fleetRoutes} buses={fleetData.buses} height={isMobile ? 320 : 420} />
              ) : (
                <div style={{ padding: "32px 0", textAlign: "center", color: colors.textMuted, fontSize: 13 }}>No active buses are configured.</div>
              )
            ) : fleetError ? (
              <div style={{ padding: "32px 0", textAlign: "center", color: colors.warningText, fontSize: 13 }}>{fleetError}</div>
            ) : <Spinner />}
          </div>
          {isSuperAdmin() && <RecentAdminActivity />}
        </div>
      )}

      {!can("fleet") && isSuperAdmin() && <RecentAdminActivity />}

      <Suspense fallback={<div style={styles.chartsLoading}>Loading dashboard charts...</div>}>
        <DashboardCharts stats={stats} fleetData={fleetData} showFleet={can("fleet")} />
      </Suspense>

    </PageShell>
  );
}

const ACTION_COLORS = {
  create: { bg: colors.successBg, text: colors.successText },
  update: { bg: colors.infoBg, text: colors.infoText },
  delete: { bg: colors.dangerBg, text: colors.dangerText },
  action: { bg: colors.warningBg, text: colors.warningText },
  login: { bg: colors.neutralBg, text: colors.neutralText },
};

function RecentAdminActivity() {
  const navigate = useNavigate();
  const [items, setItems] = useState(null);

  useEffect(() => {
    getActivityLogs({ page_size: 8 })
      .then((res) => setItems(res.data.items || []))
      .catch(() => setItems([]));
  }, []);

  return (
    <div style={{ ...styles.activityCard, marginTop: 0, height: "100%", boxSizing: "border-box" }}>
      <div style={styles.activityHeader}>
        <h3 style={{ ...styles.sectionHeading, margin: 0 }}>Recent Admin Activity</h3>
        <button onClick={() => navigate("/admin/activity-logs")} style={styles.linkBtn}>View all logs →</button>
      </div>
      {items === null ? <Spinner /> : items.length === 0 ? (
        <p style={{ margin: 0, fontSize: "13px", color: colors.textMuted }}>No admin activity yet.</p>
      ) : (
        <div style={{ display: "grid", gap: "2px" }}>
          {items.map((log) => {
            const color = ACTION_COLORS[log.action] || ACTION_COLORS.action;
            return (
              <div key={log.id} style={styles.activityRow}>
                <span style={{ ...styles.actionTag, background: color.bg, color: color.text }}>{log.action}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={styles.activityText}><strong>{log.actor_name || log.actor_username || "System"}</strong> — {log.description}</div>
                  <div style={styles.activityMeta}>{log.module_label} · {new Date(log.created_at).toLocaleString()}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function QuickAction({ label, path, Icon: icon }) {
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
        {icon()}
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
  fleetActivityRow: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 7fr) minmax(240px, 3fr)",
    gap: "16px",
    alignItems: "stretch",
    marginBottom: "20px",
  },
  fleetCard: {
    minWidth: 0,
    background: "#fff", borderRadius: "14px",
    border: `1px solid ${colors.borderLight}`,
    padding: "20px 24px",
    boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
  },
  fleetHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: "12px", flexWrap: "wrap", marginBottom: "12px",
  },
  fleetSummary: { marginTop: "4px", fontSize: "12px", color: colors.textSecondary },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: "14px", marginBottom: "24px",
  },
  quickActionsCard: {
    display: "grid",
    gridTemplateColumns: "130px minmax(0, 1fr)",
    alignItems: "center",
    gap: "18px",
    background: "#fff", borderRadius: "14px",
    border: `1px solid ${colors.borderLight}`,
    padding: "14px 18px",
    marginBottom: "20px",
    boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
  },
  activityCard: {
    minWidth: 0,
    background: "#fff", borderRadius: "14px",
    border: `1px solid ${colors.borderLight}`,
    padding: "20px 24px",
    boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
  },
  sectionHeading: {
    margin: "0 0 10px", fontSize: "15px", fontWeight: "700",
    color: colors.textPrimary, fontFamily: fonts.heading,
  },
  actionHint: { color: colors.textMuted, fontSize: "11px" },
  activityHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    flexWrap: "wrap", marginBottom: "12px", gap: "8px",
  },
  linkBtn: {
    background: "transparent", border: "none", color: colors.accent,
    fontSize: "13px", fontWeight: "600", cursor: "pointer", fontFamily: fonts.body, padding: 0,
  },
  activityRow: {
    display: "flex", alignItems: "flex-start", gap: "10px", minWidth: 0,
    padding: "9px 0", borderBottom: `1px solid ${colors.tableRowBorder}`,
  },
  actionTag: {
    fontSize: "10.5px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.04em",
    padding: "3px 8px", borderRadius: "999px", flexShrink: 0, marginTop: "1px", minWidth: "54px", textAlign: "center",
  },
  activityText: { fontSize: "13px", color: colors.textPrimary, overflowWrap: "anywhere", lineHeight: 1.4 },
  activityMeta: { fontSize: "11.5px", color: colors.textMuted, marginTop: "3px", overflowWrap: "anywhere", lineHeight: 1.35 },
  chartsLoading: {
    minHeight: "218px", marginBottom: "20px", borderRadius: "14px",
    background: colors.neutralBg, color: colors.textMuted, display: "flex",
    alignItems: "center", justifyContent: "center", fontSize: "12px",
  },
};

export default AdminDashboard;
