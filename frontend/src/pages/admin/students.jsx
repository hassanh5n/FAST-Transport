import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { getStudents } from "../../services/transportService";
import { colors, input as inputStyle } from "../../theme";

function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    getStudents()
      .then((res) => setStudents(res.data))
      .catch(() => alert("Failed to fetch students."));
  }, []);

  const fullName = (row) =>
    `${row.user?.first_name || ""} ${row.user?.last_name || ""}`.trim();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return students;
    return students.filter((row) =>
      [
        fullName(row),
        row.user?.username,
        row.user?.email,
        row.roll_number,
        row.batch,
        row.department,
      ]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q))
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
  ];

  return (
    <PageShell role="staff" title="Admin — Students">
      <PageTitle sub="Registered students in the transport system.">All Students</PageTitle>

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
        {query.trim() && (
          <button type="button" onClick={() => setQuery("")} style={styles.clearBtn}>
            Clear
          </button>
        )}
      </div>

      <Table
        columns={columns}
        rows={filtered}
        emptyMessage={
          query.trim()
            ? `No students match “${query.trim()}”.`
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
