import { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import {
  getMyRouteChangeRequests,
  submitRouteChangeRequest,
  cancelRouteChangeRequest,
} from "../../services/transportService";
import api from "../../services/api";

const STATUS_STYLE = {
  Pending:   { background: "#fff3cd", color: "#856404" },
  Approved:  { background: "#EAF3DE", color: "#3B6D11" },
  Rejected:  { background: "#fde8e8", color: "#9b1c1c" },
  Cancelled: { background: "#f3f4f6", color: "#6b7280" },
};

export default function StudentRouteChange() {
  const [requests, setRequests]           = useState([]);
  const [allStops, setAllStops]           = useState([]);
  const [currentRoute, setCurrentRoute]   = useState("");
  const [currentStop, setCurrentStop]     = useState("");
  const [form, setForm]                   = useState({ requested_stop_id: "" });
  const [submitting, setSubmitting]       = useState(false);
  const [cancelling, setCancelling]       = useState(null);
  const [error, setError]                 = useState("");
  const [success, setSuccess]             = useState("");

  const fetchRequests = () =>
    getMyRouteChangeRequests().then((r) => setRequests(r.data)).catch(() => {});

  useEffect(() => {
    fetchRequests();
    // Load all stops for the dropdown
    api.get("/api/stops/").then((r) => setAllStops(r.data)).catch(() => {});
    // Get student's current route and stop from dashboard
    api.get("/api/dashboard/").then((r) => {
      const reg = r.data?.active_registration;
      if (reg?.route) setCurrentRoute(reg.route);
      if (reg?.stop) setCurrentStop(reg.stop);
    }).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(""); setSuccess("");
    if (!form.requested_stop_id) {
      setError("Please select a new stop.");
      return;
    }
    setSubmitting(true);
    try {
      await submitRouteChangeRequest({ requested_stop_id: form.requested_stop_id });
      setSuccess("Route change request submitted! The system will auto-assign the best route for your stop.");
      setForm({ requested_stop_id: "" });
      fetchRequests();
    } catch (err) {
      setError(err.response?.data?.detail || JSON.stringify(err.response?.data) || "Submission failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (id) => {
    setCancelling(id);
    try {
      await cancelRouteChangeRequest(id);
      fetchRequests();
    } catch (err) {
      alert(err.response?.data?.detail || "Cancel failed.");
    } finally {
      setCancelling(null);
    }
  };

  const hasPending = requests.some((r) => r.status === "Pending");

  return (
    <div style={{ display: "flex" }}>
      <Sidebar role="student" />
      <div style={{ flex: 1 }}>
        <Navbar title="Route Change Request" />
        <div style={{ padding: "24px", maxWidth: "760px" }}>
          <h2 style={{ marginBottom: "4px" }}>Request a Route Change</h2>
          <p style={{ color: "#6b7280", fontSize: "14px", marginBottom: "24px" }}>
            Select your new stop below. The system will automatically determine the best route for you.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", alignItems: "start" }}>

            {/* Left: form */}
            <div>
              {currentRoute && (
                <div style={currentInfoStyle}>
                  <span style={{ fontSize: "12px", fontWeight: 500, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.04em" }}>Current Assignment</span>
                  <p style={{ margin: "6px 0 0", fontSize: "14px" }}>
                    <strong>Route:</strong> {currentRoute} &nbsp;·&nbsp; <strong>Stop:</strong> {currentStop}
                  </p>
                </div>
              )}

              {hasPending && (
                <div style={{ ...errorBanner, background: "#fff3cd", borderColor: "#fcd34d", color: "#92400e", marginBottom: "20px" }}>
                  ⚠ You already have a pending request. Cancel it before submitting a new one.
                </div>
              )}

              {!hasPending && (
                <div style={cardStyle}>
                  <h3 style={{ margin: "0 0 16px", fontSize: "15px" }}>New Request</h3>
                  {error   && <div style={errorBanner}>{error}</div>}
                  {success && <div style={successBanner}>{success}</div>}
                  <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                    <div style={fieldStyle}>
                      <label style={labelStyle}>New Stop</label>
                      <select
                        style={selectStyle}
                        value={form.requested_stop_id}
                        onChange={(e) => setForm({ requested_stop_id: e.target.value })}
                      >
                        <option value="">— Select your new stop —</option>
                        {allStops.filter((s) => s.name !== currentStop).map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                      <span style={{ fontSize: "12px", color: "#9ca3af", marginTop: "4px" }}>
                        Route will be auto-assigned based on stop proximity.
                      </span>
                    </div>
                    <button type="submit" disabled={submitting} style={submitBtnStyle}>
                      {submitting ? "Submitting…" : "Submit Request"}
                    </button>
                  </form>
                </div>
              )}
            </div>

            {/* Right: request history */}
            <div>
              <h3 style={{ margin: "0 0 12px", fontSize: "15px" }}>My Requests</h3>
              {requests.length === 0 ? (
                <p style={{ color: "#9ca3af", fontSize: "14px" }}>No requests yet.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {requests.map((req) => (
                    <div key={req.id} style={requestCardStyle}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <p style={{ margin: "0 0 4px", fontWeight: "600", fontSize: "14px" }}>
                            {req.current_route?.name} → {req.requested_route?.name || "Auto-assigned"}
                          </p>
                          <p style={{ margin: "0 0 4px", fontSize: "13px", color: "#6b7280" }}>
                            New Stop: {req.requested_stop?.name} · Semester: {req.registration?.semester?.name}
                          </p>
                          {req.admin_remarks && req.admin_remarks !== "N/A" && (
                            <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#6b7280" }}>
                              Admin note: {req.admin_remarks}
                            </p>
                          )}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px" }}>
                          <span style={{ ...badgeStyle, ...STATUS_STYLE[req.status] }}>{req.status}</span>
                          {req.status === "Pending" && (
                            <button
                              style={cancelBtnStyle}
                              disabled={cancelling === req.id}
                              onClick={() => handleCancel(req.id)}
                            >
                              {cancelling === req.id ? "Cancelling…" : "Cancel"}
                            </button>
                          )}
                        </div>
                      </div>
                      <p style={{ margin: "8px 0 0", fontSize: "11px", color: "#9ca3af" }}>
                        Submitted: {new Date(req.requested_at).toLocaleDateString()}
                        {req.resolved_at && ` · Resolved: ${new Date(req.resolved_at).toLocaleDateString()}`}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}

const currentInfoStyle = { background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: "10px", padding: "14px 18px", marginBottom: "20px" };
const cardStyle        = { border: "1px solid #e5e7eb", borderRadius: "10px", padding: "20px", marginBottom: "8px", background: "#fff" };
const requestCardStyle = { border: "1px solid #e5e7eb", borderRadius: "10px", padding: "16px", background: "#fff" };
const fieldStyle       = { display: "flex", flexDirection: "column", gap: "6px" };
const labelStyle       = { fontSize: "12px", fontWeight: "500", color: "#374151", textTransform: "uppercase", letterSpacing: "0.04em" };
const selectStyle      = { padding: "9px 12px", borderRadius: "8px", border: "1px solid #d1d5db", fontSize: "14px", color: "#111827", background: "#fff" };
const submitBtnStyle   = { padding: "10px", background: "#288dc4", color: "#fff", border: "none", borderRadius: "8px", fontSize: "14px", fontWeight: "500", cursor: "pointer" };
const cancelBtnStyle   = { padding: "5px 12px", background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: "6px", fontSize: "12px", cursor: "pointer", fontWeight: "500" };
const badgeStyle       = { fontSize: "11px", fontWeight: "600", padding: "3px 10px", borderRadius: "20px" };
const errorBanner      = { background: "#fef2f2", border: "1px solid #fecaca", color: "#dc2626", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", marginBottom: "12px" };
const successBanner    = { background: "#f0fdf4", border: "1px solid #86efac", color: "#16a34a", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", marginBottom: "12px" };