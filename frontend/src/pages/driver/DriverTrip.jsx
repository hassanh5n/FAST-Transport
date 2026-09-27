// frontend/src/pages/driver/DriverTrip.jsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner, Pill } from "../../components/ui";
import { btn, colors, fonts } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getDriverOverview, sendDriverLocation } from "../../services/transportService";
import { useBreakpoint } from "../../utils/useBreakpoint";

const PING_INTERVAL_MS = 15000;
// ponytail: one fixed arrival radius; make it per-stop if GPS drift marks stops early.
const ARRIVAL_RADIUS_M = 120;

const DIRECTIONS = [
  { key: "morning", label: "Morning pickup" },
  { key: "evening", label: "Evening drop-off" },
];

const GEO_ERRORS = {
  1: "Location access is blocked. Allow location for this site in your browser settings, then start the trip again.",
  2: "Your phone could not find its location. Move to open sky and check that location is switched on.",
  3: "Still waiting for a GPS fix…",
};

// Trip progress survives a refresh or an accidental tab close, per day and direction.
const progressKey = (direction) => `driver-trip:${new Date().toLocaleDateString("en-CA")}:${direction}`;
const loadProgress = (direction) => {
  try { return new Set(JSON.parse(localStorage.getItem(progressKey(direction)) || "[]")); }
  catch { return new Set(); }
};

function metersBetween(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

// "07:05:00" → today's Date at 07:05
const todayAt = (value) => {
  if (!value) return null;
  const [h, m] = value.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d;
};
const clock = (date) => date.toLocaleTimeString("en-PK", { hour: "numeric", minute: "2-digit" });
const inMinutes = (seconds) => (seconds < 60 ? "< 1 min" : `${Math.round(seconds / 60)} min`);
const ago = (ms) => {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`;
};

function scheduleVariance(arrival, scheduled) {
  if (!arrival || !scheduled) return null;
  const diff = Math.round((arrival - scheduled) / 60000);
  if (diff > 10) return { label: `${diff} min late`, variant: "danger" };
  if (diff > 3) return { label: `${diff} min late`, variant: "warning" };
  if (diff < -5) return { label: `${-diff} min early`, variant: "info" };
  return { label: "On time", variant: "success" };
}

export default function DriverTrip() {
  const isMobile = useBreakpoint(768);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [direction, setDirection] = useState(() => (new Date().getHours() < 12 ? "morning" : "evening"));
  const [reached, setReached] = useState(() => loadProgress(new Date().getHours() < 12 ? "morning" : "evening"));
  const [sharing, setSharing] = useState(false);
  const [position, setPosition] = useState(null);
  const [geoError, setGeoError] = useState("");
  const [live, setLive] = useState(null);       // last server reply + when it arrived
  const [sendError, setSendError] = useState("");
  const [, setTick] = useState(0);              // re-render "x s ago" labels

  useEffect(() => {
    getDriverOverview()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load your route. Please try again."));
  }, []);

  // ── Stops in driving order ──────────────────────────────────────────────
  const stops = useMemo(() => {
    const list = data?.stops || [];
    return direction === "morning" ? list : [...list].reverse();
  }, [data, direction]);
  const remaining = useMemo(() => stops.filter((s) => !reached.has(s.route_stop_id)), [stops, reached]);
  const nextStop = remaining[0];

  const saveProgress = useCallback((next) => {
    setReached(next);
    localStorage.setItem(progressKey(direction), JSON.stringify([...next]));
  }, [direction]);

  const markReached = useCallback((id) => saveProgress(new Set([...reached, id])), [reached, saveProgress]);
  const unmarkReached = (id) => { const next = new Set(reached); next.delete(id); saveProgress(next); };

  const switchDirection = (key) => {
    setDirection(key);
    setReached(loadProgress(key));
    setLive(null);
  };

  // ── GPS watch + screen wake lock while sharing ─────────────────────────
  useEffect(() => {
    if (!sharing) return undefined;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setGeoError("");
        setPosition({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          speed: pos.coords.speed,
          at: pos.timestamp,
        });
      },
      (err) => {
        setGeoError(GEO_ERRORS[err.code] || "Location is unavailable right now.");
        if (err.code === 1) setSharing(false);
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );
    // Location stops when the screen sleeps, so keep it awake during the trip.
    let wakeLock = null;
    navigator.wakeLock?.request("screen").then((lock) => { wakeLock = lock; }).catch(() => {});
    const tick = setInterval(() => setTick((n) => n + 1), 5000);
    return () => {
      navigator.geolocation.clearWatch(watchId);
      wakeLock?.release().catch(() => {});
      clearInterval(tick);
    };
  }, [sharing]);

  // ── Send the latest fix every 15 s; server stores it and returns ETAs ───
  const positionRef = useRef(null);
  const remainingRef = useRef([]);
  useEffect(() => { positionRef.current = position; }, [position]);
  useEffect(() => { remainingRef.current = remaining; }, [remaining]);

  const sendFix = useCallback(() => {
    const fix = positionRef.current;
    if (!fix) return;
    sendDriverLocation({
      latitude: fix.lat,
      longitude: fix.lng,
      remaining: remainingRef.current.map((s) => s.route_stop_id),
    })
      .then((res) => { setLive({ ...res.data, at: Date.now() }); setSendError(""); })
      .catch((err) => setSendError(
        err.response?.data?.detail || "Could not reach the server. Your location will be sent again in a few seconds."
      ));
  }, []);

  const hasFix = Boolean(position);
  useEffect(() => {
    if (!sharing || !hasFix) return undefined;
    sendFix();
    const id = setInterval(sendFix, PING_INTERVAL_MS);
    return () => clearInterval(id);
  }, [sharing, hasFix, sendFix]);

  // A stop was reached (or undone): refresh ETAs now instead of at the next tick.
  useEffect(() => {
    if (sharing) sendFix();
  }, [reached, sharing, sendFix]);

  // Auto-arrive when the bus is within the radius of the next stop.
  useEffect(() => {
    if (!position || !nextStop) return;
    if (metersBetween(position, { lat: nextStop.latitude, lng: nextStop.longitude }) <= ARRIVAL_RADIUS_M) {
      const timer = setTimeout(() => markReached(nextStop.route_stop_id), 0);
      return () => clearTimeout(timer);
    }
  }, [position, nextStop, markReached]);

  const startTrip = () => {
    if (!("geolocation" in navigator)) {
      setGeoError("This browser cannot share location. Open the portal in Chrome or Safari on your phone.");
      return;
    }
    setPosition(null);
    setGeoError("");
    setSendError("");
    setSharing(true);
  };

  const stopTrip = () => { setSharing(false); setLive(null); };

  // ── Render ──────────────────────────────────────────────────────────────
  if (error) return (
    <PageShell role="driver" title="Live Trip"><Banner variant="danger">{error}</Banner></PageShell>
  );
  if (!data) return <PageShell role="driver" title="Live Trip"><Spinner /></PageShell>;

  if (!data.assignment) return (
    <PageShell role="driver" title="Live Trip">
      <PageTitle sub="Live tracking is available once you have a bus and route.">Live Trip</PageTitle>
      <Banner variant="warning">You have not been assigned a bus for this semester yet. Please contact the transport office.</Banner>
    </PageShell>
  );

  const { assignment, route_map: routeMap, last_ping: lastPing } = data;
  const etaById = Object.fromEntries((live?.etas || []).map((e) => [e.route_stop_id, e]));
  const nextEta = nextStop && etaById[nextStop.route_stop_id];
  const markerPosition = position || (lastPing && { lat: lastPing.latitude, lng: lastPing.longitude });
  const speedKmh = position?.speed != null ? Math.round(position.speed * 3.6) : null;
  const allDone = stops.length > 0 && remaining.length === 0;

  return (
    <PageShell role="driver" title="Live Trip">
      <PageTitle sub={`${assignment.route.name} · Bus ${assignment.bus.bus_number}`}>Live Trip</PageTitle>

      {/* ── Trip controls ── */}
      <ContentCard>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div role="radiogroup" aria-label="Trip direction" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {DIRECTIONS.map(({ key, label }) => {
              const active = direction === key;
              return (
                <button
                  key={key}
                  role="radio"
                  aria-checked={active}
                  disabled={sharing}
                  onClick={() => switchDirection(key)}
                  style={{
                    padding: "7px 16px", borderRadius: 999,
                    border: `1px solid ${active ? colors.accent : colors.borderLight}`,
                    background: active ? colors.accent : "#fff",
                    color: active ? "#fff" : colors.textSecondary,
                    fontSize: 13, fontWeight: 500, fontFamily: fonts.body,
                    cursor: sharing ? "not-allowed" : "pointer",
                    opacity: sharing && !active ? 0.5 : 1,
                    transition: "all 0.15s",
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", width: isMobile ? "100%" : "auto" }}>
            {!sharing && reached.size > 0 && (
              <button onClick={() => saveProgress(new Set())} style={{ ...btn.ghost, flex: isMobile ? 1 : "none" }}>
                Reset progress
              </button>
            )}
            {sharing ? (
              <button onClick={stopTrip} style={{ ...btn.danger, flex: isMobile ? 1 : "none", padding: "11px 22px" }}>
                End trip
              </button>
            ) : (
              <button onClick={startTrip} style={{ ...btn.primary, flex: isMobile ? 1 : "none", padding: "11px 22px" }}>
                {reached.size > 0 ? "Resume trip" : "Start trip"}
              </button>
            )}
          </div>
        </div>

        <p style={{ margin: "14px 0 0", fontSize: 12.5, color: colors.textSecondary, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
            background: sharing ? (position ? colors.successDot : colors.warningDot) : colors.borderMid,
          }} />
          {!sharing && "Location sharing is off. Start the trip when the bus leaves."}
          {sharing && !position && "Finding your location…"}
          {sharing && position && `Sharing location · sent ${live ? ago(live.at) : "shortly"} · keep this page open while driving`}
        </p>
      </ContentCard>

      {geoError && <Banner variant={sharing ? "warning" : "danger"}>{geoError}</Banner>}
      {sendError && <Banner variant="warning">{sendError}</Banner>}
      {live?.is_off_route && (
        <Banner variant="danger">
          The bus is about {Math.round(live.distance_from_route_m ?? 0)} m away from the assigned route. The transport office has been alerted.
        </Banner>
      )}
      {allDone && (
        <Banner variant="success">
          All {stops.length} stops are done for the {direction === "morning" ? "morning pickup" : "evening drop-off"}. End the trip when the bus is parked.
        </Banner>
      )}

      {/* ── Glanceable readouts ── */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
        <Readout label="Next stop" value={nextStop?.name ?? (allDone ? "Done" : "—")} />
        <Readout
          label="Arriving"
          value={nextEta ? inMinutes(nextEta.eta_seconds) : "—"}
          sub={nextEta ? `${(nextEta.distance_m / 1000).toFixed(1)} km away` : undefined}
        />
        <Readout label="Speed" value={speedKmh != null ? `${speedKmh} km/h` : "—"} />
        <Readout
          label="GPS"
          value={position ? `±${Math.round(position.accuracy)} m` : "Off"}
          sub={!position && lastPing ? `Last seen ${ago(new Date(lastPing.recorded_at).getTime())}` : undefined}
          tone={position && position.accuracy > 100 ? colors.warningText : undefined}
        />
      </div>

      {/* ── Map + stop list ── */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "minmax(0, 1fr)" : "minmax(0, 1fr) 380px", gap: 16, alignItems: "start" }}>
        <ContentCard style={{ marginBottom: 0, padding: 12 }}>
          <RouteMap
            routes={routeMap ? [routeMap] : []}
            selectedRouteId={assignment.route.id}
            height={isMobile ? 300 : 540}
            livePosition={markerPosition}
          />
        </ContentCard>

        <ContentCard style={{ marginBottom: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
            <h3 style={cardHeading}>Stops</h3>
            <span style={{ fontSize: 12, color: colors.textSecondary, fontVariantNumeric: "tabular-nums" }}>
              {stops.length - remaining.length} of {stops.length} done
            </span>
          </div>

          {stops.length === 0 ? (
            <p style={{ margin: 0, fontSize: 13, color: colors.textSecondary }}>This route has no stops yet.</p>
          ) : (
            <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8, maxHeight: isMobile ? "none" : 470, overflowY: "auto" }}>
              {stops.map((stop) => (
                <TripStop
                  key={stop.route_stop_id}
                  stop={stop}
                  direction={direction}
                  done={reached.has(stop.route_stop_id)}
                  isNext={stop === nextStop}
                  eta={etaById[stop.route_stop_id]}
                  etaAt={live?.at}
                  onArrive={() => markReached(stop.route_stop_id)}
                  onUndo={() => unmarkReached(stop.route_stop_id)}
                />
              ))}
            </ol>
          )}

          {live?.eta_source === "estimate" && (
            <p style={{ margin: "12px 0 0", fontSize: 12, color: colors.textMuted }}>
              Road routing is unavailable, so arrival times are straight-line estimates.
            </p>
          )}
          <p style={{ margin: "12px 0 0", fontSize: 12, color: colors.textMuted }}>
            Stops tick off automatically within {ARRIVAL_RADIUS_M} m. See who boards where in the{" "}
            <Link to="/driver/passengers" style={{ color: colors.accent, fontWeight: 600, textDecoration: "none" }}>passenger list</Link>.
          </p>
        </ContentCard>
      </div>
    </PageShell>
  );
}

function TripStop({ stop, direction, done, isNext, eta, etaAt, onArrive, onUndo }) {
  const scheduled = todayAt(direction === "morning" ? stop.morning_eta : stop.evening_eta);
  const arrival = eta && etaAt ? new Date(etaAt + eta.eta_seconds * 1000) : null;
  const variance = scheduleVariance(arrival, scheduled);
  const count = stop.student_count;

  return (
    <li style={{
      display: "grid", gridTemplateColumns: "28px minmax(0, 1fr) auto", gap: 10, alignItems: "center",
      border: `1px solid ${isNext ? colors.accent : colors.borderLight}`,
      background: isNext ? colors.accentGlow : "#fff",
      borderRadius: 10, padding: "10px 12px",
      opacity: done ? 0.6 : 1,
      transition: "background 0.2s, border-color 0.2s",
    }}>
      {done ? (
        <span style={{ ...orderBadge, background: colors.successBg, color: colors.successText, border: "1px solid rgba(34,197,94,0.25)" }} aria-label="Done">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
        </span>
      ) : (
        <span style={orderBadge}>{stop.stop_order}</span>
      )}

      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: colors.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {stop.name}
        </div>
        <div style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
          {count} {count === 1 ? "student" : "students"}
          {scheduled && ` · scheduled ${clock(scheduled)}`}
        </div>
        {!done && variance && (
          <div style={{ marginTop: 6 }}><Pill label={variance.label} variant={variance.variant} /></div>
        )}
      </div>

      <div style={{ textAlign: "right", display: "grid", gap: 6, justifyItems: "end" }}>
        {done ? (
          <button onClick={onUndo} style={linkBtn}>Undo</button>
        ) : arrival ? (
          <div style={{ fontVariantNumeric: "tabular-nums" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: colors.textPrimary }}>{inMinutes(eta.eta_seconds)}</div>
            <div style={{ fontSize: 11, color: colors.textSecondary }}>{clock(arrival)}</div>
          </div>
        ) : (
          <span style={{ fontSize: 12, color: colors.textMuted }}>—</span>
        )}
        {isNext && (
          <button onClick={onArrive} style={{ ...btn.ghost, padding: "5px 10px", fontSize: 12, background: "#fff" }}>
            Mark arrived
          </button>
        )}
      </div>
    </li>
  );
}

function Readout({ label, value, sub, tone }) {
  return (
    <div style={{
      background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: 12,
      padding: "14px 16px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)", minWidth: 0,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: colors.textSecondary, marginBottom: 6 }}>
        {label}
      </div>
      <div style={{
        fontSize: 18, fontWeight: 700, color: tone || colors.textPrimary, fontFamily: fonts.heading,
        lineHeight: 1.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums",
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11.5, color: colors.textMuted, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────
const cardHeading = { margin: 0, fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading };

const orderBadge = {
  width: 26, height: 26, borderRadius: "50%", display: "grid", placeItems: "center",
  fontSize: 12, fontWeight: 700, color: colors.accent, background: colors.infoBg,
  border: "1px solid rgba(40,141,196,0.2)", fontVariantNumeric: "tabular-nums",
};

const linkBtn = {
  background: "none", border: "none", padding: 0, cursor: "pointer",
  fontSize: 12, fontWeight: 600, color: colors.accent, fontFamily: fonts.body,
};