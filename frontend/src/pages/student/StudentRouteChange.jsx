import { useEffect, useState } from "react";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Banner } from "../../components/ui";
import { colors, fonts, radius, btn } from "../../theme";
import {
  getMyRouteChangeRequests,
  submitRouteChangeRequest,
  cancelRouteChangeRequest,
} from "../../services/transportService";
import api from "../../services/api";

const STATUS_COLORS = {
  Pending:   { bg: "#fff3cd", color: "#856404" },
  Approved:  { bg: "#EAF3DE", color: "#3B6D11" },
  Rejected:  { bg: "#fde8e8", color: "#9b1c1c" },
  Cancelled: { bg: "#f3f4f6", color: "#6b7280" },
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
    <PageShell role="student" title="Route Change Request">
      <PageTitle sub="Select your new stop below. The system will automatically determine the best route for you.">
        Request a Route Change
      </PageTitle>

      <div className="grid-2col">

        {/* Left: form */}
        <div>
          {currentRoute && (
            <div style={{
              background: colors.infoBg, border: `1px solid rgba(40,141,196,0.2)`,
              borderRadius: radius.lg, padding: "14px 18px", marginBottom: "20px",
            }}>
              <span style={{ fontSize: "12px", fontWeight: 500, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: "0.04em" }}>Current Assignment</span>
              <p style={{ margin: "6px 0 0", fontSize: "14px", color: colors.textPrimary }}>
                <strong>Route:</strong> {currentRoute} &nbsp;·&nbsp; <strong>Stop:</strong> {currentStop}
              </p>
            </div>
          )}

          {hasPending && (
            <Banner variant="warning">
              ⚠ You already have a pending request. Cancel it before submitting a new one.
            </Banner>
          )}

          {!hasPending && (
            <ContentCard>
              <h3 style={{ margin: "0 0 16px", fontSize: "15px", fontWeight: "700", fontFamily: fonts.heading, color: colors.textPrimary }}>New Request</h3>
              {error   && <Banner variant="danger">{error}</Banner>}
              {success && <Banner variant="success">{success}</Banner>}
              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <label style={{ fontSize: "11px", fontWeight: "600", color: colors.textSecondary, letterSpacing: "0.04em", textTransform: "uppercase" }}>New Stop</label>
                  <select
                    style={{
                      padding: "9px 12px", borderRadius: radius.md,
                      border: `1px solid ${colors.borderMid}`, fontSize: "14px",
                      color: colors.textPrimary, background: "#fff",
                      width: "100%", boxSizing: "border-box",
                    }}
                    value={form.requested_stop_id}
                    onChange={(e) => setForm({ requested_stop_id: e.target.value })}
                  >
                    <option value="">— Select your new stop —</option>
                    {allStops.filter((s) => s.name !== currentStop).map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <span style={{ fontSize: "12px", color: colors.textMuted, marginTop: "4px" }}>
                    Route will be auto-assigned based on stop proximity.
                  </span>
                </div>
                <button type="submit" disabled={submitting} style={{ ...btn.primary, width: "100%" }}>
                  {submitting ? "Submitting…" : "Submit Request"}
                </button>
              </form>
            </ContentCard>
          )}
        </div>

        {/* Right: request history */}
        <div>
          <h3 style={{ margin: "0 0 12px", fontSize: "15px", fontWeight: "700", fontFamily: fonts.heading, color: colors.textPrimary }}>My Requests</h3>
          {requests.length === 0 ? (
            <p style={{ color: colors.textMuted, fontSize: "14px" }}>No requests yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {requests.map((req) => (
                <ContentCard key={req.id} style={{ marginBottom: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px" }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p style={{ margin: "0 0 4px", fontWeight: "600", fontSize: "14px", color: colors.textPrimary }}>
                        {req.current_route?.name} → {req.requested_route?.name || "Auto-assigned"}
                      </p>
                      <p style={{ margin: "0 0 4px", fontSize: "13px", color: colors.textSecondary }}>
                        New Stop: {req.requested_stop?.name} · Semester: {req.registration?.semester?.name}
                      </p>
                      {req.admin_remarks && req.admin_remarks !== "N/A" && (
                        <p style={{ margin: "4px 0 0", fontSize: "12px", color: colors.textMuted }}>
                          Admin note: {req.admin_remarks}
                        </p>
                      )}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px", flexShrink: 0 }}>
                      <span style={{ fontSize: "11px", fontWeight: "600", padding: "3px 10px", borderRadius: "20px", ...(STATUS_COLORS[req.status] || STATUS_COLORS.Cancelled) }}>{req.status}</span>
                      {req.status === "Pending" && (
                        <button
                          style={{ ...btn.danger, padding: "5px 12px", fontSize: "12px" }}
                          disabled={cancelling === req.id}
                          onClick={() => handleCancel(req.id)}
                        >
                          {cancelling === req.id ? "Cancelling…" : "Cancel"}
                        </button>
                      )}
                    </div>
                  </div>
                  <p style={{ margin: "8px 0 0", fontSize: "11px", color: colors.textMuted }}>
                    Submitted: {new Date(req.requested_at).toLocaleDateString()}
                    {req.resolved_at && ` · Resolved: ${new Date(req.resolved_at).toLocaleDateString()}`}
                  </p>
                </ContentCard>
              ))}
            </div>
          )}
        </div>

      </div>
    </PageShell>
  );
}