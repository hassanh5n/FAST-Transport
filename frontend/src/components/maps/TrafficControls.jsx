// Traffic on the student and driver maps: a legend for the shared incidents, and a
// button that opens Google's live traffic map only when someone asks for it. That map
// cannot be shared or cached (Google's terms), and each opening is one map load.
import { Suspense, lazy, useEffect } from "react";
import { ModalLayer, Spinner } from "../ui";
import Icon from "../Icon";
import { colors, fonts, radius, shadow } from "../../theme";
import { GOOGLE_MAPS_API_KEY } from "./googleMaps";
import { TRAFFIC_TYPES, trafficAge } from "./trafficAlerts";
import { MAPBOX_TOKEN, MAPBOX_TRAFFIC_LEVELS } from "./mapboxTraffic";

/** Checkbox for the optional Mapbox traffic lines; renders nothing without a Mapbox token. */
export function MapboxTrafficToggle({ on, onChange, compact = false }) {
  if (!MAPBOX_TOKEN) return null;
  return (
    <div style={{ display: "grid", gap: 5 }}>
      <label style={styles.toggle} title="Mapbox has little live traffic data for Karachi, so most roads show as free-flowing">
        <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
        {compact ? "Mapbox" : "Mapbox traffic"}
        {!compact && <span style={styles.limited}>limited Karachi data</span>}
      </label>
      {on && !compact && (
        <div style={styles.kinds}>
          {MAPBOX_TRAFFIC_LEVELS.map(([level, label, color]) => (
            <span key={level} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <i style={{ width: 14, height: 3, borderRadius: 2, background: color }} />{label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const TrafficMap = lazy(() => import("./TrafficMap"));

/** Floating legend: toggles the incidents and opens the live traffic map. */
// compact: one row (toggle, count, live button) for narrow maps; each incident's popup names its type.
// mapbox: { on, onChange } adds the optional Mapbox traffic lines toggle.
export function TrafficLegend({ traffic, visible, onToggle, onOpenLive, style, compact = false, mapbox = null }) {
  const counts = traffic.alerts.reduce((all, a) => ({ ...all, [a.type]: (all[a.type] || 0) + 1 }), {});
  return (
    <div style={{ ...styles.legend, ...(compact ? styles.compact : null), ...style }}>
      <label style={styles.toggle} title={traffic.fetchedAt ? `Karachi-wide, ${trafficAge(traffic.fetchedAt)}` : undefined}>
        <input type="checkbox" checked={visible} onChange={(e) => onToggle(e.target.checked)} />
        {compact ? "Traffic" : "Traffic incidents"}
        <span style={styles.count}>{traffic.alerts.length}</span>
      </label>
      {visible && !compact && (
        <>
          <div style={styles.kinds}>
            {Object.entries(TRAFFIC_TYPES).map(([type, { label, color }]) => (
              <span key={type} style={{ display: "inline-flex", alignItems: "center", gap: 4, opacity: counts[type] ? 1 : 0.5 }}>
                <i style={{ width: 9, height: 9, borderRadius: "50%", background: color, border: "1.5px solid #fff", boxShadow: "0 0 0 1px rgba(0,0,0,0.12)" }} />
                {label}
              </span>
            ))}
          </div>
          <div style={styles.age}>
            {traffic.error && !traffic.fetchedAt ? traffic.error
              : traffic.alerts.length ? `Karachi-wide, ${trafficAge(traffic.fetchedAt)}${traffic.stale ? " (may be out of date)" : ""}`
              : traffic.fetchedAt ? `None reported, ${trafficAge(traffic.fetchedAt)}` : "Loading…"}
          </div>
        </>
      )}
      {mapbox && <MapboxTrafficToggle on={mapbox.on} onChange={mapbox.onChange} compact={compact} />}
      {GOOGLE_MAPS_API_KEY && (
        <button type="button" onClick={onOpenLive} style={styles.liveBtn}>
          <Icon name="map" size={13} /> {compact ? "Live" : "Live traffic"}
        </button>
      )}
    </div>
  );
}

/** Google's coloured live traffic for this route, in a window. */
export function LiveTrafficDialog({ title, routes, buses, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <ModalLayer>
      <div style={styles.overlay} onMouseDown={onClose}>
        <div role="dialog" aria-modal="true" aria-labelledby="live-traffic-title" style={styles.dialog} onMouseDown={(e) => e.stopPropagation()}>
          <div style={styles.head}>
            <div>
              <h3 id="live-traffic-title" style={styles.title}>{title}</h3>
              <p style={styles.sub}>Live road speeds from Google. Green is moving freely; red and dark red are slow or stopped.</p>
            </div>
            <button type="button" onClick={onClose} aria-label="Close live traffic" style={styles.close}><Icon name="x" size={16} /></button>
          </div>
          <Suspense fallback={<Spinner />}>
            <TrafficMap routes={routes} buses={buses} height={Math.min(520, window.innerHeight - 220)} showRoutesInitially />
          </Suspense>
        </div>
      </div>
    </ModalLayer>
  );
}

const styles = {
  legend: {
    position: "absolute", left: 12, bottom: 12, zIndex: 2, maxWidth: "calc(100% - 24px)",
    background: "rgba(255,255,255,0.97)", borderRadius: 10, padding: "9px 11px",
    boxShadow: "0 1px 6px rgba(11,45,66,0.22)", fontSize: 12, color: colors.textSecondary,
    display: "grid", gap: 7, fontFamily: fonts.body,
  },
  compact: { display: "flex", alignItems: "center", gap: 10, padding: "6px 8px 6px 10px" },
  toggle: { display: "flex", alignItems: "center", gap: 7, cursor: "pointer", fontWeight: 600, color: colors.textPrimary },
  limited: { fontWeight: 500, fontSize: 10.5, color: colors.warningText, background: colors.warningBg, borderRadius: radius.pill, padding: "1px 7px" },
  count: { marginLeft: 2, fontVariantNumeric: "tabular-nums", background: colors.neutralBg, color: colors.textSecondary, borderRadius: radius.pill, padding: "0 7px", fontSize: 11 },
  kinds: { display: "flex", gap: 9, flexWrap: "wrap", fontSize: 11 },
  age: { fontSize: 11, color: colors.textMuted },
  liveBtn: {
    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, border: `1px solid ${colors.borderMid}`,
    background: "#fff", color: colors.accent, borderRadius: 8, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
  },
  overlay: { position: "fixed", inset: 0, background: "rgba(11,45,66,0.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16 },
  dialog: { background: "#fff", borderRadius: radius.xl, boxShadow: shadow.modal, width: "100%", maxWidth: 860, padding: "18px 20px 20px", maxHeight: "92vh", overflowY: "auto" },
  head: { display: "flex", justifyContent: "space-between", gap: 16, marginBottom: 12 },
  title: { margin: "0 0 4px", fontFamily: fonts.heading, fontSize: 17, color: colors.textPrimary },
  sub: { margin: 0, fontSize: 13, color: colors.textSecondary, lineHeight: 1.5 },
  close: { width: 34, height: 34, border: `1px solid ${colors.borderMid}`, borderRadius: radius.pill, background: "#fff", color: colors.textSecondary, display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flex: "0 0 auto" },
};
