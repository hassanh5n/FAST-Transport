import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Pill } from "../../components/ui";
import { btn, colors} from "../../theme";
import { getComplaints, resolveComplaint } from "../../services/transportService";
import { can } from "../../utils/permissions";

function AdminComplaintsPage() {
  const [complaints, setComplaints] = useState([]);
  const [responses, setResponses] = useState({});
  const [resolvingId, setResolvingId] = useState(null);
  const canReply = can("complaints", "manage");

  const fetchComplaints = () =>
    getComplaints().then((res) => setComplaints(res.data)).catch(() => alert("Failed to fetch complaints."));

  useEffect(() => { fetchComplaints(); }, []);

  const handleResolve = async (id) => {
    const adminResponse = (responses[id] || "").trim();
    if (!adminResponse) { alert("Please add an admin response before resolving."); return; }
    setResolvingId(id);
    try {
      await resolveComplaint(id, { admin_response: adminResponse });
      setResponses(prev => ({ ...prev, [id]: "" }));
      fetchComplaints();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to resolve complaint.");
    } finally { setResolvingId(null); }
  };

  const formatDateTime = (v) => v ? new Date(v).toLocaleString() : "-";
  const isResolved = (s) => (s || "").toLowerCase() === "resolved";

  const columns = [
    { key: "student",      label: "Student" },
    { key: "subject",      label: "Subject" },
    { key: "description",  label: "Description" },
    { key: "priority",     label: "Priority" },
    { key: "status",       label: "Status" },
    { key: "submitted_at", label: "Submitted" },
    { key: "resolved_by",  label: "Resolved By" },
    { key: "resolved_at",  label: "Resolved At" },
    { key: "admin_response", label: "Admin Response" },
    { key: "action",       label: "Action" },
  ];

  const rows = complaints
    .slice()
    .sort((a, b) => {
      const ar = isResolved(a.status) ? 1 : 0, br = isResolved(b.status) ? 1 : 0;
      if (ar !== br) return ar - br;
      return new Date(b.created_at) - new Date(a.created_at);
    })
    .map((c) => {
      const resolved = isResolved(c.status);
      return {
        ...c,
        student: (() => {
          const u = c.submitted_by;
          const name = `${u?.first_name || ""} ${u?.last_name || ""}`.trim();
          return name || u?.username || "N/A";
        })(),
        status:       <Pill label={resolved ? "Resolved" : "Pending"} variant={resolved ? "success" : "warning"} />,
        submitted_at: formatDateTime(c.created_at),
        resolved_by:  c.resolved_by?.username || "-",
        resolved_at:  formatDateTime(c.resolved_at),
        admin_response: (c.admin_response && c.admin_response !== "N/A") ? c.admin_response : "-",
        action: resolved ? (
          <span style={{ color: colors.textMuted, fontSize: "13px" }}>Completed</span>
        ) : !canReply ? (
          <span style={{ color: colors.textMuted, fontSize: "13px" }}>View only</span>
        ) : (
          <div style={{ display: "grid", gap: "6px", minWidth: "220px" }}>
            <textarea
              rows={2}
              placeholder="Write response..."
              value={responses[c.id] || ""}
              onChange={(e) => setResponses(prev => ({ ...prev, [c.id]: e.target.value }))}
              style={{ resize: "vertical", padding: "7px 10px", border: `1px solid ${colors.borderMid}`, borderRadius: "8px", fontSize: "13px", fontFamily: "inherit" }}
            />
            <button
              onClick={() => handleResolve(c.id)}
              disabled={resolvingId === c.id}
              style={{ ...btn.primary, background: colors.successText, opacity: resolvingId === c.id ? 0.7 : 1 }}
            >
              {resolvingId === c.id ? "Resolving…" : "Resolve"}
            </button>
          </div>
        ),
      };
    });

  return (
    <PageShell role="staff" title="Admin — Complaints">
      <PageTitle sub="Review student complaints and resolve them with an admin response.">Complaint Resolution</PageTitle>
      <Table columns={columns} rows={rows} />
    </PageShell>
  );
}

export default AdminComplaintsPage;