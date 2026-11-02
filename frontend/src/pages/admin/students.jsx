import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Pill } from "../../components/ui";
import { getStudents } from "../../services/transportService";
import { colors, input as inputStyle } from "../../theme";
import { TRANSPORT_STATUS, transportStatusMeta } from "../../utils/transportStatus";

function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [query, setQuery] = useState("");
  // "" = everyone; otherwise one of the transport statuses.
  const [statusFilter, setStatusFilter] = useState("");

  // The status filter runs on the server, so it covers every student and not only
  // the rows already loaded; the text search below filters what came back.
  useEffect(() => {
    let current = true;
    getStudents(statusFilter)
      .then((res) => { if (current) setStudents(res.data); })
      .catch(() => alert("Failed to fetch students."));
    return () => { current = false; };
  }, [statusFilter]);

  const fullName = (row) =>
    `${row.user?.first_name || ""} ${row.user?.last_name || ""}`.trim();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return students.filter((row) =>
      (!q || [
        fullName(row),
        row.user?.username,
        row.user?.email,
        row.roll_number,
        row.batch,
        row.department,
      ]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q)))
    );
  }, [students, query]);

  const columns = [
    { key: "id", label: "ID" },
    {
      key: "full_name",
      label: "Full Name",
      render: (row) => fullName(row) || row.user?.username,
    },
    { key: "username", label: "Username", render: (row) => row.user?.username },
    { key: "email", label: "Email", render: (row) => row.user?.email },
    { key: "roll_number", label: "Roll Number" },
    { key: "batch", label: "Batch" },
    { key: "department", label: "Department" },
    {
      key: "transport_status",
      label: "Transport",
      render: (row) => {
        const meta = transportStatusMeta(row.transport_status);
        return <Pill label={meta.label} variant={meta.variant} />;
      },
    },
  ];

  const filtering = query.trim() || statusFilter;

  return (
    <PageShell role="staff" title="Admin — Students">
      <PageTitle sub="Everyone with an account. Transport users are registered for the current semester; site users are not.">
        All Students
      </PageTitle>

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
            placeholder="Search by name, username, email, roll number…"
            aria-label="Search students"
            style={styles.searchInput}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter by transport status"
          style={styles.select}
        >
          <option value="">Everyone</option>
          {Object.entries(TRANSPORT_STATUS).map(([key, meta]) => (
            <option key={key} value={key}>{meta.label}s</option>
          ))}
        </select>
        {filtering && (
          <button
            type="button"
            onClick={() => { setQuery(""); setStatusFilter(""); }}
            style={styles.clearBtn}
          >
            Clear
          </button>
        )}
      </div>

      <Table
        columns={columns}
        rows={filtered}
        emptyMessage={
          filtering
            ? "No students match these filters."
            : "No students registered yet."
        }
      />
    </PageShell>
  );
}

const styles = {
  toolbar: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "10px",
    marginBottom: "14px",
  },
  searchWrap: {
    position: "relative",
    flex: "1 1 auto",
    maxWidth: "420px",
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
    cursor: "pointer",
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
};

export default StudentsPage;
