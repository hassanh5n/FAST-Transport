import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Spinner, Pill, Banner, inputStyle } from "../../components/ui";
import { btn, colors, radius, fonts } from "../../theme";
import {
  listAllRouteChangeRequests,
  approveRouteChangeRequest,
  denyRouteChangeRequest,
} from "../../services/transportService";

const STATUS_VARIANT = { Pending: "warning", Approved: "success", Rejected: "danger", Cancelled: "neutral" };

const FILTERS = ["Pending", "Approved", "Rejected", "Cancelled", "All"];

export default function AdminRouteChangeRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [actionId, setActionId] = useState(null);
  const [remarks, setRemarks]   = useState({});
  const [filter, setFilter]     = useState("Pending");

  const fetchRequests = () =>
    listAllRouteChangeRequests()
      .then((r) => { setRequests(r.data); setLoading(false); })
      .catch(() => setLoading(false));

  useEffect(() => { fetchRequests(); }, []);

  const handleApprove = async (id) => {
    setActionId(id);
    try { await approveRouteChangeRequest(id, remarks[id] || ""); fetchRequests(); }
    catch (err) { alert(err.response?.data?.detail || "Approval failed."); }
    finally { setActionId(null); }
  };

  const handleDeny = async (id) => {
    if (!remarks[id]?.trim()) { alert("Please enter a reason before denying."); return; }
    setActionId(id);
    try { await denyRouteChangeRequest(id, remarks[id]); fetchRequests(); }
    catch (err) { alert(err.response?.data?.detail || "Denial failed."); }
    finally { setActionId(null); }
  };

  const filtered = requests.filter(r => filter === "All" || r.status === filter);

  return (
    <PageShell role="staff" title="Admin — Route Change Requests">
      <PageTitle sub="Review requests to change transport routes. Approving will free the old seat and allocate a new one.">
        Route Change Requests
      </PageTitle>

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px", flexWrap: "wrap" }}>
        {FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            style={{
              padding: "6px 16px", borderRadius: "999px",
              border: `1px solid ${filter === s ? colors.accent : colors.borderLight}`,
              background: filter === s ? colors.accent : "#fff",
              color: filter === s ? "#fff" : colors.textSecondary,
              fontSize: "13px", fontWeight: "500", cursor: "pointer", fontFamily: fonts.body,
              transition: "all 0.15s",
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? <Spinner /> : filtered.length === 0 ? (
        <p style={{ color: colors.textMuted, fontSize: "14px" }}>No {filter.toLowerCase()} requests.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {filtered.map((req) => (
            <div key={req.id} style={{
              border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg,
              padding: "20px", background: "#fff", boxShadow: "0 1px 3px rgba(11,45,66,0.05)",
            }}>
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <p style={{ margin: "0 0 3px", fontWeight: "600", fontSize: "15px", color: colors.textPrimary }}>
                    {(() => {
                        const u = req.registration?.student?.user;
                        const name = `${u?.first_name || ""} ${u?.last_name || ""}`.trim();
                        return name || u?.username || "—";
                      })()}
                    <span style={{ fontWeight: "400", color: colors.textSecondary, fontSize: "13px" }}>
                      {" "}· {req.registration?.student?.roll_number}
                    </span>
                  </p>
                  <p style={{ margin: 0, fontSize: "12.5px", color: colors.textMuted }}>
                    Semester: {req.registration?.semester?.name}
                  </p>
                </div>
                <Pill label={req.status} variant={STATUS_VARIANT[req.status] || "neutral"} />
              </div>

              {/* Route details */}
              <div style={{
                display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap",
                background: colors.pageBg, borderRadius: radius.md, padding: "12px 16px",
              }}>
                {[
                  ["Current Route", req.current_route?.name],
                  ["→", null],
                  ["Requested Route", req.requested_route?.name],
                  ["Requested Stop", req.requested_stop?.name],
                  ["Seats Available", req.available_seats],
                ].map(([label, val], i) =>
                  label === "→" ? (
                    <span key={i} style={{ fontSize: "18px", color: colors.textMuted }}>→</span>
                  ) : (
                    <div key={label} style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                      <span style={{ fontSize: "10px", fontWeight: "700", color: colors.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
                      <span style={{
                        fontSize: "13.5px", fontWeight: "600",
                        color: label === "Seats Available" ? (Number(val) > 0 ? colors.successText : colors.dangerText) : colors.textPrimary,
                      }}>
                        {val ?? "—"}
                      </span>
                    </div>
                  )
                )}
              </div>

              {req.admin_remarks && req.admin_remarks !== "N/A" && req.status !== "Pending" && (
                <p style={{ margin: "10px 0 0", fontSize: "12px", color: colors.textSecondary }}>
                  Admin note: {req.admin_remarks}
                </p>
              )}

              {/* Action row */}
              {req.status === "Pending" && (
                <div style={{ marginTop: "14px", display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    type="text"
                    placeholder="Remarks (required for denial)"
                    value={remarks[req.id] || ""}
                    onChange={(e) => setRemarks({ ...remarks, [req.id]: e.target.value })}
                    style={{ ...inputStyle, flex: "1 1 200px" }}
                  />
                  <button
                    onClick={() => handleApprove(req.id)}
                    disabled={actionId === req.id || req.available_seats === 0}
                    title={req.available_seats === 0 ? "No seats available on this route" : ""}
                    style={{ ...btn.primary, background: colors.successText, opacity: (actionId === req.id || req.available_seats === 0) ? 0.5 : 1 }}
                  >
                    {actionId === req.id ? "Processing…" : "✓ Approve"}
                  </button>
                  <button
                    onClick={() => handleDeny(req.id)}
                    disabled={actionId === req.id}
                    style={{ ...btn.danger, background: colors.dangerText, color: "#fff", border: "none", opacity: actionId === req.id ? 0.5 : 1 }}
                  >
                    ✗ Deny
                  </button>
                </div>
              )}

              <p style={{ margin: "10px 0 0", fontSize: "11px", color: colors.textMuted }}>
                Submitted: {new Date(req.requested_at).toLocaleString()}
                {req.resolved_at && ` · Resolved: ${new Date(req.resolved_at).toLocaleString()}`}
              </p>
            </div>
          ))}
        </div>
      )}
    </PageShell>
  );
}