import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner, Field } from "../../components/ui";
import { selectStyle } from "../../styles/formStyles";
import { btn, colors, fonts } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import RegistrationStatus from "./RegistrationStatus";
import RegistrationSteps from "./RegistrationSteps";
import { getSemesters, createRegistration, getRegistration, getChallan, getEligibleRouteStops, getDashboard } from "../../services/transportService";
import { openSemesters, feeFor, formatPKR, formatDate } from "./transportHelpers";

// A passenger accumulates one row per attempt. The live registration is
// whichever is not cancelled; if every row is cancelled we keep the newest so
// the page can offer to register again.
function pickRegistration(payload) {
  const list = payload?.results ?? payload;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.find((r) => r.status !== "Cancelled") || list[list.length - 1];
}

const sectionH = { margin: 0, fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading };

function TransportRegistration() {
  const navigate = useNavigate();
  const [registration, setRegistration] = useState(null);
  const [semesters, setSemesters] = useState([]);
  const [profile, setProfile] = useState(null);
  const [eligibleStops, setEligibleStops] = useState([]);
  const [routeGeometries, setRouteGeometries] = useState({});
  const [stopsLoading, setStopsLoading] = useState(false);
  const [selectedRouteStop, setSelectedRouteStop] = useState("");
  const [selectedSemester, setSelectedSemester] = useState("");
  const [loading, setLoading] = useState(false);
  // True until the existing registration (and its challan) has been looked up. Without it the
  // empty form shows for a moment before an already-registered passenger's status replaces it.
  const [initializing, setInitializing] = useState(true);
  const [challan, setChallan] = useState(null);
  const [message, setMessage] = useState("");

  const loadEligibleStops = async (semesterId) => {
    setEligibleStops([]);
    setRouteGeometries({});
    setSelectedRouteStop("");
    setMessage("");
    if (!semesterId) return;
    setStopsLoading(true);
    try {
      const response = await getEligibleRouteStops(semesterId);
      setEligibleStops(response.data.route_stops || []);
      setRouteGeometries(response.data.route_geometries || {});
    } catch (err) {
      setMessage(err.response?.data?.detail || "No selectable route stops are available for this semester.");
    } finally {
      setStopsLoading(false);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        const [semRes, regRes] = await Promise.all([getSemesters(), getRegistration()]);
        const semData = semRes.data?.results ?? semRes.data;
        const all = Array.isArray(semData) ? semData : [];
        setSemesters(all);
        const reg = pickRegistration(regRes.data);
        if (reg) {
          setRegistration(reg);
          try { const cr = await getChallan(reg.id); setChallan(cr.data); } catch { setChallan(null); }
        }
        // One open semester is the normal case: pick it so the map shows straight away.
        const open = openSemesters(all);
        if ((!reg || reg.status === "Cancelled") && open.length === 1) {
          setSelectedSemester(String(open[0].id));
          loadEligibleStops(open[0].id);
        }
      } catch {
        setMessage("Could not load registration details. Refresh the page to try again.");
      } finally { setInitializing(false); }
    };
    loadData();
    // Only used for the fee shown before submitting; the form works without it.
    getDashboard().then((res) => setProfile(res.data?.profile || null)).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRouteStop || !selectedSemester) { setMessage("Choose a pickup stop from the list or the map."); return; }
    setLoading(true); setMessage("");
    try {
      await createRegistration({ route_stop_id: selectedRouteStop, semester_id: selectedSemester });

      // Re-read and pick the live row. Taking data[0] here would grab the
      // previous cancelled registration and leave the page showing the form
      // until a manual refresh.
      const regRes = await getRegistration();
      const reg = pickRegistration(regRes.data);
      setRegistration(reg);

      // A waitlisted passenger has no challan at all, so a miss is expected.
      if (reg) {
        try { const cr = await getChallan(reg.id); setChallan(cr.data); } catch { setChallan(null); }
      }
      setSelectedRouteStop("");
    } catch (err) {
      console.error(err.response?.data);
      setMessage(err.response?.data?.detail || "Registration failed. Check your selection and try again.");
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
  const selectableStops = eligibleStops.filter((stop) => !stop.is_campus);

  if (initializing) {
    return (
      <PageShell role="student" title="Transport Registration">
        <PageTitle sub="Register for transport this semester.">Transport Registration</PageTitle>
        <Spinner />
      </PageShell>
    );
  }

  const hasLiveRegistration = Boolean(registration) && status !== "cancelled";
  const open = openSemesters(semesters);
  const semester = semesters.find((s) => String(s.id) === String(selectedSemester));
  const fee = feeFor(semester, profile);
  const deadline = formatDate(semester?.registration_deadline, true);

  return (
    <PageShell role="student" title="Transport Registration">
      <PageTitle sub={hasLiveRegistration ? "Your registration for this semester and what happens next." : "Pick your pickup stop. Your route is assigned from it."}>Transport Registration</PageTitle>

      {/* A live registration gets the full status view; the form below is for everyone else. */}
      {hasLiveRegistration && <RegistrationStatus registration={registration} challan={challan} />}

      {status === "cancelled" && (
        <Banner variant="warning">
          Your previous registration was cancelled or its seat offer expired. You have not been charged, and you can register again below.
        </Banner>
      )}

      {/* Registration closed: say so instead of showing a form that cannot be submitted. */}
      {!hasLiveRegistration && open.length === 0 && (
        <div className="tp-layout">
          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={{ ...sectionH, fontSize: 19 }}>Registration is closed</h3>
            <p style={{ margin: "8px 0 18px", fontSize: 14, lineHeight: 1.6, color: colors.textSecondary, maxWidth: 560 }}>
              No semester is accepting registrations right now. You can register as soon as the transport office opens the next one, and you can look at the routes in the meantime.
            </p>
            <button onClick={() => navigate("/student/routes")} style={btn.primary}>Browse routes</button>
            {message && <p style={{ margin: "14px 0 0", fontSize: 13, color: colors.dangerText }}>{message}</p>}
          </ContentCard>
          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={{ ...sectionH, marginBottom: 14 }}>How it works</h3>
            <RegistrationSteps layout="column" />
          </ContentCard>
        </div>
      )}

      {/* Form: also shown after a cancellation or an expired seat offer. */}
      {!hasLiveRegistration && open.length > 0 && (
        <div className="reg-layout">
          <div className="reg-layout__form">
            <ContentCard style={{ marginBottom: 0 }}>
              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {open.length > 1 ? (
                  <Field label="Semester" required flex="0 0 auto">
                    <select value={selectedSemester} onChange={(e) => { setSelectedSemester(e.target.value); loadEligibleStops(e.target.value); }} style={selectStyle}>
                      <option value="">Select semester</option>
                      {open.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </Field>
                ) : (
                  <div>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: colors.textSecondary }}>Semester</div>
                    <div style={{ fontFamily: fonts.heading, fontSize: 18, fontWeight: 700, color: colors.textPrimary, marginTop: 2 }}>{open[0].name}</div>
                  </div>
                )}

                <Field label="Pickup stop" required flex="0 0 auto">
                  <select value={selectedRouteStop} onChange={(e) => setSelectedRouteStop(e.target.value)} style={selectStyle} disabled={!selectedSemester || stopsLoading}>
                    <option value="">{stopsLoading ? "Loading stops…" : selectedSemester ? "Choose a stop, or click one on the map" : "Select a semester first"}</option>
                    {selectableStops.map((stop) => <option key={stop.id} value={stop.id}>{stop.route_name}: {stop.stop_name}{stop.est_morning_eta ? ` (${stop.est_morning_eta})` : ""}</option>)}
                  </select>
                </Field>

                <div className="reg-summary">
                  <div className="reg-summary__row">
                    <span>Route</span>
                    <strong>{selectedStop ? selectedStop.route_name : "Set by your stop"}</strong>
                  </div>
                  <div className="reg-summary__row">
                    <span>Morning pickup</span>
                    <strong>{selectedStop?.est_morning_eta ? String(selectedStop.est_morning_eta).slice(0, 5) : "—"}</strong>
                  </div>
                  <div className="reg-summary__row">
                    <span>Your fee</span>
                    <strong>{semester ? formatPKR(fee) : "—"}</strong>
                  </div>
                  {deadline && (
                    <div className="reg-summary__row">
                      <span>Registration closes</span>
                      <strong>{deadline}</strong>
                    </div>
                  )}
                </div>

                <button type="submit" disabled={loading || !selectedRouteStop} style={{ ...btn.primary, padding: "11px 20px", fontSize: 14, opacity: loading || !selectedRouteStop ? 0.55 : 1, cursor: loading || !selectedRouteStop ? "not-allowed" : "pointer" }}>
                  {loading ? "Registering…" : "Register for transport"}
                </button>
                <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: colors.textMuted }}>
                  If the route is full you join its waiting list. Nothing is charged until a seat is confirmed.
                </p>
                {message && <p role="alert" style={{ margin: 0, fontSize: 13.5, color: colors.dangerText }}>{message}</p>}
              </form>
            </ContentCard>

            <ContentCard style={{ marginBottom: 0 }}>
              <h3 style={{ ...sectionH, marginBottom: 14 }}>How it works</h3>
              <RegistrationSteps layout="column" />
            </ContentCard>
          </div>

          <ContentCard style={{ marginBottom: 0, padding: 18 }} >
            <div className="reg-layout__map">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
                <h3 style={sectionH}>Routes and stops</h3>
                <span style={{ fontSize: 12.5, color: colors.textSecondary }}>
                  {selectedStop ? `Selected: ${selectedStop.stop_name}` : "Click a stop to select it"}
                </span>
              </div>
              {!selectedSemester ? (
                <div className="reg-map-empty">Select a semester to see its routes.</div>
              ) : stopsLoading ? (
                <div className="reg-map-empty"><Spinner /></div>
              ) : mapRoutes.length ? (
                <RouteMap routes={mapRoutes} selectedRouteId={selectedStop?.route_id} height={560} onStopSelect={(stop) => { if (!stop.isCampus) setSelectedRouteStop(String(stop.routeStopId)); }} />
              ) : (
                <div className="reg-map-empty">No routes with mapped stops are available for this semester yet.</div>
              )}
            </div>
          </ContentCard>
        </div>
      )}
    </PageShell>
  );
}

export default TransportRegistration;
