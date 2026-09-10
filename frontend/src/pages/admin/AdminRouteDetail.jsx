import { useEffect, useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import Table from "../../components/Table";
import { SectionBlock, Pill, Spinner, Banner, DetailRow } from "../../components/ui";
import { inputStyle, selectStyle } from "../../styles/formStyles";
import { btn, colors, fonts } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getRouteOverview, getRouteMapDetail } from "../../services/transportService";

// Maps a TransportRegistration status onto one of the theme's badge variants.
const statusVariant = (status) => {
  switch (status) {
    case "Approved":          return "success";
    case "Rejected":          return "danger";
    case "payment_submitted": return "info";
    default:                  return "warning"; // Pending
  }
};

const statusLabel = (status) =>
  status === "payment_submitted" ? "Payment Submitted" : status;

const EMPTY_STUDENTS = [];

function AdminRouteDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [routeMap, setRouteMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getRouteOverview(id),
      getRouteMapDetail(id),
    ])
      .then(([overviewRes, mapRes]) => {
        if (!cancelled) {
          setData(overviewRes.data);
          setRouteMap(mapRes.data || null);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err.response?.status === 404
              ? "That route no longer exists."
              : "Failed to load this route. Please try again."
          );
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const students = data?.students || EMPTY_STUDENTS;

  const visibleStudents = useMemo(() => {
    const q = search.trim().toLowerCase();
    return students.filter((s) => {
      if (statusFilter !== "All") {
        // A student is "confirmed" only when the fee is settled AND a seat is
        // actually allocated. Either half missing means they are not riding yet.
        const confirmed = Boolean(s.is_paid) && s.seat_number != null;
        if (statusFilter === "Confirmed") {
          if (!confirmed) return false;
        } else if (statusFilter === "Unconfirmed") {
          if (confirmed) return false;
        } else if (statusFilter === "Pending") {
          if (s.status !== "Pending" && s.status !== "payment_submitted") return false;
        } else if (s.status !== statusFilter) {
          return false;
        }
      }
      if (!q) return true;
      return [s.roll_number, s.name, s.email, s.department, s.batch, s.stop]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [students, statusFilter, search]);

  const exportCsv = () => {
    const headers = [
      "Roll Number", "Name", "Email", "Department", "Batch",
      "Phone", "Stop", "Seat", "Status", "Paid",
    ];
    const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [
      headers.join(","),
      ...visibleStudents.map((s) => [
        s.roll_number, s.name, s.email, s.department, s.batch,
        s.phone, s.stop, s.seat_number, statusLabel(s.status),
        s.is_paid ? "Yes" : "No",
      ].map(escape).join(",")),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `route-${data?.route?.name ?? id}-students.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const studentColumns = [
    { key: "roll_number", label: "Roll Number", render: (r) => <strong>{r.roll_number}</strong> },
    { key: "name", label: "Name" },
    { key: "department", label: "Dept" },
    { key: "batch", label: "Batch" },
    { key: "stop", label: "Stop" },
    { key: "phone", label: "Phone" },
    {
      key: "seat_number",
      label: "Seat",
      render: (r) => (r.seat_number != null ? r.seat_number : <span style={muted}>—</span>),
    },
    {
      key: "status",
      label: "Status",
      render: (r) => <Pill label={statusLabel(r.status)} variant={statusVariant(r.status)} />,
    },
    {
      key: "is_paid",
      label: "Fee",
      render: (r) => <Pill label={r.is_paid ? "Paid" : "Unpaid"} variant={r.is_paid ? "success" : "neutral"} />,
    },
  ];

  // ── Loading / error ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <PageShell role="staff" title="Admin — Route Detail">
        <div style={{ padding: "60px 0", display: "flex", justifyContent: "center" }}>
          <Spinner />
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell role="staff" title="Admin — Route Detail">
        <Banner variant="danger">{error}</Banner>
        <Link to="/admin/routes" style={{ ...btn.ghost, display: "inline-block", textDecoration: "none", marginTop: "16px" }}>
          ← Back to Routes
        </Link>
      </PageShell>
    );
  }

  const { route, assignment, stats, semester } = data;

  return (
    <PageShell role="staff" title="Admin — Route Detail">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <Link to="/admin/routes" style={{ ...backLink, marginBottom: 0 }}>← Back to Routes</Link>
        <Link to={`/admin/routes/${id}/edit`} style={{ ...btn.ghost, textDecoration: "none" }}>Edit Route</Link>
      </div>

      <PageTitle sub={route.description}>
        {route.name}
      </PageTitle>

      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "20px" }}>
        <Pill label={route.is_active ? "Active" : "Inactive"} variant={route.is_active ? "success" : "neutral"} />
        {semester && <Pill label={semester} variant="info" />}
      </div>

      {/* ── Stats ─────────────────────────────────────────────────────────── */}
      <div style={statGrid}>
        <Stat label="Registered"  value={stats.registered} />
        <Stat label="Approved"    value={stats.approved}  tone={colors.successText} />
        <Stat label="Pending"     value={stats.pending}   tone={colors.warningText} />
        <Stat label="Rejected"    value={stats.rejected}  tone={colors.dangerText} />
        <Stat label="Bus Capacity" value={stats.capacity ?? "—"} />
        <Stat
          label="Seats Left"
          value={stats.seats_left ?? "—"}
          tone={stats.seats_left != null && stats.seats_left <= 0 ? colors.dangerText : undefined}
        />
      </div>

      {/* ── Driver + Bus ──────────────────────────────────────────────────── */}
      {assignment ? (
        <div style={twoCol}>
          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={cardHeading}>Driver</h3>
            <DetailRow label="Name"        value={assignment.driver.name} />
            <DetailRow label="Phone"       value={assignment.driver.phone} />
            <DetailRow label="CNIC"        value={assignment.driver.cnic} />
            <DetailRow label="License No"  value={assignment.driver.license_no} />
            <DetailRow label="Address"     value={assignment.driver.address} />
            <div style={{ marginTop: "12px" }}>
              <Pill
                label={assignment.driver.is_available ? "Available" : "Unavailable"}
                variant={assignment.driver.is_available ? "success" : "neutral"}
              />
            </div>
          </ContentCard>

          <ContentCard style={{ marginBottom: 0 }}>
            <h3 style={cardHeading}>Bus</h3>
            <DetailRow label="Bus Number" value={assignment.bus.bus_number} />
            <DetailRow label="Model"      value={assignment.bus.model} />
            <DetailRow label="Capacity"   value={assignment.bus.capacity} />
            <DetailRow label="Semester"   value={assignment.semester} />
            <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <Pill
                label={assignment.bus.is_active ? "Active" : "Inactive"}
                variant={assignment.bus.is_active ? "success" : "neutral"}
              />
              {assignment.bus.is_off_route && <Pill label="Off Route" variant="danger" />}
            </div>
          </ContentCard>
        </div>
      ) : (
        <Banner variant="warning">
          No bus or driver is assigned to this route yet.{" "}
          <Link to="/admin/assignments" style={{ color: colors.infoText, fontWeight: 600 }}>
            Create an assignment →
          </Link>
        </Banner>
      )}

      <ContentCard style={{ marginBottom: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <h3 style={cardHeading}>Route Map</h3>
            <span style={{ color: colors.textSecondary, fontSize: 12 }}>
              {routeMap?.stops?.length ?? 0} stops on the route
            </span>
          </div>
          <RouteMap
            routes={routeMap ? [routeMap] : []}
            selectedRouteId={Number(route.id)}
            height={320}
          />
        </div>
      </ContentCard>

      {/* ── Students ──────────────────────────────────────────────────────── */}
      <SectionBlock
        title="Registered Students"
        sub="All registrations on this route for the current semester, regardless of status."
      >
        <div style={toolbar}>
          <input
            placeholder="Search roll number, name, email, stop…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ ...inputStyle, maxWidth: "320px" }}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ ...selectStyle, maxWidth: "200px" }}
          >
            <option value="All">All statuses</option>
            <option value="Confirmed">Paid &amp; seated</option>
            <option value="Unconfirmed">Not paid / no seat</option>
            <option value="Approved">Approved</option>
            <option value="Pending">Pending / Payment Submitted</option>
            <option value="Rejected">Rejected</option>
          </select>
          <button
            onClick={exportCsv}
            style={{ ...btn.ghost, whiteSpace: "nowrap" }}
            disabled={visibleStudents.length === 0}
          >
            Export CSV
          </button>
        </div>

        <Table
          columns={studentColumns}
          rows={visibleStudents}
          emptyMessage={
            students.length === 0
              ? "No students are registered on this route yet."
              : statusFilter === "Confirmed"
                ? "No students on this route have both paid and been allocated a seat."
                : statusFilter === "Unconfirmed"
                  ? "Every student on this route has paid and holds a seat."
                  : "No students match the current filters."
          }
        />
      </SectionBlock>
    </PageShell>
  );
}

// ── Small presentational bits ────────────────────────────────────────────────
function Stat({ label, value, tone }) {
  return (
    <div style={statCard}>
      <div style={statLabel}>{label}</div>
      <div style={{ ...statValue, ...(tone ? { color: tone } : {}) }}>{value}</div>
    </div>
  );
}

const muted = { color: colors.textMuted };

const backLink = {
  display: "inline-block",
  marginBottom: "14px",
  fontSize: "13px",
  fontWeight: 600,
  color: colors.textSecondary,
  textDecoration: "none",
};

const statGrid = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "12px",
  marginBottom: "20px",
};

const statCard = {
  background: "#fff",
  border: `1px solid ${colors.borderLight}`,
  borderRadius: "12px",
  padding: "16px 18px",
  boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
};

const statLabel = {
  fontSize: "11px",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: colors.textSecondary,
  marginBottom: "6px",
};

const statValue = {
  fontSize: "24px",
  fontWeight: 700,
  color: colors.textPrimary,
  fontFamily: fonts.heading,
  lineHeight: 1.1,
};

const twoCol = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
  gap: "16px",
  marginBottom: "20px",
};

const cardHeading = {
  margin: "0 0 14px",
  fontSize: "15px",
  fontWeight: 700,
  color: colors.textPrimary,
  fontFamily: fonts.heading,
};

const toolbar = {
  display: "flex",
  gap: "10px",
  flexWrap: "wrap",
  alignItems: "center",
  marginBottom: "14px",
};

export default AdminRouteDetail;
