// frontend/src/pages/driver/DriverPassengers.jsx
import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Spinner, Banner, Pill } from "../../components/ui";
import { inputStyle, selectStyle } from "../../styles/formStyles";
import { colors, fonts } from "../../theme";
import { getDriverOverview } from "../../services/transportService";

// SemesterRegistration status → what the driver needs to know at the door.
const STATUS = {
  Confirmed:   { label: "Confirmed",   variant: "success" },
  "Seat Held": { label: "Fee pending", variant: "warning" },
};

export default function DriverPassengers() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [stopFilter, setStopFilter] = useState("all");

  useEffect(() => {
    getDriverOverview()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load your passengers. Please try again."));
  }, []);

  const stops = data?.stops ?? [];
  const orderByStop = useMemo(() => Object.fromEntries(stops.map((s) => [s.id, s.stop_order])), [stops]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.passengers ?? [])
      .filter((p) => stopFilter === "all" || String(p.stop_id) === stopFilter)
      .filter((p) => !q || [p.name, p.roll_number, p.stop_name, String(p.seat_number)].some((v) => v?.toLowerCase().includes(q)))
      .map((p) => ({ ...p, id: p.seat_number, stop_order: orderByStop[p.stop_id] }))
      .sort((a, b) => (a.stop_order ?? 999) - (b.stop_order ?? 999) || a.seat_number - b.seat_number);
  }, [data, search, stopFilter, orderByStop]);

  if (error) return <PageShell role="driver" title="Passengers"><Banner variant="danger">{error}</Banner></PageShell>;
  if (!data) return <PageShell role="driver" title="Passengers"><Spinner /></PageShell>;

  if (!data.assignment) return (
    <PageShell role="driver" title="Passengers">
      <PageTitle sub="Your passenger list appears once you have a bus and route.">Passengers</PageTitle>
      <Banner variant="warning">You have not been assigned a bus for this semester yet. Please contact the transport office.</Banner>
    </PageShell>
  );

  const { assignment, passengers } = data;
  const feePending = passengers.filter((p) => p.status === "Seat Held").length;

  const columns = [
    { key: "seat_number", label: "Seat", width: "70px", render: (r) => <strong style={{ fontVariantNumeric: "tabular-nums" }}>#{r.seat_number}</strong> },
    { key: "name", label: "Name", render: (r) => <span style={{ fontWeight: 600, color: colors.textPrimary }}>{r.name}</span> },
    { key: "roll_number", label: "Roll No" },
    {
      key: "stop_name", label: "Stop",
      render: (r) => r.stop_order
        ? <span>{r.stop_name} <span style={{ color: colors.textMuted }}>· stop {r.stop_order}</span></span>
        : r.stop_name,
    },
    {
      key: "status", label: "Status",
      render: (r) => {
        const s = STATUS[r.status] || { label: r.status, variant: "neutral" };
        return <Pill label={s.label} variant={s.variant} />;
      },
    },
  ];

  return (
    <PageShell role="driver" title="Passengers">
      <PageTitle sub={`Students with a seat on bus ${assignment.bus.bus_number} for ${assignment.semester}.`}>
        Passengers
      </PageTitle>

      <div style={statGrid}>
        <Stat label="Passengers" value={`${passengers.length} / ${assignment.bus.capacity}`} />
        <Stat label="Stops served" value={stops.filter((s) => s.student_count > 0).length} />
        <Stat label="Fee pending" value={feePending} tone={feePending ? colors.warningText : undefined} />
      </div>

      <div style={toolbar}>
        <input
          type="search"
          placeholder="Search name, roll number, seat…"
          aria-label="Search passengers"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...inputStyle, maxWidth: 320 }}
        />
        <select value={stopFilter} onChange={(e) => setStopFilter(e.target.value)} aria-label="Filter by stop" style={{ ...selectStyle, maxWidth: 260 }}>
          <option value="all">All stops</option>
          {stops.map((s) => (
            <option key={s.route_stop_id} value={String(s.id)}>
              {s.stop_order}. {s.name} ({s.student_count})
            </option>
          ))}
        </select>
      </div>

      <Table
        columns={columns}
        rows={rows}
        emptyMessage={
          passengers.length === 0
            ? "No students have been seated on your bus yet."
            : "No passengers match the current search or stop."
        }
      />
    </PageShell>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div style={statCard}>
      <div style={statLabel}>{label}</div>
      <div style={{ ...statValue, ...(tone ? { color: tone } : {}) }}>{value}</div>
    </div>
  );
}

// Same stat tiles as the admin route detail page.
const statGrid = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 20 };
const statCard = { background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: 12, padding: "16px 18px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)" };
const statLabel = { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: colors.textSecondary, marginBottom: 6 };
const statValue = { fontSize: 24, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading, lineHeight: 1.1, fontVariantNumeric: "tabular-nums" };
const toolbar = { display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 14 };