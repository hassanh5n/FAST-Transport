import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Pill, Banner, ConfirmModal } from "../../components/ui";
import { btn, colors, fonts } from "../../theme";
import {
  getDashboard,
  getWaitlistStatus,
  cancelRegistration,
  getSemesters,
} from "../../services/transportService";
import RegistrationSteps from "./RegistrationSteps";
import { openSemesters, feeFor, formatPKR, formatDate, fullName, profileMeta } from "./transportHelpers";

// Time left on a seat-offer deadline. A held seat is not open-ended, so the
// passenger needs to see the clock, not just a status word.
function formatCountdown(deadline, now) {
  if (!deadline) return null;
  const remaining = new Date(deadline).getTime() - now;
  if (remaining <= 0) return { expired: true, label: "expired" };
  const hours = Math.floor(remaining / 3600000);
  const minutes = Math.floor((remaining % 3600000) / 60000);
  return { expired: false, label: hours >= 1 ? `${hours}h ${minutes}m` : `${minutes}m` };
}

const sectionH = { margin: 0, fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading };
const ghostBtn = { ...btn.ghost, padding: "9px 16px", fontSize: 13 };

function Fact({ label, children, wide }) {
  return (
    <div className={`tp-fact${wide ? " tp-fact--wide" : ""}`}>
      <dt>{label}</dt>
      <dd>{children ?? "—"}</dd>
    </div>
  );
}

// ── Not registered (or the last registration was cancelled) ─────────────────
function NotRegistered({ profile, semesters, cancelled, navigate }) {
  const open = openSemesters(semesters);
  const semester = open[0];
  const fee = feeFor(semester, profile);
  const deadline = formatDate(semester?.registration_deadline, true);

  return (
    <>
      {cancelled && (
        <Banner variant="warning">
          Your previous registration was cancelled or its seat offer expired. You have not been charged.
        </Banner>
      )}
      <div className="tp-layout">
        <ContentCard style={{ marginBottom: 0 }}>
          <div className="tp-hero">
            <span className="tp-hero__icon" aria-hidden="true">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6v6" /><path d="M16 6v6" /><path d="M2 12h20" /><path d="M18 18h2a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /><circle cx="8" cy="18" r="2" /><circle cx="16" cy="18" r="2" /></svg>
            </span>
            <div style={{ minWidth: 0 }}>
              <h3 style={{ ...sectionH, fontSize: 20, letterSpacing: "-0.01em" }}>
                {cancelled ? "Register again for this semester" : "You're not registered for transport yet"}
              </h3>
              <p style={{ margin: "6px 0 0", fontSize: 14, lineHeight: 1.6, color: colors.textSecondary, maxWidth: 560 }}>
                {semester
                  ? `Registration for ${semester.name} is open. Pick your pickup stop and you'll be placed on the route that serves it.`
                  : "Registration is closed right now. You can register as soon as the transport office opens the next semester."}
              </p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 18 }}>
                {semester && (
                  <button onClick={() => navigate("/student/transport-registrations")} style={{ ...btn.primary, padding: "11px 22px", fontSize: 14 }}>
                    Register for transport
                  </button>
                )}
                <button onClick={() => navigate("/student/routes")} style={ghostBtn}>Browse routes</button>
              </div>
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${colors.borderLight}`, margin: "24px 0 20px" }} />
          <h4 style={{ ...sectionH, fontSize: 13.5, marginBottom: 14 }}>How it works</h4>
          <RegistrationSteps layout="row" />
        </ContentCard>

        <aside className="tp-side">
          <ContentCard style={{ marginBottom: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <h3 style={sectionH}>This semester</h3>
              <Pill label={semester ? "Open" : "Closed"} variant={semester ? "success" : "neutral"} />
            </div>
            <dl className="tp-facts tp-facts--stack">
              <Fact label="Semester">{semester?.name || "No semester open"}</Fact>
              <Fact label="Your fee">{semester ? formatPKR(fee) : "—"}</Fact>
              <Fact label="Registration closes">{semester ? (deadline || "When the office closes it") : "—"}</Fact>
            </dl>
            <p style={{ margin: "14px 0 0", fontSize: 12.5, lineHeight: 1.55, color: colors.textMuted }}>
              If your route is full you join its waiting list. Nothing is charged until a seat is confirmed for you.
            </p>
          </ContentCard>
          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={sectionH}>Your account</h3>
            <dl className="tp-facts tp-facts--stack">
              <Fact label="Name">{fullName(profile) || "—"}</Fact>
              <Fact label="Details">{profileMeta(profile) || "—"}</Fact>
            </dl>
          </ContentCard>
        </aside>
      </div>
    </>
  );
}

// ── The single next action for a live registration ──────────────────────────
function nextStep({ normStatus, seat, isWaitlisted, isSeatHeld, hasSubmittedFee, queueInfo, countdown }) {
  if (normStatus === "rejected") {
    return { tone: "danger", title: "Registration rejected", text: "Contact the transport office for the reason and what to do next.", action: { label: "Contact the office", to: "/student/complaints" } };
  }
  if (seat) {
    return { tone: "success", title: "You're all set", text: `Seat #${seat.seat_number} is yours for this semester. Track your bus live on the day.`, action: { label: "Open live bus map", to: "/student/map" }, secondary: { label: "Request route change", to: "/student/route-change" } };
  }
  if (isWaitlisted) {
    return { tone: "info", title: "Wait for a seat", text: `You are ${queueInfo.position} of ${queueInfo.total} in the queue. You'll be notified the moment a seat opens, and only then is a challan issued.` };
  }
  if (hasSubmittedFee) {
    return { tone: "info", title: "Payment is being verified", text: "Your payment has been recorded. The transport office confirms your seat once it is verified." };
  }
  return {
    tone: "warning",
    title: "Pay your transport fee",
    text: isSeatHeld && countdown && !countdown.expired
      ? `Your seat is held for ${countdown.label}. Pay before then or it passes to the next passenger in the queue.`
      : "Pay the fee using your challan. Your seat is confirmed once the office verifies the payment.",
    action: { label: "View challan", to: "/student/challan" },
  };
}

const TONE = {
  success: { bg: colors.successBg, text: colors.successText, bar: colors.successDot },
  warning: { bg: colors.warningBg, text: colors.warningText, bar: colors.warningDot },
  info:    { bg: colors.infoBg,    text: colors.infoText,    bar: colors.infoDot },
  danger:  { bg: colors.dangerBg,  text: colors.dangerText,  bar: colors.dangerDot },
};

function StudentTransport() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [queue, setQueue] = useState(null);
  const [semesters, setSemesters] = useState([]);
  const [cancelling, setCancelling] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const load = () => {
    getDashboard()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load transport data."));
    getWaitlistStatus()
      .then((res) => setQueue(res.data))
      .catch(() => setQueue(null));
    getSemesters()
      .then((res) => { const d = res.data?.results ?? res.data; setSemesters(Array.isArray(d) ? d : []); })
      .catch(() => setSemesters([]));
  };

  useEffect(() => { load(); }, []);

  // Keep the offer countdown moving without re-fetching.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelRegistration(queue?.registration_id ?? data?.active_registration?.id);
      setConfirmCancel(false);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Could not cancel your registration.");
      setConfirmCancel(false);
    } finally {
      setCancelling(false);
    }
  };

  if (error) return <PageShell role="student" title="My Transport"><Banner variant="danger">{error}</Banner></PageShell>;
  if (!data)  return <PageShell role="student" title="My Transport"><Spinner /></PageShell>;

  const { profile, active_registration, seat, waitlist_position, waitlist, fee_summary } = data;
  // queue.status comes from TransportRegistration and is the authoritative
  // value ("Seat Held" / "Waitlisted" / "Approved"); the dashboard's
  // active_registration is only a fallback for older data.
  const effectiveStatus = queue?.status || active_registration?.status || "";
  const normStatus = effectiveStatus.toLowerCase();

  if (!active_registration || normStatus === "cancelled") {
    return (
      <PageShell role="student" title="My Transport">
        <PageTitle sub="Your transport for this semester.">My Transport</PageTitle>
        <NotRegistered profile={profile} semesters={semesters} cancelled={normStatus === "cancelled"} navigate={navigate} />
      </PageShell>
    );
  }

  const queueInfo = queue?.waitlist || waitlist;
  const countdown = formatCountdown(queue?.payment_due_at, now);
  const isWaitlisted = Boolean(queueInfo) && !seat;
  const isSeatHeld = queue?.status === "Seat Held" && queue?.challan_status !== "paid";
  const canCancel = queue?.challan_status !== "paid" && ["Waitlisted", "Seat Held", "Pending"].includes(queue?.status || "");
  const hasSubmittedFee = Boolean(active_registration.fee_submitted);
  const statusLabel = !seat && hasSubmittedFee && ["pending", "approved", "payment_submitted"].includes(normStatus)
    ? "Payment received"
    : effectiveStatus;
  const holdsSeat = Boolean(seat) || isSeatHeld;
  const statusVariant = ["approved", "confirmed"].includes(normStatus) ? "success" : normStatus === "rejected" ? "danger" : "warning";

  const step = nextStep({ normStatus, seat, isWaitlisted, isSeatHeld, hasSubmittedFee, queueInfo, countdown });
  const tone = TONE[step.tone];

  return (
    <PageShell role="student" title="My Transport">
      {confirmCancel && (
        <ConfirmModal
          title="Cancel registration?"
          message={
            holdsSeat
              ? "Your seat will be released immediately and given to the next passenger in the queue. You will have to register again to get another seat."
              : "You will be removed from the waiting list and lose your place in the queue."
          }
          confirmLabel={cancelling ? "Cancelling…" : "Yes, cancel"}
          onConfirm={handleCancel}
          onCancel={() => setConfirmCancel(false)}
        />
      )}

      <PageTitle sub="Your transport for this semester.">My Transport</PageTitle>

      <div className="tp-layout">
        {/* ── Registration ── */}
        <ContentCard style={{ marginBottom: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div>
              <h3 style={{ ...sectionH, fontSize: 18 }}>{active_registration.semester} registration</h3>
              <p style={{ margin: "4px 0 0", fontSize: 13, color: colors.textSecondary }}>{[fullName(profile), profileMeta(profile)].filter(Boolean).join(" · ")}</p>
            </div>
            <Pill label={statusLabel} variant={statusVariant} />
          </div>

          <dl className="tp-facts">
            <Fact label="Route">{active_registration.route || "Not assigned yet"}</Fact>
            <Fact label="Pickup stop">{active_registration.stop}</Fact>
            <Fact label="Bus">{active_registration.bus || "Pending assignment"}</Fact>
            <Fact label="Seat">{seat ? `#${seat.seat_number}` : "Not allocated yet"}</Fact>
            {queueInfo && <Fact label="Waiting list">Position {queueInfo.position} of {queueInfo.total}</Fact>}
            {!queueInfo && waitlist_position && <Fact label="Waiting list">Position #{waitlist_position}</Fact>}
            {isSeatHeld && countdown && (
              <Fact label="Pay before" wide>
                {countdown.expired ? "Deadline passed" : `${formatDate(queue.payment_due_at, true)} (${countdown.label} left)`}
              </Fact>
            )}
          </dl>

          {canCancel && (
            <div style={{ marginTop: 22, paddingTop: 18, borderTop: `1px solid ${colors.borderLight}`, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <button onClick={() => setConfirmCancel(true)} style={{ ...btn.danger, padding: "8px 16px", fontSize: 13 }}>
                {holdsSeat ? "Cancel registration" : "Leave waiting list"}
              </button>
              <span style={{ fontSize: 12.5, color: colors.textMuted }}>
                {holdsSeat ? "Releases your seat to the next passenger in the queue." : "Frees your place for the passengers behind you."}
              </span>
            </div>
          )}
        </ContentCard>

        {/* ── Next step + fees ── */}
        <aside className="tp-side">
          <ContentCard style={{ marginBottom: 0, padding: 0, overflow: "hidden" }}>
            <div style={{ height: 4, background: tone.bar }} />
            <div style={{ padding: 22, background: tone.bg }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: tone.text, marginBottom: 4 }}>Next step</div>
              <h3 style={{ ...sectionH, fontSize: 17, color: tone.text }}>{step.title}</h3>
              <p style={{ margin: "6px 0 0", fontSize: 13.5, lineHeight: 1.6, color: tone.text }}>{step.text}</p>
              {(step.action || step.secondary) && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
                  {step.action && <button onClick={() => navigate(step.action.to)} style={{ ...btn.primary, padding: "10px 18px" }}>{step.action.label}</button>}
                  {step.secondary && <button onClick={() => navigate(step.secondary.to)} style={{ ...ghostBtn, background: "#fff" }}>{step.secondary.label}</button>}
                </div>
              )}
            </div>
          </ContentCard>

          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={sectionH}>Fee history</h3>
            {fee_summary?.length > 0 ? (
              <ul className="tp-fees">
                {fee_summary.map((f, i) => (
                  <li key={i}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: colors.textPrimary }}>{f.semester}</div>
                      <div style={{ fontSize: 12, color: colors.textMuted }}>Challan {f.challan_number || "—"}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: colors.textPrimary }}>{formatPKR(f.amount)}</div>
                      <Pill label={f.is_verified ? "Verified" : "Pending"} variant={f.is_verified ? "success" : "warning"} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ margin: "10px 0 0", color: colors.textMuted, fontSize: 13 }}>No payments yet. Paid challans appear here once recorded.</p>
            )}
          </ContentCard>
        </aside>
      </div>
    </PageShell>
  );
}

export default StudentTransport;
