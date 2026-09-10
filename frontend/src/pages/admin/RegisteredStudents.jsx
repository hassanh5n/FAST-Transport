import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { getRegisteredStudents, getSemesters } from "../../services/transportService";
import { badge, colors, input as inputStyle } from "../../theme";

const STATUS_VARIANT = {
  Approved: "success",
  "Seat Held": "info",
  payment_submitted: "info",
  Pending: "warning",
  Waitlisted: "warning",
};

const STATUS_LABEL = {
  payment_submitted: "Payment Submitted",
};

function RegisteredStudentsPage() {
  const [rows, setRows] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [semesterId, setSemesterId] = useState("");
  const [scope, setScope] = useState("confirmed");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSemesters()
      .then((res) => setSemesters(res.data))
      .catch(() => setSemesters([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    getRegisteredStudents({ semesterId: semesterId || undefined, scope })
      .then((res) => setRows(res.data))
      .catch(() => alert("Failed to fetch registered students."))
      .finally(() => setLoading(false));
  }, [semesterId, scope]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [
        row.full_name,
        row.username,
        row.email,
        row.roll_number,
        row.stop_name,
        row.route_name,
        row.bus_number,
      ]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q))
    );
  }, [rows, query]);

  const withoutBus = useMemo(() => rows.filter((r) => !r.bus_number).length, [rows]);

  const columns = [
    {
      key: "full_name",
      label: "Student",
      render: (row) => (
        <div>
          <div style={styles.primaryLine}>{row.full_name}</div>
          <div style={styles.secondaryLine}>{row.username}</div>
        </div>
      ),
    },
    { key: "roll_number", label: "Roll Number" },
    { key: "department", label: "Dept" },
    {
      key: "stop_name",
      label: "Pickup Point",
      render: (row) =>
        row.stop_name ? (
          <div>
            <div style={styles.primaryLine}>{row.stop_name}</div>
            {row.stop_address && (
              <div style={styles.secondaryLine}>{row.stop_address}</div>
            )}
          </div>
        ) : (
          "—"
        ),
    },
    { key: "route_name", label: "Route", render: (row) => row.route_name || "—" },
    {
      key: "bus_number",
      label: "Bus",
      render: (row) =>
        row.bus_number ? (
          <div>
            <div style={styles.primaryLine}>{row.bus_number}</div>
            {row.driver_name && (
              <div style={styles.secondaryLine}>{row.driver_name}</div>
            )}
          </div>
        ) : (
          <span style={styles.unassigned}>Not assigned</span>
        ),
    },
    {
      key: "seat_number",
      label: "Seat",
      render: (row) => (row.seat_number ? `#${row.seat_number}` : "—"),
    },
    {
      key: "status",
      label: "Status",
      render: (row) => (
        <span style={badge(STATUS_VARIANT[row.status] || "neutral")}>
          {STATUS_LABEL[row.status] || row.status}
        </span>
      ),
    },
    {
      key: "is_paid",
      label: "Fee",
      render: (row) => (
        <span style={badge(row.is_paid ? "success" : "danger")}>
          {row.is_paid ? "Paid" : "Unpaid"}
        </span>
      ),
    },
  ];

  const subtitle =
    scope === "confirmed"
      ? "Students with a paid fee and a held seat, showing their pickup point, route and assigned bus."
      : "Every live transport registration, including unpaid and waitlisted students.";

  return (
    <PageShell role="staff" title="Admin — Registered Students">
      <PageTitle sub={subtitle}>Registered Students</PageTitle>

      <div style={styles.toolbar}>
        <div style={styles.searchWrap}>
          <span style={styles.searchIcon}>
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke={colors.textMuted}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          </span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, roll number, stop, route or bus…"
            aria-label="Search registered students"
            style={styles.searchInput}
          />
        </div>

        <select
          value={semesterId}
          onChange={(e) => setSemesterId(e.target.value)}
          aria-label="Filter by semester"
          style={styles.select}
        >
          <option value="">All semesters</option>
          {semesters.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>

        <div style={styles.toggle} role="group" aria-label="Scope">
          {[
            { value: "confirmed", label: "Paid & seated" },
            { value: "all", label: "All registrations" },
          ].map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setScope(opt.value)}
              aria-pressed={scope === opt.value}
              style={{
                ...styles.toggleBtn,
                ...(scope === opt.value ? styles.toggleBtnActive : {}),
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {query.trim() && (
          <button type="button" onClick={() => setQuery("")} style={styles.clearBtn}>
            Clear
          </button>
        )}
      </div>

      {!loading && withoutBus > 0 && (
        <div style={styles.notice}>
          {withoutBus} {withoutBus === 1 ? "student has" : "students have"} a seat
          but no bus assigned to their route yet — check Assignments.
        </div>
      )}

      <Table
        columns={columns}
        rows={filtered}
        emptyMessage={
          loading
            ? "Loading…"
            : query.trim()
              ? `No students match “${query.trim()}”.`
              : scope === "confirmed"
                ? "No students have both paid their fee and been given a seat yet. Switch to “All registrations” to see pending and unpaid ones."
                : "No students are registered for transport yet."
        }
      />
    </PageShell>
  );
}

const styles = {
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    marginBottom: "14px",
    flexWrap: "wrap",
  },
  searchWrap: {
    position: "relative",
    flex: "1 1 260px",
    maxWidth: "380px",
  },
  searchIcon: {
    position: "absolute",
    left: "12px",
    top: "50%",
    transform: "translateY(-50%)",
    display: "flex",
    pointerEvents: "none",
  },
  searchInput: {
    ...inputStyle,
    paddingLeft: "34px",
  },
  select: {
    ...inputStyle,
    width: "auto",
    minWidth: "160px",
    cursor: "pointer",
  },
  toggle: {
    display: "inline-flex",
    border: `1px solid ${colors.borderMid}`,
    borderRadius: "10px",
    overflow: "hidden",
    background: "#fff",
  },
  toggleBtn: {
    background: "transparent",
    border: "none",
    padding: "9px 14px",
    fontSize: "13px",
    fontWeight: 500,
    color: colors.textSecondary,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  toggleBtnActive: {
    background: colors.accent,
    color: "#fff",
    fontWeight: 600,
  },
  clearBtn: {
    background: "transparent",
    border: `1px solid ${colors.borderMid}`,
    borderRadius: "10px",
    padding: "9px 14px",
    fontSize: "13px",
    fontWeight: 500,
    color: colors.textSecondary,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  notice: {
    background: colors.warningBg,
    color: colors.warningText,
    border: `1px solid rgba(245,158,11,0.25)`,
    borderRadius: "10px",
    padding: "10px 14px",
    fontSize: "13px",
    fontWeight: 500,
    marginBottom: "14px",
  },
  primaryLine: {
    fontSize: "13.5px",
    color: colors.textPrimary,
  },
  secondaryLine: {
    fontSize: "11.5px",
    color: colors.textMuted,
    marginTop: "2px",
  },
  unassigned: {
    fontSize: "12.5px",
    color: colors.textMuted,
    fontStyle: "italic",
  },
};

export default RegisteredStudentsPage;
