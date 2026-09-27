import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner, DetailRow } from "../../components/ui";
import { btn, colors, fonts } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getDriverOverview } from "../../services/transportService";
import { useBreakpoint } from "../../utils/useBreakpoint";

// "07:05:00" → "7:05 AM"
const fmtTime = (value) => {
  if (!value) return "—";
  const [h, m] = value.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString("en-PK", { hour: "numeric", minute: "2-digit" });
};

const LIVE_WINDOW_MS = 2 * 60 * 1000;

function gpsState(bus, lastPing) {
  if (bus.is_off_route) return { label: "Off route", dot: colors.dangerDot, text: "#fca5a5" };
  const fresh = lastPing && Date.now() - new Date(lastPing.recorded_at).getTime() < LIVE_WINDOW_MS;
  return fresh
    ? { label: "Live", dot: colors.successDot, text: "#86efac" }
    : { label: "Not sharing", dot: colors.warningDot, text: "#fcd34d" };
}

function DriverDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const isMobile = useBreakpoint(768);

  useEffect(() => {
    getDriverOverview()
      .then((res) => setData(res.data))
      .catch((err) => setError(
        err.response?.status === 403
          ? "This account is not linked to a driver. Please contact the transport office."
          : "Failed to load your assignment. Please try again."
      ));
  }, []);

  if (error) return (
    <PageShell role="driver" title="Driver Dashboard">
      <Banner variant="danger">{error}</Banner>
    </PageShell>
  );
  if (!data) return <PageShell role="driver" title="Driver Dashboard"><Spinner /></PageShell>;

  const { driver, assignment, stops, passengers, last_ping: lastPing, route_map: routeMap } = data;

  if (!assignment) return (
    <PageShell role="driver" title="Driver Dashboard">
      <PageTitle sub="Your bus, route and passengers will appear here once you are assigned.">Welcome, {driver.name}</PageTitle>
      <Banner variant="warning">
        You have not been assigned a bus for this semester yet. Please contact the transport office.
      </Banner>
      <ContentCard style={{ maxWidth: 520 }}>
        <h3 style={cardHeading}>Your details</h3>
        <DetailRow label="Name"       value={driver.name} />
        <DetailRow label="Phone"      value={driver.phone} />
        <DetailRow label="License No" value={driver.license_no} />
      </ContentCard>
    </PageShell>
  );

  const { bus, route, semester } = assignment;
  const seated = passengers.length;
  const maxAtStop = Math.max(1, ...stops.map((s) => s.student_count));
  const busiest = stops.reduce((best, s) => (s.student_count > (best?.student_count ?? 0) ? s : best), null);

  return (
    <PageShell role="driver" title="Driver Dashboard">
      <PageTitle sub={`Your duty assignment for ${semester}.`}>Welcome, {driver.name}</PageTitle>

      {bus.is_off_route && (
        <Banner variant="danger">
          The last location from your bus was away from the assigned route. The transport office has been alerted.
        </Banner>
      )}

      <DutyCard bus={bus} route={route} seated={seated} stops={stops.length} lastPing={lastPing} isMobile={isMobile} />

      <div className="dashboard-main-grid" style={{ marginBottom: 20 }}>
        {/* ── Stops & pickups ── */}
        <ContentCard style={{ marginBottom: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
            <h3 style={{ ...cardHeading, margin: 0 }}>Stops &amp; pickups</h3>
            <span style={{ fontSize: 12, color: colors.textSecondary }}>
              {seated} student{seated === 1 ? "" : "s"} across {stops.length} stop{stops.length === 1 ? "" : "s"}
            </span>
          </div>
          {stops.length === 0 ? (
            <p style={{ margin: 0, fontSize: 13, color: colors.textSecondary }}>
              This route has no stops yet. The transport office adds them in the route builder.
            </p>
          ) : (
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {stops.map((stop) => (
                <StopRow key={stop.route_stop_id} stop={stop} max={maxAtStop} isMobile={isMobile} />
              ))}
            </ol>
          )}
        </ContentCard>

        {/* ── Right column ── */}
        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={cardHeading}>Start your trip</h3>
            <p style={{ margin: "0 0 16px", fontSize: 13, color: colors.textSecondary, lineHeight: 1.6 }}>
              Share your location while driving so the office can follow the bus and you get live arrival times for every stop.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link to="/driver/trip" style={{ ...btn.primary, textDecoration: "none", display: "inline-block" }}>Start live trip</Link>
              <Link to="/driver/passengers" style={{ ...btn.ghost, textDecoration: "none", display: "inline-block" }}>Passenger list</Link>
            </div>
          </ContentCard>

          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={cardHeading}>Bus</h3>
            <DetailRow label="Bus Number"   value={bus.bus_number} />
            <DetailRow label="Model"        value={bus.model} />
            <DetailRow label="Capacity"     value={bus.capacity} />
            <DetailRow label="Seats Free"   value={Math.max(bus.capacity - seated, 0)} />
            <DetailRow label="Busiest Stop" value={busiest ? `${busiest.name} (${busiest.student_count})` : "—"} />
          </ContentCard>
        </div>
      </div>

      <ContentCard>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          <h3 style={{ ...cardHeading, margin: 0 }}>Route Map</h3>
          <span style={{ fontSize: 12, color: colors.textSecondary }}>{route.name}</span>
        </div>
        <RouteMap
          routes={routeMap ? [routeMap] : []}
          selectedRouteId={route.id}
          height={isMobile ? 280 : 360}
          livePosition={lastPing ? { lat: lastPing.latitude, lng: lastPing.longitude } : null}
        />
      </ContentCard>
    </PageShell>
  );
}

// ── Duty card — same surface as the student transport card ─────────────────
function DutyCard({ bus, route, seated, stops, lastPing, isMobile }) {
  const state = gpsState(bus, lastPing);
  const fill = bus.capacity ? Math.min(seated / bus.capacity, 1) : 0;

  return (
    <div style={{ ...dutyCard, padding: isMobile ? "22px 20px" : "26px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <p style={cardLabel}>Route</p>
          <p style={{ margin: 0, fontSize: isMobile ? 16 : 18, fontWeight: 700, color: "#fff", fontFamily: fonts.heading, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {route.name}
          </p>
        </div>
        <div style={statusChip}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: state.dot, boxShadow: `0 0 6px ${state.dot}` }} />
          <span style={{ fontSize: 11, fontWeight: 600, color: state.text }}>{state.label}</span>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16, marginTop: 28 }}>
        <div>
          <p style={cardLabel}>Bus</p>
          <p style={{ margin: 0, fontSize: isMobile ? 26 : 32, fontWeight: 800, color: "#fff", letterSpacing: "0.02em", fontFamily: fonts.heading, lineHeight: 1 }}>
            {bus.bus_number}
          </p>
          {bus.model && bus.model !== "N/A" && (
            <p style={{ margin: "6px 0 0", fontSize: 11, color: "rgba(255,255,255,0.45)", letterSpacing: "0.06em" }}>{bus.model}</p>
          )}
        </div>
        <div style={{ display: "flex", gap: 28, textAlign: "right" }}>
          {[
            { label: "Passengers", value: `${seated} / ${bus.capacity}` },
            { label: "Stops", value: stops },
          ].map(({ label, value }) => (
            <div key={label}>
              <p style={cardLabel}>{label}</p>
              <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#fff", fontVariantNumeric: "tabular-nums" }}>{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Seat fill: how full the bus is this semester */}
      <div style={{ marginTop: 20, height: 4, borderRadius: 999, background: "rgba(255,255,255,0.12)", overflow: "hidden" }} aria-hidden="true">
        <div style={{ width: `${fill * 100}%`, height: "100%", background: fill >= 1 ? "#fcd34d" : colors.accentLight, borderRadius: 999 }} />
      </div>
    </div>
  );
}

function StopRow({ stop, max, isMobile }) {
  const count = stop.student_count;
  return (
    <li style={{ ...stopRow, gridTemplateColumns: isMobile ? "28px minmax(0, 1fr) auto" : "28px minmax(0, 1fr) 132px 118px" }}>
      <span style={orderBadge}>{stop.stop_order}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: colors.textPrimary }}>{stop.name}</div>
        {isMobile ? (
          <div style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>
            AM {fmtTime(stop.morning_eta)} · PM {fmtTime(stop.evening_eta)}
          </div>
        ) : stop.address && stop.address !== "N/A" && (
          <div style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{stop.address}</div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }} title={`${count} student${count === 1 ? "" : "s"} board here`}>
        {!isMobile && (
          <div style={{ flex: 1, height: 6, borderRadius: 999, background: colors.neutralBg, overflow: "hidden" }} aria-hidden="true">
            <div style={{ width: `${(count / max) * 100}%`, height: "100%", background: count ? colors.accent : "transparent", borderRadius: 999 }} />
          </div>
        )}
        <span style={{ fontSize: 13, fontWeight: 700, color: count ? colors.textPrimary : colors.textMuted, fontVariantNumeric: "tabular-nums", minWidth: isMobile ? 0 : 22, textAlign: "right" }}>
          {count}{isMobile && <span style={{ fontWeight: 500, color: colors.textSecondary }}> {count === 1 ? "student" : "students"}</span>}
        </span>
      </div>
      {!isMobile && (
        <div style={{ fontSize: 12, color: colors.textSecondary, textAlign: "right", lineHeight: 1.5, fontVariantNumeric: "tabular-nums" }}>
          <div>AM {fmtTime(stop.morning_eta)}</div>
          <div>PM {fmtTime(stop.evening_eta)}</div>
        </div>
      )}
    </li>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────
const cardHeading = {
  margin: "0 0 14px",
  fontSize: "15px",
  fontWeight: 700,
  color: colors.textPrimary,
  fontFamily: fonts.heading,
};

const dutyCard = {
  background: "linear-gradient(135deg, #1a4a68 0%, #0b2d42 60%, #0f3a55 100%)",
  borderRadius: 18,
  boxShadow: "0 8px 32px rgba(11,45,66,0.28), 0 2px 8px rgba(11,45,66,0.16)",
  marginBottom: 24,
};

const cardLabel = {
  margin: "0 0 4px",
  fontSize: 9,
  color: "rgba(255,255,255,0.4)",
  letterSpacing: "0.1em",
  textTransform: "uppercase",
};

const statusChip = {
  display: "flex",
  alignItems: "center",
  gap: 7,
  padding: "5px 11px",
  borderRadius: 999,
  background: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.12)",
  flexShrink: 0,
};

const stopRow = {
  display: "grid",
  alignItems: "center",
  gap: 12,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 10,
  padding: "10px 12px",
  background: "#fff",
};

const orderBadge = {
  width: 26,
  height: 26,
  borderRadius: "50%",
  display: "grid",
  placeItems: "center",
  fontSize: 12,
  fontWeight: 700,
  color: colors.accent,
  background: colors.infoBg,
  border: "1px solid rgba(40,141,196,0.2)",
  fontVariantNumeric: "tabular-nums",
};

export default DriverDashboard;