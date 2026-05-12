import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, DetailRow, Pill, Banner } from "../../components/ui";
import { btn, colors, fonts, radius } from "../../theme";
import { getDashboard } from "../../services/transportService";
import { useBreakpoint } from "../../utils/useBreakpoint";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function downloadTransportCard() {
  const token = localStorage.getItem("access");
  try {
    const res = await fetch(`${API_BASE}/api/download-transport-card/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) { alert("Failed to download. Try again."); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "transport-card.pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    alert("Download failed. Please try again.");
  }
}

// ── Student Transport Card ────────────────────────────────────────────
function StudentCard({ profile, seat, active_registration, isMobile }) {
  return (
    <div className="student-transport-card" style={{
      position: "relative",
      background: "linear-gradient(135deg, #1a4a68 0%, #0b2d42 60%, #0f3a55 100%)",
      borderRadius: "18px",
      padding: isMobile ? "22px 20px" : "28px 32px",
      marginBottom: 0,
      overflow: "hidden",
      boxShadow: "0 8px 32px rgba(11,45,66,0.28), 0 2px 8px rgba(11,45,66,0.16)",
      minHeight: isMobile ? "auto" : "260px",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      gap: isMobile ? "20px" : "0",
    }}>

      {/* ── Watermark ── */}
      <img src="/bus_favicon.svg" alt="" style={{
        position: "absolute", right: "-20px", bottom: "-20px",
        width: "200px", opacity: 0.07,
        filter: "invert(1)", pointerEvents: "none", userSelect: "none",
      }} />

      {/* ── Decorative circles ── */}
      <div style={{ position: "absolute", top: "-50px", right: "-30px", width: "220px", height: "220px", borderRadius: "50%", background: "rgba(255,255,255,0.04)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: "20px", right: "-70px", width: "180px", height: "180px", borderRadius: "50%", background: "rgba(255,255,255,0.03)", pointerEvents: "none" }} />

      {/* ── Top row: brand + status ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "34px", height: "34px", borderRadius: "8px",
            background: "rgba(40,141,196,0.35)", border: "1px solid rgba(40,141,196,0.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <rect x="2" y="8" width="24" height="12" rx="2" stroke="white" strokeWidth="1.8"/>
              <circle cx="8" cy="22" r="2.5" fill="white"/>
              <circle cx="20" cy="22" r="2.5" fill="white"/>
              <path d="M2 12h6l2-4h8l2 4" stroke="white" strokeWidth="1.8" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <p style={{ margin: 0, fontSize: "9px", letterSpacing: "0.16em", color: "rgba(255,255,255,0.4)", textTransform: "uppercase" }}>FAST NUCES</p>
            <p style={{ margin: 0, fontSize: "13px", fontWeight: "700", color: "#fff" }}>Transport Card</p>
          </div>
        </div>

        <div style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
          <div style={{
            width: "7px", height: "7px", borderRadius: "50%",
            background: seat ? "#22c55e" : "#f59e0b",
            boxShadow: seat ? "0 0 6px #22c55e" : "0 0 6px #f59e0b",
          }} />
          <span style={{ fontSize: "11px", fontWeight: "600", color: seat ? "#86efac" : "#fcd34d" }}>
            {seat ? "Active" : "Pending"}
          </span>
        </div>
      </div>

      {/* ── Bottom row: name + details ── */}
      <div className="transport-card-bottom" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ minWidth: 0 }}>
          <p style={{ margin: "0 0 4px", fontSize: "9px", color: "rgba(255,255,255,0.35)", letterSpacing: "0.1em", textTransform: "uppercase" }}>Card Holder</p>
          <p style={{ margin: "0 0 4px", fontSize: isMobile ? "16px" : "20px", fontWeight: "800", color: "#fff", letterSpacing: "0.02em", fontFamily: fonts.heading, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: isMobile ? "200px" : "none" }}>
            {(`${profile.first_name || ""} ${profile.last_name || ""}`.trim() || profile.roll_number).toUpperCase()}
          </p>
          <p style={{ margin: 0, fontSize: "11px", color: "rgba(255,255,255,0.45)", letterSpacing: "0.06em" }}>
            {profile.roll_number} · {profile.department} · Batch {profile.batch}
          </p>
        </div>

        <div style={{ display: "flex", gap: "28px", textAlign: "right", flexShrink: 0 }}>
          {[
            { label: "Seat", value: seat ? `#${seat.seat_number}` : "—" },
            { label: "Stop", value: active_registration?.stop || "—" },
          ].map(({ label, value }) => (
            <div key={label}>
              <p style={{ margin: "0 0 3px", fontSize: "9px", color: "rgba(255,255,255,0.35)", letterSpacing: "0.1em", textTransform: "uppercase" }}>{label}</p>
              <p style={{ margin: 0, fontSize: "14px", fontWeight: "700", color: "#fff" }}>{value}</p>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────
function StudentDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const navigate = useNavigate();
  const isMobile = useBreakpoint(768);

  const pendingMsg = "Fees paid; Admin will assign seats shortly.";
  const unpaidMsg  = "Registration submitted. Please pay transport fee to proceed.";

  useEffect(() => {
    getDashboard()
      .then((res) => {
        const d = res.data;
        if (d.role === "staff") { navigate("/admin/dashboard", { replace: true }); return; }
        setData(d);
      })
      .catch(() => setError("Failed to load dashboard data."));
  }, [navigate]);

  const handleDownload = async () => {
    setDownloading(true);
    await downloadTransportCard();
    setDownloading(false);
  };

  if (error) return (
    <PageShell role="student" title="Student Dashboard">
      <Banner variant="danger">{error}</Banner>
    </PageShell>
  );
  if (!data) return <PageShell role="student" title="Student Dashboard"><Spinner /></PageShell>;

  const { profile, recent_notifications, active_registration, seat, waitlist_position } = data;
  const normStatus      = (active_registration?.status || "").toLowerCase();
  const hasSubmittedFee = Boolean(active_registration?.fee_submitted);
  const displayStatus   = (!seat && hasSubmittedFee && ["pending", "approved", "payment_submitted"].includes(normStatus))
    ? pendingMsg : active_registration?.status;
  const canRequestRouteChange = active_registration && ["approved", "confirmed"].includes(normStatus) && seat;

  return (
    <PageShell role="student" title="Student Dashboard">

      {/* ── Page header row: title + download button ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "12px",
        marginBottom: "24px",
      }}>
        <div /> {/* spacer — PageShell already renders the title */}

        {seat && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
              padding: "9px 18px",
              background: downloading
                ? "rgba(11,45,66,0.5)"
                : "linear-gradient(135deg, #1a4a68, #0b2d42)",
              color: "#fff",
              border: "none",
              borderRadius: "10px",
              fontSize: "13px",
              fontWeight: "600",
              cursor: downloading ? "not-allowed" : "pointer",
              fontFamily: fonts.body,
              boxShadow: "0 2px 8px rgba(11,45,66,0.25)",
              transition: "opacity 0.15s",
              opacity: downloading ? 0.7 : 1,
            }}
            onMouseEnter={e => { if (!downloading) e.currentTarget.style.opacity = "0.85"; }}
            onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
          >
            {downloading ? (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.2"
                  strokeLinecap="round" strokeLinejoin="round"
                  style={{ animation: "spin 1s linear infinite" }}>
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                Downloading...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.2"
                  strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Download Transport Card
              </>
            )}
          </button>
        )}
      </div>

      {/* spin keyframe injected once */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>

      {/* ── Transport Card + Right Panel ── */}
      <div className="transport-card-grid">

        <StudentCard profile={profile} seat={seat} active_registration={active_registration} isMobile={isMobile} />

        <div style={{
          background: "#fff",
          border: `1px solid ${colors.borderLight}`,
          borderRadius: "18px",
          padding: isMobile ? "16px" : "24px",
          boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
          display: "flex",
          flexDirection: "column",
          minHeight: isMobile ? "auto" : "260px",
          boxSizing: "border-box",
        }}>
          <p style={{ margin: "0 0 14px", fontSize: "11px", fontWeight: "700", color: colors.textMuted, textTransform: "uppercase", letterSpacing: "0.08em" }}>Quick Actions</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", flex: 1, overflowY: "auto" }}>
            {[
              {
                label: "Pay Transport Fee",
                path: "/student/challan",
                show: !seat && !!active_registration,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/><path d="M8 9h8"/><path d="M8 13h6"/><path d="M8 17h4"/></svg>,
              },
              {
                label: "Register for Transport",
                path: "/student/transport-registrations",
                show: !active_registration,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>,
              },
              {
                label: "Request Route Change",
                path: "/student/route-change",
                show: canRequestRouteChange,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 21l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>,
              },
              {
                label: "View Routes",
                path: "/student/routes",
                show: true,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="2"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/></svg>,
              },
              {
                label: "Live Bus Map",
                path: "/student/map",
                show: true,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="3,6 9,3 15,6 21,3 21,18 15,21 9,18 3,21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>,
              },
              {
                label: "Submit Complaint",
                path: "/student/complaints",
                show: true,
                icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M12 8v4"/><circle cx="12" cy="15" r="0.5" fill="currentColor"/></svg>,
              },
            ]
              .filter(a => a.show)
              .map(({ label, path, icon }) => (
                <button
                  key={path}
                  onClick={() => navigate(path)}
                  style={{
                    display: "flex", alignItems: "center", gap: "10px",
                    padding: "9px 13px",
                    background: colors.pageBg,
                    border: `1px solid ${colors.borderLight}`,
                    borderRadius: "9px",
                    cursor: "pointer",
                    fontSize: "13px", fontWeight: "500",
                    color: colors.textPrimary,
                    fontFamily: fonts.body,
                    textAlign: "left",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = colors.infoBg;
                    e.currentTarget.style.borderColor = "rgba(40,141,196,0.3)";
                    e.currentTarget.style.color = colors.accent;
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = colors.pageBg;
                    e.currentTarget.style.borderColor = colors.borderLight;
                    e.currentTarget.style.color = colors.textPrimary;
                  }}
                >
                  <span style={{ color: "inherit", display: "flex", flexShrink: 0 }}>{icon}</span>
                  {label}
                </button>
              ))
            }
          </div>
        </div>

      </div>

      {/* ── Main two-column layout ── */}
      <div className="dashboard-main-grid">

        {/* ── Left column ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

          {/* Transport Status */}
          <ContentCard>
            <h3 style={sectionH}>Transport Status</h3>
            {active_registration ? (
              <>
                <DetailRow label="Semester" value={active_registration.semester} />
                <DetailRow label="Route"    value={active_registration.route} />
                <DetailRow label="Stop"     value={active_registration.stop} />
                <DetailRow label="Status"   value={
                  <Pill
                    label={displayStatus}
                    variant={normStatus === "approved" ? "success" : normStatus === "rejected" ? "danger" : "warning"}
                  />
                } />

                <div style={{ marginTop: "16px" }}>
                  {seat ? (
                    <div style={{ display: "inline-flex", alignItems: "center", gap: "10px", background: colors.successBg, border: `1px solid rgba(34,197,94,0.2)`, borderRadius: radius.md, padding: "12px 20px" }}>
                      <span style={{ fontSize: "22px" }}>🎫</span>
                      <div>
                        <div style={{ fontSize: "11px", color: colors.successText, fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em" }}>Allocated Seat</div>
                        <div style={{ fontSize: "22px", fontWeight: "800", color: colors.successText }}>#{seat.seat_number}</div>
                      </div>
                    </div>
                  ) : waitlist_position ? (
                    <div style={{ display: "inline-flex", alignItems: "center", gap: "10px", background: colors.warningBg, border: `1px solid rgba(245,158,11,0.2)`, borderRadius: radius.md, padding: "12px 20px" }}>
                      <span style={{ fontSize: "22px" }}>⏳</span>
                      <div>
                        <div style={{ fontSize: "11px", color: colors.warningText, fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em" }}>Waitlist Position</div>
                        <div style={{ fontSize: "22px", fontWeight: "800", color: colors.warningText }}>#{waitlist_position}</div>
                      </div>
                    </div>
                  ) : (
                    <Banner variant={hasSubmittedFee ? "info" : "warning"} style={{ margin: 0 }}>
                      {hasSubmittedFee ? "Payment received — pending seat allocation." : unpaidMsg}
                    </Banner>
                  )}
                </div>
              </>
            ) : (
              <>
                <Banner variant="warning">{unpaidMsg}</Banner>
                <button onClick={() => navigate("/student/transport")} style={{ ...btn.primary, marginTop: "8px" }}>
                  View My Transport
                </button>
              </>
            )}
          </ContentCard>

          {/* Profile */}
          <ContentCard>
            <h3 style={sectionH}>My Profile</h3>
            <DetailRow label="Roll No"    value={profile.roll_number} />
            <DetailRow label="Full Name" value={`${profile.first_name || ""} ${profile.last_name || ""}`.trim() || "—"} />
            <DetailRow label="Department" value={profile.department} />
            <DetailRow label="Batch"      value={profile.batch} />
            <DetailRow label="Phone"      value={profile.phone} />
            <DetailRow label="Address"    value={profile.address} />
          </ContentCard>

          {/* Route Change CTA */}
          {canRequestRouteChange && (
            <ContentCard style={{ borderLeft: `4px solid ${colors.accent}` }}>
              <h3 style={{ ...sectionH, marginBottom: "6px" }}>Request Route Change</h3>
              <p style={{ margin: "0 0 14px", fontSize: "13.5px", color: colors.textSecondary }}>
                Want to switch to a different route? Submit a request and admin will review seat availability.
              </p>
              <button onClick={() => navigate("/student/route-change")} style={btn.primary}>
                Request Route Change →
              </button>
            </ContentCard>
          )}
        </div>

        {/* ── Right column: Notifications ── */}
        <div style={{
          background: "#fff",
          border: `1px solid ${colors.borderLight}`,
          borderRadius: "12px",
          padding: "20px",
          boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
          position: "sticky",
          top: "84px",
        }}>
          <h3 style={{ ...sectionH, marginBottom: "16px" }}>Notifications</h3>
          {recent_notifications?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {recent_notifications.map((n, i) => (
                <div key={i} style={{
                  padding: "12px 14px",
                  borderRadius: "9px",
                  background: n.is_read ? colors.pageBg : colors.infoBg,
                  border: `1px solid ${n.is_read ? colors.borderLight : "rgba(40,141,196,0.2)"}`,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "8px", marginBottom: "4px" }}>
                    <span style={{ fontSize: "13px", fontWeight: "600", color: colors.textPrimary }}>{n.title}</span>
                    {!n.is_read && <Pill label="New" variant="info" />}
                  </div>
                  <p style={{ margin: 0, fontSize: "12.5px", color: colors.textSecondary, lineHeight: 1.5 }}>{n.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "32px 0" }}>
              <div style={{ marginBottom: "10px", color: "#facc15", filter: "drop-shadow(0 0 6px rgba(250,204,21,0.5))" }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
              </div>
              <p style={{ margin: 0, fontSize: "13px", color: colors.textMuted }}>No notifications yet.</p>
            </div>
          )}
        </div>

      </div>
    </PageShell>
  );
}

const sectionH = {
  margin: "0 0 12px",
  fontSize: "15px",
  fontWeight: "700",
  color: colors.textPrimary,
  fontFamily: fonts.heading,
};

export default StudentDashboard;