import { useEffect, useState } from "react";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner, Field, ErrorText } from "../../components/ui";
import { selectStyle } from "../../styles/formStyles";
import { btn, colors } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import RegistrationStatus from "./RegistrationStatus";
import { getSemesters, createRegistration, getRegistration, getChallan, getEligibleRouteStops } from "../../services/transportService";

// A student accumulates one row per attempt. The live registration is
// whichever is not cancelled; if every row is cancelled we keep the newest so
// the page can offer to register again.
function pickRegistration(payload) {
  const list = payload?.results ?? payload;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.find((r) => r.status !== "Cancelled") || list[list.length - 1];
}

function TransportRegistration() {
  const [registration, setRegistration] = useState(null);
  const [semesters, setSemesters] = useState([]);
  const [eligibleStops, setEligibleStops] = useState([]);
  const [routeGeometries, setRouteGeometries] = useState({});
  const [selectedRouteStop, setSelectedRouteStop] = useState("");
  const [selectedSemester, setSelectedSemester] = useState("");
  const [loading, setLoading] = useState(false);
  // True until the existing registration (and its challan) has been looked up. Without it the
  // empty form shows for a moment before an already-registered student's status replaces it.
  const [initializing, setInitializing] = useState(true);
  const [challan, setChallan] = useState(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const loadData = async () => {
      try {
        const [semRes, regRes] = await Promise.all([getSemesters(), getRegistration()]);
        const semData = semRes.data?.results ?? semRes.data;
        setSemesters(Array.isArray(semData) ? semData : []);
        const reg = pickRegistration(regRes.data);
        if (reg) {
          setRegistration(reg);
          try { const cr = await getChallan(reg.id); setChallan(cr.data); } catch { setChallan(null); }
        }
      } catch { alert("Failed to load data"); }
      finally { setInitializing(false); }
    };
    loadData();
  }, []);

  const loadEligibleStops = async (semesterId) => {
    setEligibleStops([]);
    setRouteGeometries({});
    setSelectedRouteStop("");
    if (!semesterId) return;
    try {
      const response = await getEligibleRouteStops(semesterId);
      setEligibleStops(response.data.route_stops || []);
      setRouteGeometries(response.data.route_geometries || {});
    } catch (err) {
      setMessage(err.response?.data?.detail || "No selectable route stops are available for this semester.");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRouteStop || !selectedSemester) { setMessage("Please select both semester and pickup stop on the map."); return; }
    setLoading(true); setMessage("");
    try {
      await createRegistration({ route_stop_id: selectedRouteStop, semester_id: selectedSemester });

      // Re-read and pick the live row. Taking data[0] here would grab the
      // previous cancelled registration and leave the page showing the form
      // until a manual refresh.
      const regRes = await getRegistration();
      const reg = pickRegistration(regRes.data);
      setRegistration(reg);

      // A waitlisted student has no challan at all, so a miss is expected.
      if (reg) {
        try { const cr = await getChallan(reg.id); setChallan(cr.data); } catch { setChallan(null); }
      }

      setSelectedRouteStop("");
      setMessage("Registration submitted successfully!");
    } catch (err) {
      console.error(err.response?.data);
      setMessage("Failed to submit registration.");
    } finally { setLoading(false); }
  };

  const status = registration?.status?.toLowerCase();
  const mapRoutes = Object.values(eligibleStops.reduce((groups, routeStop) => {
    const key = routeStop.route_id;
    if (!groups[key]) groups[key] = { id: key, name: routeStop.route_name, description: routeStop.route_description, geometry: routeGeometries[key], stops: [] };
    groups[key].stops.push({
      ...routeStop,
      route_stop_id: routeStop.id,
      id: routeStop.stop_id,
      name: routeStop.stop_name,
      longitude: routeStop.longitude,
      latitude: routeStop.latitude,
    });
    return groups;
  }, {}));
  const selectedStop = eligibleStops.find((stop) => String(stop.id) === String(selectedRouteStop));

  if (initializing) {
    return (
      <PageShell role="student" title="Transport Registration" maxWidth="860px">
        <PageTitle sub="Register for transport service this semester.">Transport Registration</PageTitle>
        <Spinner />
      </PageShell>
    );
  }

  const hasLiveRegistration = Boolean(registration) && status !== "cancelled";

  return (
    <PageShell role="student" title="Transport Registration" maxWidth={hasLiveRegistration ? "920px" : "860px"}>
      <PageTitle sub={hasLiveRegistration ? "Your registration for this semester and what happens next." : "Register for transport service this semester."}>Transport Registration</PageTitle>

      {/* A live registration gets the full status view; the form below is for everyone else. */}
      {hasLiveRegistration && <RegistrationStatus registration={registration} challan={challan} />}

      {status === "cancelled" && (
        <Banner variant="warning">
          <strong>Registration Cancelled</strong> — Your previous registration was
          cancelled or its seat offer expired. You have not been charged, and you
          can register again below while registration is open.
        </Banner>
      )}

      {/* Form — also shown after a cancellation or an expired seat offer, so a
          student can rejoin the queue without contacting the office. */}
      {(!registration || status === "cancelled") && (
        <div className="grid-2col">
          <ContentCard>
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <Field label="Semester" required>
                <select value={selectedSemester} onChange={(e) => { setSelectedSemester(e.target.value); loadEligibleStops(e.target.value); }} style={selectStyle}>
                  <option value="">Select Semester</option>
                  {Array.isArray(semesters) && semesters.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Pickup Stop" required>
                <select value={selectedRouteStop} onChange={(e) => setSelectedRouteStop(e.target.value)} style={selectStyle} disabled={!selectedSemester}>
                  <option value="">Select a route and stop</option>
                  {eligibleStops.filter((stop) => !stop.is_campus).map((stop) => <option key={stop.id} value={stop.id}>{stop.route_name} — {stop.stop_name}{stop.est_morning_eta ? ` (${stop.est_morning_eta})` : ""}</option>)}
                </select>
              </Field>
              {selectedStop && <p style={{ margin: 0, color: colors.successText, fontSize: 13 }}><strong>Selected:</strong> {selectedStop.route_name} · {selectedStop.stop_name}{selectedStop.est_morning_eta ? ` · AM ${selectedStop.est_morning_eta}` : ""}</p>}
              <button type="submit" disabled={loading} style={{ ...btn.primary, alignSelf: "flex-start", minWidth: "180px", opacity: loading ? 0.6 : 1 }}>
                {loading ? "Submitting…" : "Submit Registration"}
              </button>
              {message && <p style={{ margin: 0, fontSize: "13.5px", color: message.includes("success") ? colors.successText : colors.dangerText }}>{message}</p>}
            </form>
          </ContentCard>

          {selectedSemester && (
            <ContentCard style={{ gridColumn: "1 / -1" }}>
              <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>Choose your route and stop on the map</h3>
              <p style={{ margin: "0 0 14px", color: colors.textSecondary, fontSize: 13 }}>Click a route to focus it, then choose the exact route-stop pair from the list above. This prevents ambiguous stop assignments.</p>
              {mapRoutes.length ? <RouteMap routes={mapRoutes} height={400} onStopSelect={(stop) => { if (!stop.isCampus) setSelectedRouteStop(String(stop.routeStopId)); }} /> : <Banner variant="warning">No assigned routes have selectable mapped stops for this semester.</Banner>}
            </ContentCard>
          )}

          <div style={{ background: colors.infoBg, border: `1px solid rgba(40,141,196,0.2)`, borderRadius: "12px", padding: "24px" }}>
            <h4 style={{ margin: "0 0 16px", fontSize: "14px", fontWeight: "700", color: colors.infoText }}>How Registration Works</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {[
                { step: "01", text: "Select your active semester and nearest pickup stop." },
                { step: "02", text: "A route is auto-assigned based on your stop." },
                { step: "03", text: "Pay the transport challan fee to proceed." },
                { step: "04", text: "Admin verifies payment and your seat is allocated." },
              ].map(({ step, text }) => (
                <div key={step} style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
                  <span style={{ fontSize: "11px", fontWeight: "800", color: colors.accent, background: "#fff", border: `1px solid rgba(40,141,196,0.2)`, borderRadius: "6px", padding: "2px 7px", flexShrink: 0 }}>{step}</span>
                  <p style={{ margin: 0, fontSize: "13px", color: colors.infoText, lineHeight: 1.6 }}>{text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}

export default TransportRegistration;
