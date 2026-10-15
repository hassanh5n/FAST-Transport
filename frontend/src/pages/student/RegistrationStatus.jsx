// What a student sees on the Register page once they have a live registration:
// where it stands, the one thing to do next, and what they registered for.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ContentCard } from "../../components/PageShell";
import Icon from "../../components/Icon";
import RouteMap from "../../components/maps/RouteMap";
import { btn, colors, fonts } from "../../theme";
import { getRoutesMap } from "../../services/transportService";

const STEPS = ["Registered", "Seat reserved", "Fee paid", "Confirmed"];
const TONES = {
  success: { bg: colors.successBg, text: colors.successText, dot: colors.successDot },
  warning: { bg: colors.warningBg, text: colors.warningText, dot: colors.warningDot },
  info:    { bg: colors.infoBg,    text: colors.infoText,    dot: colors.infoDot },
  danger:  { bg: colors.dangerBg,  text: colors.dangerText,  dot: colors.dangerDot },
};

// `step` is how many of STEPS are complete; null hides the progress bar.
function viewFor(registration, challan) {
  const status = registration.status?.toLowerCase();
  const challanPath = `/student/challan/${registration.id}`;
  const paid = challan?.status === "paid";
  if (status === "approved") {
    return { tone: "success", icon: "check", step: 4, title: "You're registered", text: `Your transport registration for ${registration.semester_name} is confirmed and your seat is reserved.`, action: { label: "View My Transport", to: "/student/transport" } };
  }
  if (status === "payment_submitted" || (status === "pending" && paid)) {
    return { tone: "info", icon: "clock", step: 3, title: "Payment received", text: "Your payment has been recorded. The transport office is verifying it, and your seat is confirmed as soon as they do.", action: { label: "View Challan", to: challanPath } };
  }
  if (status === "seat held") {
    return { tone: "warning", icon: "clock", step: 2, title: "Seat held: payment needed", text: "A seat is reserved for you, but it is not confirmed until the fee is paid. If payment is not received by the deadline the seat passes to the next student on the waiting list.", action: { label: "Pay Fee (View Challan)", to: challanPath } };
  }
  if (status === "waitlisted") {
    return { tone: "info", icon: "clock", step: 1, title: "On the waiting list", text: "This route is currently full, so you are queued for the next available seat. You have not been charged. A challan is issued only once a seat is confirmed for you, and you will be notified the moment one opens up.", action: { label: "View my position", to: "/student/transport" } };
  }
  if (status === "rejected") {
    return { tone: "danger", icon: "x", step: null, title: "Registration rejected", text: "Please contact the transport office for details.", action: { label: "Contact the transport office", to: "/student/complaints" } };
  }
  return { tone: "warning", icon: "clock", step: 2, title: "Registration pending", text: "Please pay the transport fee using your challan. Your seat is confirmed after the transport office reviews the payment.", action: { label: "Pay Fee (View Challan)", to: challanPath } };
}

const formatDate = (value, withTime = false) =>
  value ? new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) }) : "—";
const eta = (value) => (value ? String(value).slice(0, 5) : "—");
const sameName = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

const muted = { fontSize: 13, color: colors.textSecondary };

function Progress({ done, tone }) {
  return (
    <ol style={{ display: "grid", gridTemplateColumns: `repeat(${STEPS.length}, 1fr)`, listStyle: "none", margin: 0, padding: 0 }}>
      {STEPS.map((label, index) => {
        const complete = index < done;
        const current = index === done;
        return (
          <li key={label} aria-current={current ? "step" : undefined} style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 8, textAlign: "center" }}>
            {/* connector to the previous step */}
            {index > 0 && <span aria-hidden="true" style={{ position: "absolute", top: 15, left: "calc(-50% + 22px)", right: "calc(50% + 22px)", height: 2, borderRadius: 2, background: index <= done ? colors.successDot : colors.borderLight }} />}
            <span style={{
              position: "relative", width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13, fontWeight: 700,
              background: complete ? colors.successDot : "#fff",
              color: complete ? "#fff" : current ? tone.text : colors.textMuted,
              border: `2px solid ${complete ? colors.successDot : current ? tone.dot : colors.borderMid}`,
              boxShadow: current ? `0 0 0 4px ${tone.bg}` : "none",
            }}>
              {complete ? <Icon name="check" size={16} /> : index + 1}
            </span>
            <span style={{ fontSize: 12.5, fontWeight: complete || current ? 700 : 500, color: complete || current ? colors.textPrimary : colors.textMuted, padding: "0 4px" }}>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Detail({ label, children }) {
  return (
    <div className="reg-detail" style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "11px 0" }}>
      <dt style={muted}>{label}</dt>
      <dd style={{ margin: 0, fontSize: 13.5, fontWeight: 600, color: colors.textPrimary, textAlign: "right", overflowWrap: "anywhere" }}>{children}</dd>
    </div>
  );
}

export default function RegistrationStatus({ registration, challan }) {
  const navigate = useNavigate();
  const [route, setRoute] = useState(undefined); // undefined while loading, null when it cannot be shown
  const view = viewFor(registration, challan);
  const tone = TONES[view.tone];
  const paid = challan?.status === "paid" || registration.is_paid;
  const unpaidDue = !paid && challan?.payment_due_at;

  useEffect(() => {
    let live = true;
    getRoutesMap()
      .then((res) => { if (live) setRoute((res.data?.routes || []).find((item) => sameName(item.name, registration.route_name)) || null); })
      .catch(() => { if (live) setRoute(null); });
    return () => { live = false; };
  }, [registration.route_name]);

  const myStop = route?.stops.find((stop) => sameName(stop.name, registration.stop_name));

  return (
    <div style={{ display: "grid", gap: 20 }}>
      {/* Status, with the progress underneath in the same card */}
      <ContentCard style={{ marginBottom: 0, padding: 0, overflow: "hidden" }}>
        <section style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", padding: 24, background: tone.bg }}>
          <span aria-hidden="true" style={{ flex: "0 0 auto", width: 52, height: 52, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: "#fff", color: tone.dot }}>
            <Icon name={view.icon} size={26} />
          </span>
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: 20, fontWeight: 700, fontFamily: fonts.heading, color: tone.text, letterSpacing: "-0.01em" }}>{view.title}</h3>
            <p style={{ margin: "6px 0 0", fontSize: 13.5, lineHeight: 1.6, color: tone.text, maxWidth: 560 }}>{view.text}</p>
            {unpaidDue && view.step === 2 && <p style={{ margin: "8px 0 0", fontSize: 13, fontWeight: 700, color: tone.text }}>Pay by {formatDate(challan.payment_due_at, true)}</p>}
          </div>
          <button type="button" onClick={() => navigate(view.action.to)} style={{ ...btn.primary, flex: "0 0 auto", padding: "11px 20px" }}>{view.action.label}</button>
        </section>
        {view.step !== null && (
          <div style={{ padding: "22px 24px" }}>
            <Progress done={view.step} tone={tone} />
          </div>
        )}
      </ContentCard>

      {/* What they registered for, beside their route */}
      <ContentCard style={{ marginBottom: 0 }}>
        <div className="grid-2col" style={{ alignItems: "center" }}>
          <dl style={{ margin: 0 }}>
            <Detail label="Semester">{registration.semester_name || "—"}</Detail>
            <Detail label="Route">{registration.route_name || "Not assigned yet"}</Detail>
            <Detail label="Pickup stop">{registration.stop_name || "—"}{myStop?.est_morning_eta ? ` · ${eta(myStop.est_morning_eta)}` : ""}</Detail>
            <Detail label="Transport fee">
              PKR {Number(challan?.amount ?? registration.fee_amount).toLocaleString()}
              <span style={{ marginLeft: 8, color: paid ? colors.successText : colors.warningText }}>{paid ? "Paid" : view.step === 1 ? "Not due yet" : "Unpaid"}</span>
            </Detail>
          </dl>
          {route
            ? <RouteMap routes={[route]} selectedRouteId={route.id} height={230} />
            : <p style={{ ...muted, margin: 0, textAlign: "center" }}>{route === undefined ? "Loading your route…" : "The map for this route is not available right now."}</p>}
        </div>
      </ContentCard>
    </div>
  );
}
