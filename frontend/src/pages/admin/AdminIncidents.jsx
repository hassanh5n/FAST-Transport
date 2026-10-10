import { useEffect, useRef, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Pill } from "../../components/ui";
import { btn, colors } from "../../theme";
import api from "../../services/api";
import Icon from "../../components/Icon";
import IncidentsMap from "../../components/maps/IncidentsMap";
import { SEVERITY_COLORS, REJECTED_COLOR } from "../../components/maps/incidents";

const LEGEND = [["Low", SEVERITY_COLORS.low], ["Medium", SEVERITY_COLORS.medium], ["High", SEVERITY_COLORS.high], ["Rejected", REJECTED_COLOR]];

function AdminIncidents() {
  const [incidents, setIncidents] = useState([]);
  const [adminNotes, setAdminNotes] = useState({});
  const [processingId, setProcessingId] = useState(null);
  const [viewingId, setViewingId] = useState(null);
  const mapSection = useRef(null);

  const viewOnMap = (id) => {
    setViewingId(id);
    mapSection.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const fetchIncidents = () => {
    api.get("/api/incidents/")
      .then((res) => setIncidents(res.data))
      .catch(() => alert("Failed to fetch incidents."));
  };

  useEffect(() => {
    fetchIncidents();
  }, []);

  const handleApprove = async (id) => {
    setProcessingId(id);
    try {
      await api.post(`/api/incidents/${id}/approve/`);
      fetchIncidents();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to approve incident.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id) => {
    const notes = (adminNotes[id] || "").trim();
    if (!notes) {
      alert("Please provide admin notes when rejecting an incident.");
      return;
    }
    setProcessingId(id);
    try {
      await api.post(`/api/incidents/${id}/reject/`, { admin_notes: notes });
      setAdminNotes(prev => ({ ...prev, [id]: "" }));
      fetchIncidents();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to reject incident.");
    } finally {
      setProcessingId(null);
    }
  };

  const statusVariant = (s) => (s === "Approved" ? "success" : s === "Rejected" ? "danger" : "warning");
  const isPending = (s) => s === "Pending";

  const viewing = incidents.find((inc) => inc.id === viewingId) || null;

  const columns = [
    { key: "student",     label: "Student" },
    { key: "type",        label: "Type" },
    { key: "severity",    label: "Severity" },
    { key: "location",    label: "Location" },
    { key: "description", label: "Description" },
    { key: "status",      label: "Status" },
    { key: "submitted",   label: "Submitted" },
    { key: "actions",     label: "Actions" },
  ];

  const rows = incidents
    .slice()
    .sort((a, b) => {
      const ap = isPending(a.status) ? 0 : 1;
      const bp = isPending(b.status) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return new Date(b.created_at) - new Date(a.created_at);
    })
    .map((inc) => {
      const studentName = inc.reported_by?.first_name || inc.reported_by?.username || "N/A";
      const pending = isPending(inc.status);

      return {
        id: inc.id,
        student: studentName,
        type: inc.incident_type_display,
        severity: (
          <span style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: "4px",
            fontSize: "11px",
            fontWeight: "bold",
            color: inc.severity === "high" ? "#EF4444" : inc.severity === "medium" ? "#F97316" : "#F59E0B",
            background: inc.severity === "high" ? "#fee2e2" : inc.severity === "medium" ? "#ffedd5" : "#fef3c7"
          }}>
            {inc.severity.toUpperCase()}
          </span>
        ),
        location: (
          <div style={{ display: "grid", gap: 6, justifyItems: "start" }}>
            <span>{parseFloat(inc.latitude).toFixed(4)}, {parseFloat(inc.longitude).toFixed(4)} ({inc.radius_meters}m)</span>
            <button
              type="button"
              onClick={() => viewOnMap(inc.id)}
              aria-pressed={viewingId === inc.id}
              style={{ ...(viewingId === inc.id ? btn.primary : btn.ghost), display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", fontSize: "12px", whiteSpace: "nowrap" }}
            >
              <Icon name="pin" size={13} /> {viewingId === inc.id ? "Viewing on map" : "View on map"}
            </button>
          </div>
        ),
        description: inc.description || "-",
        status: <Pill label={inc.status} variant={statusVariant(inc.status)} />,
        submitted: new Date(inc.created_at).toLocaleString(),
        actions: pending ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", minWidth: "200px" }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={() => handleApprove(inc.id)}
                disabled={processingId === inc.id}
                style={{ ...btn.primary, flex: 1, padding: "6px", fontSize: "12px", background: colors.successText }}
              >
                Approve
              </button>
              <button
                onClick={() => handleReject(inc.id)}
                disabled={processingId === inc.id}
                style={{ ...btn.primary, flex: 1, padding: "6px", fontSize: "12px", background: colors.dangerText }}
              >
                Reject
              </button>
            </div>
            <textarea
              rows={2}
              placeholder="Admin notes (required for rejection)"
              value={adminNotes[inc.id] || ""}
              onChange={(e) => setAdminNotes(prev => ({ ...prev, [inc.id]: e.target.value }))}
              style={{
                resize: "vertical",
                padding: "6px",
                border: `1px solid ${colors.borderMid}`,
                borderRadius: "4px",
                fontSize: "12px",
                fontFamily: "inherit"
              }}
            />
          </div>
        ) : (
          <div style={{ fontSize: "12px", color: colors.textMuted }}>
            {inc.status === "Approved" ? "Approved ✓" : "Rejected ✗"}
            {inc.admin_notes && (
              <div style={{ marginTop: "4px", fontStyle: "italic", fontSize: "11px" }}>
                Notes: {inc.admin_notes}
              </div>
            )}
          </div>
        ),
      };
    });

  return (
    <PageShell role="staff" title="Admin — Incidents">
      <PageTitle sub="Review and approve student incident reports for the live map.">Incident Reports</PageTitle>
      <div ref={mapSection} style={{ marginBottom: 20, scrollMarginTop: 16 }}>
        <IncidentsMap incidents={incidents} selectedId={viewingId} onSelect={setViewingId} />
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginTop: 8, fontSize: 12, color: colors.textSecondary }}>
          {LEGEND.map(([label, color]) => (
            <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: "50%", background: color, border: "2px solid #fff", boxShadow: `0 0 0 1px ${color}` }} />
              {label}
            </span>
          ))}
          <span>Click a report on the map, or "View on map" in the table, to focus it.</span>
        </div>
        <div style={{ marginTop: 10, padding: "12px 14px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: "#fff", fontSize: 13 }}>
          {viewing ? (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                <strong style={{ fontSize: 14 }}>Viewing: {viewing.incident_type_display}</strong>
                <Pill label={`${viewing.severity_display || viewing.severity} severity`} variant="neutral" />
                <Pill label={viewing.status} variant={statusVariant(viewing.status)} />
                <button type="button" onClick={() => setViewingId(null)} style={{ ...btn.ghost, marginLeft: "auto", padding: "4px 10px", fontSize: "12px" }}>Clear</button>
              </div>
              <div style={{ color: colors.textSecondary }}>
                Reported by {viewing.reported_by?.first_name || viewing.reported_by?.username || "N/A"} · occurred {new Date(viewing.occurred_at || viewing.created_at).toLocaleString()} · {viewing.radius_meters} m radius
              </div>
              <div style={{ marginTop: 4 }}>{viewing.description || "No description given."}</div>
            </>
          ) : (
            <span style={{ color: colors.textMuted }}>No report selected. The map shows every report; pick one to see it here.</span>
          )}
        </div>
      </div>
      <Table columns={columns} rows={rows} />
    </PageShell>
  );
}

export default AdminIncidents;
