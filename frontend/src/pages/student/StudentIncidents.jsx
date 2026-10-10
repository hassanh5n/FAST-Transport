import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Banner, Pill } from "../../components/ui";
import { colors, fonts, radius, btn, input, shadow } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";
import api from "../../services/api";
import { CAMPUS, addCampusMarker } from "../../components/maps/campus";
import { circleRing } from "../../components/maps/incidents";

const Icon = ({ name, size = 18, color = "currentColor" }) => {
  const icons = {
    alertCircle: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
    alertTriangle: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
    trafficJam: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
    robbery: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19.69 14a6.9 6.9 0 0 0 .31-2V5l-8-3-3.16 1.18"/><path d="M4.73 4.73L4 5v7c0 6 8 10 8 10a20.29 20.29 0 0 0 5.62-4.38"/><line x1="1" y1="1" x2="23" y2="23"/></svg>,
    roadClosure: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>,
    flooding: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="16" y1="13" x2="16" y2="21"/><line x1="8" y1="13" x2="8" y2="21"/><line x1="12" y1="15" x2="12" y2="23"/><path d="M20 16.58A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25"/></svg>,
    accident: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
    other: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
    map: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>,
    pin: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>,
    bell: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
    clipboard: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>,
  };
  return icons[name] || null;
};

const SEVERITY_CONFIG = {
  low:    { color: "#F59E0B", label: "Low",    icon: "alertCircle", desc: "Minor inconvenience" },
  medium: { color: "#F97316", label: "Medium", icon: "alertCircle", desc: "Moderate disruption" },
  high:   { color: "#EF4444", label: "High",   icon: "alertTriangle", desc: "Serious threat / danger" },
};

const INCIDENT_TYPES = [
  { value: "traffic_jam",  label: "Traffic Jam",  icon: "trafficJam" },
  { value: "robbery",      label: "Robbery",      icon: "robbery" },
  { value: "road_closure", label: "Road Closure", icon: "roadClosure" },
  { value: "flooding",     label: "Flooding",     icon: "flooding" },
  { value: "accident",     label: "Accident",     icon: "accident" },
  { value: "other",        label: "Other",        icon: "other" },
];

const statusVariant = (s) =>
  s === "Approved" ? "success" : s === "Rejected" ? "danger" : "warning";

function buildCircleGeoJSON(lng, lat, radiusM) {
  return { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [circleRing(lng, lat, radiusM)] } }] };
}

export default function StudentIncidents() {
  const mapContainer = useRef(null);
  const mapRef       = useRef(null);
  const markerRef    = useRef(null);
  const isMobile     = useBreakpoint(900);

  const [form, setForm] = useState({
    incident_type: "traffic_jam", severity: "low",
    radius_meters: 300, description: "", latitude: null, longitude: null,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitMsg,  setSubmitMsg]  = useState(null);
  const [myIncidents, setMyIncidents] = useState([]);
  const [loadingList, setLoadingList] = useState(true);

  const fetchMyIncidents = useCallback(() => {
    setLoadingList(true);
    api.get("/api/incidents/")
      .then(res => setMyIncidents(Array.isArray(res.data) ? res.data : []))
      .catch(() => {})
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => { fetchMyIncidents(); }, [fetchMyIncidents]);

  useEffect(() => {
    if (mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: CAMPUS.center, zoom: CAMPUS.zoom,
    });
    mapRef.current = map;
    addCampusMarker(map);
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      map.addSource("incident-preview", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "incident-preview-fill", type: "fill", source: "incident-preview",
        paint: { "fill-color": "#F59E0B", "fill-opacity": 0.25 } });
      map.addLayer({ id: "incident-preview-border", type: "line", source: "incident-preview",
        paint: { "line-color": "#F59E0B", "line-width": 2.5, "line-opacity": 0.9 } });
    });

    map.on("click", (e) => {
      const { lng, lat } = e.lngLat;
      setForm(prev => ({ ...prev, latitude: lat, longitude: lng }));
      if (markerRef.current) {
        markerRef.current.setLngLat([lng, lat]);
      } else {
        const el = document.createElement("div");
        el.style.cssText = "width:34px;height:34px;border-radius:50%;background:#EF4444;border:3px solid white;box-shadow:0 2px 10px rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;cursor:pointer;";
        el.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>';
        markerRef.current = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([lng, lat]).addTo(map);
      }
    });

    return () => { if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
  }, []);

  const { latitude, longitude, radius_meters, severity } = form;

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("incident-preview");
    if (!src) return;
    if (!latitude || !longitude) { src.setData({ type: "FeatureCollection", features: [] }); return; }
    const color = SEVERITY_CONFIG[severity]?.color || "#F59E0B";
    src.setData(buildCircleGeoJSON(longitude, latitude, radius_meters));
    map.setPaintProperty("incident-preview-fill",   "fill-color", color);
    map.setPaintProperty("incident-preview-border", "line-color", color);
  }, [latitude, longitude, radius_meters, severity]);

  const handleChange = (field, value) => setForm(prev => ({ ...prev, [field]: value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.latitude || !form.longitude) {
      setSubmitMsg({ type: "danger", text: "Please click on the map to set the incident location first." });
      return;
    }
    setSubmitting(true); setSubmitMsg(null);
    try {
      await api.post("/api/incidents/", {
        incident_type: form.incident_type, severity: form.severity,
        latitude: Number(form.latitude.toFixed(6)),
        longitude: Number(form.longitude.toFixed(6)),
        radius_meters: form.radius_meters, description: form.description,
      });
      setSubmitMsg({ type: "success", text: "Report submitted! It will appear on the live map once approved by an admin." });
      setForm(prev => ({ ...prev, description: "", latitude: null, longitude: null }));
      if (markerRef.current) { markerRef.current.remove(); markerRef.current = null; }
      const src = mapRef.current?.getSource("incident-preview");
      if (src) src.setData({ type: "FeatureCollection", features: [] });
      fetchMyIncidents();
    } catch (err) {
      const data = err.response?.data;
      let msg = "Failed to submit report.";
      if (data) {
        if (data.detail) msg = data.detail;
        else msg = typeof data === "object" ? JSON.stringify(data) : data;
      }
      setSubmitMsg({ type: "danger", text: msg });
    } finally { setSubmitting(false); }
  };

  const sevCfg = SEVERITY_CONFIG[form.severity];

  return (
    <PageShell role="student" title="Report an Incident">
      <PageTitle sub="Pin the location on the map, describe the incident, and submit for admin review.">
        Report an Incident
      </PageTitle>

      {submitMsg && <Banner variant={submitMsg.type} style={{ marginBottom: 16 }}>{submitMsg.text}</Banner>}

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 420px", gap: 20, marginBottom: 28, alignItems: "start" }}>

        {/* MAP */}
        <div style={{ borderRadius: radius.lg, border: `1px solid ${colors.borderLight}`, overflow: "hidden", boxShadow: shadow.card }}>
          <div style={{ padding: "11px 16px", background: "linear-gradient(135deg,#0b2d42,#1a4a68)", color: "#fff", fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 9 }}>
            <span style={{ display:"flex" }}><Icon name="map" size={20} /></span>
            <span style={{ flex: 1, display:"flex", alignItems:"center", gap:6 }}>
              {form.latitude ? <><Icon name="pin" size={14} /> {`${form.latitude.toFixed(5)}, ${form.longitude.toFixed(5)}`}</> : "Click anywhere on the map to place the incident pin"}
            </span>
            {form.latitude && (
              <button type="button" onClick={() => {
                setForm(p => ({ ...p, latitude: null, longitude: null }));
                if (markerRef.current) { markerRef.current.remove(); markerRef.current = null; }
              }} style={{ background: "rgba(255,255,255,0.12)", border: "1px solid rgba(255,255,255,0.2)", color: "#fff", borderRadius: 6, padding: "3px 10px", fontSize: 11, cursor: "pointer", fontWeight: 600 }}>
                ✕ Clear
              </button>
            )}
          </div>
          <div ref={mapContainer} style={{ height: isMobile ? 300 : 450 }} />
          <div style={{ padding: "9px 14px", background: colors.tableHeaderBg, borderTop: `1px solid ${colors.borderLight}`, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 11.5, color: colors.textSecondary }}>
            {Object.entries(SEVERITY_CONFIG).map(([k, v]) => (
              <span key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 11, height: 11, borderRadius: "50%", background: v.color, display: "inline-block", border: "1px solid rgba(0,0,0,0.12)" }} />
                <strong>{v.label}</strong>: {v.desc}
              </span>
            ))}
          </div>
        </div>

        {/* FORM */}
        <form onSubmit={handleSubmit} style={{ background: colors.cardBg, borderRadius: radius.lg, border: `1px solid ${colors.borderLight}`, boxShadow: shadow.card, padding: "24px 22px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 38, height: 38, borderRadius: 10, background: "linear-gradient(135deg,#EF4444,#dc2626)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 4px 12px rgba(239,68,68,0.3)" }}>
              <Icon name="bell" size={20} color="white" />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading }}>Incident Details</div>
              <div style={{ fontSize: 12, color: colors.textMuted }}>Fill in the form and submit for admin review</div>
            </div>
          </div>

          {/* Type grid */}
          <FormField label="Incident Type">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {INCIDENT_TYPES.map(t => (
                <button key={t.value} type="button" onClick={() => handleChange("incident_type", t.value)} style={{
                  padding: "9px 8px", borderRadius: radius.md,
                  border: form.incident_type === t.value ? `2px solid ${colors.accent}` : `1px solid ${colors.borderMid}`,
                  background: form.incident_type === t.value ? colors.accentGlow : "#fff",
                  cursor: "pointer", fontSize: 12,
                  fontWeight: form.incident_type === t.value ? 700 : 500,
                  color: form.incident_type === t.value ? colors.accent : colors.textSecondary,
                  transition: "all 0.15s", display: "flex", alignItems: "center", gap: 6,
                }}>
                  <span style={{ display:"flex" }}><Icon name={t.icon} size={16} /></span> {t.label}
                </button>
              ))}
            </div>
          </FormField>

          {/* Severity */}
          <FormField label="Severity Level">
            <div style={{ display: "flex", gap: 8 }}>
              {Object.entries(SEVERITY_CONFIG).map(([k, v]) => (
                <button key={k} type="button" onClick={() => handleChange("severity", k)} style={{
                  flex: 1, padding: "10px 4px", borderRadius: radius.md,
                  border: form.severity === k ? `2px solid ${v.color}` : `1px solid ${colors.borderMid}`,
                  background: form.severity === k ? `${v.color}1a` : "#fff",
                  cursor: "pointer", fontSize: 11.5, fontWeight: 700,
                  color: form.severity === k ? v.color : colors.textMuted,
                  transition: "all 0.18s", display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                }}>
                  <span style={{ display:"flex" }}><Icon name={v.icon} size={22} /></span>{v.label}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 6, padding: "7px 12px", borderRadius: radius.sm, background: `${sevCfg.color}14`, border: `1px solid ${sevCfg.color}45`, fontSize: 12, color: sevCfg.color, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: sevCfg.color, display: "inline-block" }} />
              {sevCfg.desc} — circle will be <strong style={{ fontFamily: "monospace", marginLeft: 4 }}>{sevCfg.color}</strong>
            </div>
          </FormField>

          {/* Radius */}
          <FormField label={`Affected Radius — ${form.radius_meters} m`}>
            <input type="range" min={50} max={2000} step={50} value={form.radius_meters}
              onChange={e => handleChange("radius_meters", Number(e.target.value))}
              style={{ width: "100%", accentColor: sevCfg.color, cursor: "pointer", height: 5 }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: colors.textMuted }}>
              <span>50 m</span><span>Small ‹ › Large</span><span>2,000 m</span>
            </div>
          </FormField>

          {/* Description */}
          <FormField label="Description (optional)">
            <textarea rows={3} placeholder="Add extra details about the incident..." value={form.description}
              onChange={e => handleChange("description", e.target.value)}
              style={{ ...input, resize: "vertical", lineHeight: 1.5, minHeight: 72 }} />
          </FormField>

          {/* Location indicator */}
          <div style={{
            padding: "10px 14px", borderRadius: radius.md,
            background: form.latitude ? colors.successBg : colors.warningBg,
            border: `1px solid ${form.latitude ? "#86efac" : "#fcd34d"}`,
            fontSize: 13, color: form.latitude ? colors.successText : colors.warningText, fontWeight: 600,
          }}>
            {form.latitude
              ? `✅ Location set at ${form.latitude.toFixed(5)}, ${form.longitude.toFixed(5)}`
              : "⚠️ No location — click on the map to place the pin"}
          </div>

          <button type="submit" disabled={submitting} style={{
            ...btn.primary, padding: "13px 20px", fontSize: 14, fontWeight: 700, opacity: submitting ? 0.7 : 1,
            background: "linear-gradient(135deg,#EF4444,#dc2626)", boxShadow: "0 4px 16px rgba(239,68,68,0.4)",
            transition: "all 0.2s", letterSpacing: "-0.01em",
          }}>
            {submitting ? "Submitting…" : <span style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}><Icon name="bell" size={16} /> Submit Incident Report</span>}
          </button>
        </form>
      </div>

      {/* My reports */}
      <div style={{ background: colors.cardBg, borderRadius: radius.lg, border: `1px solid ${colors.borderLight}`, boxShadow: shadow.card, overflow: "hidden" }}>
        <div style={{ padding: "15px 22px", borderBottom: `1px solid ${colors.borderLight}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading }}>My Submitted Reports</div>
            <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>Track the review status of your incident reports here</div>
          </div>
          <button onClick={fetchMyIncidents} style={{ ...btn.ghost, padding: "5px 14px", fontSize: 12 }}>↻ Refresh</button>
        </div>

        {loadingList ? (
          <div style={{ padding: 40, textAlign: "center", color: colors.textMuted }}>Loading…</div>
        ) : myIncidents.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: colors.textMuted, fontSize: 14 }}>
            <div style={{ display:"flex", justifyContent:"center", marginBottom: 8, color: colors.borderMid }}><Icon name="clipboard" size={32} /></div>
            No incident reports yet. Use the form above to submit one.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: colors.tableHeaderBg }}>
                  {["#","Type","Severity","Location","Radius","Description","Status","Submitted","Admin Notes"].map(h => (
                    <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 10.5, fontWeight: 700, color: colors.textMuted, letterSpacing: "0.06em", textTransform: "uppercase", borderBottom: `1px solid ${colors.borderLight}`, whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {myIncidents.map((inc, i) => {
                  const sev  = SEVERITY_CONFIG[inc.severity] || SEVERITY_CONFIG.low;
                  const type = INCIDENT_TYPES.find(t => t.value === inc.incident_type);
                  return (
                    <tr key={inc.id} style={{ background: i%2===0 ? "#fff" : colors.tableRowAlt }}>
                      <td style={{ ...td, color: colors.textMuted }}>{inc.id}</td>
                      <td style={td}><span style={{ display:"flex", alignItems:"center", gap:6 }}><Icon name={type?.icon} size={14} color={colors.textSecondary} /> {inc.incident_type_display}</span></td>
                      <td style={td}>
                        <span style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"3px 10px", borderRadius:radius.pill, background:`${sev.color}1a`, color:sev.color, fontWeight:700, fontSize:11 }}>
                          <Icon name={sev.icon} size={12} /> {sev.label}
                        </span>
                      </td>
                      <td style={{ ...td, fontSize:11.5, color:colors.textSecondary }}>{parseFloat(inc.latitude).toFixed(4)},&nbsp;{parseFloat(inc.longitude).toFixed(4)}</td>
                      <td style={td}>{inc.radius_meters} m</td>
                      <td style={{ ...td, maxWidth:160, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{inc.description || <span style={{ color:colors.textMuted }}>—</span>}</td>
                      <td style={td}><Pill label={inc.status} variant={statusVariant(inc.status)} /></td>
                      <td style={{ ...td, whiteSpace:"nowrap", fontSize:12, color:colors.textSecondary }}>{new Date(inc.created_at).toLocaleString()}</td>
                      <td style={{ ...td, maxWidth:160, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", color:colors.textSecondary, fontSize:12 }}>{inc.admin_notes || <span style={{ color:colors.textMuted }}>—</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageShell>
  );
}

function FormField({ label, children }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
      <label style={{ fontSize:11, fontWeight:700, color:colors.textMuted, letterSpacing:"0.07em", textTransform:"uppercase" }}>{label}</label>
      {children}
    </div>
  );
}

const td = {
  padding: "11px 14px",
  borderBottom: `1px solid ${colors.tableRowBorder}`,
  color: colors.textPrimary,
  verticalAlign: "middle",
};

