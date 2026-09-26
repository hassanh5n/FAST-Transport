// frontend/src/pages/admin/ActivityLogs.jsx
// Super admin only: everything admins did, with filters and field-level diffs.
import { Fragment, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Spinner } from "../../components/ui";
import { btn, colors, fonts, input, radius } from "../../theme";
import { getActivityLogs, getAdminModules, getAdminUsers } from "../../services/transportService";

const ACTIONS = [
  { key: "create", label: "Created", bg: colors.successBg, text: colors.successText },
  { key: "update", label: "Updated", bg: colors.infoBg,    text: colors.infoText    },
  { key: "delete", label: "Deleted", bg: colors.dangerBg,  text: colors.dangerText  },
  { key: "action", label: "Action",  bg: colors.warningBg, text: colors.warningText },
  { key: "login",  label: "Login",   bg: colors.neutralBg, text: colors.neutralText },
];
const ACTION_MAP = Object.fromEntries(ACTIONS.map((a) => [a.key, a]));
const PAGE_SIZE = 25;

const show = (v) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

function ChangesTable({ changes }) {
  const entries = Object.entries(changes || {});
  if (entries.length === 0) return <div style={{ color: colors.textMuted, fontSize: "12.5px" }}>No field details recorded.</div>;
  const hasFrom = entries.some(([, c]) => "from" in c);
  const hasTo = entries.some(([, c]) => "to" in c);
  return (
    <table style={styles.diffTable}>
      <thead>
        <tr>
          <th style={styles.diffTh}>Field</th>
          {hasFrom && <th style={styles.diffTh}>{hasTo ? "Before" : "Value"}</th>}
          {hasTo && <th style={styles.diffTh}>{hasFrom ? "After" : "Value"}</th>}
        </tr>
      </thead>
      <tbody>
        {entries.map(([field, c]) => (
          <tr key={field}>
            <td style={{ ...styles.diffTd, fontWeight: 600 }}>{field.replace(/_/g, " ")}</td>
            {hasFrom && <td style={{ ...styles.diffTd, color: hasTo ? colors.dangerText : colors.textPrimary }}>{show(c.from)}</td>}
            {hasTo && <td style={{ ...styles.diffTd, color: hasFrom ? colors.successText : colors.textPrimary }}>{show(c.to)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ActivityLogs() {
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState({
    actor: searchParams.get("actor") || "",
    module: "", action: "", date_from: "", date_to: "", q: "",
  });
  const [query, setQuery] = useState(filters); // applied filters
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [modules, setModules] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAdminUsers().then((r) => setAdmins(r.data)).catch(() => {});
    getAdminModules().then((r) => setModules(r.data.modules)).catch(() => {});
  }, []);

  useEffect(() => {
    const params = { page, page_size: PAGE_SIZE };
    Object.entries(query).forEach(([k, v]) => { if (v) params[k] = v; });
    getActivityLogs(params)
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => { setError(err.response?.data?.detail || "Failed to load activity logs."); setData({ items: [], total: 0, pages: 0 }); });
  }, [query, page]);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));
  const apply = (e) => { e?.preventDefault(); setPage(1); setExpanded(null); setQuery(filters); };
  const reset = () => {
    const empty = { actor: "", module: "", action: "", date_from: "", date_to: "", q: "" };
    setFilters(empty); setQuery(empty); setPage(1); setExpanded(null);
  };

  return (
    <PageShell role="staff" title="Activity Logs">
      <PageTitle sub="Every change an admin makes — who did it, when, and exactly what changed.">Admin Activity Logs</PageTitle>

      <form onSubmit={apply} style={styles.filters}>
        <label style={styles.filter}>
          <span style={styles.filterLabel}>Admin</span>
          <select style={input} value={filters.actor} onChange={set("actor")}>
            <option value="">All admins</option>
            {admins.map((a) => <option key={a.id} value={a.id}>{`${a.first_name} ${a.last_name}`.trim() || a.username} (@{a.username})</option>)}
          </select>
        </label>
        <label style={styles.filter}>
          <span style={styles.filterLabel}>Module</span>
          <select style={input} value={filters.module} onChange={set("module")}>
            <option value="">All modules</option>
            {modules.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            <option value="admin_management">Admin Management</option>
          </select>
        </label>
        <label style={styles.filter}>
          <span style={styles.filterLabel}>Action</span>
          <select style={input} value={filters.action} onChange={set("action")}>
            <option value="">All actions</option>
            {ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
          </select>
        </label>
        <label style={styles.filter}>
          <span style={styles.filterLabel}>From</span>
          <input style={input} type="date" value={filters.date_from} onChange={set("date_from")} />
        </label>
        <label style={styles.filter}>
          <span style={styles.filterLabel}>To</span>
          <input style={input} type="date" value={filters.date_to} onChange={set("date_to")} />
        </label>
        <label style={{ ...styles.filter, flex: "2 1 220px" }}>
          <span style={styles.filterLabel}>Search</span>
          <input style={input} placeholder="e.g. complaint subject, bus number…" value={filters.q} onChange={set("q")} />
        </label>
        <div style={{ display: "flex", gap: "8px", alignItems: "flex-end" }}>
          <button type="submit" style={btn.primary}>Apply</button>
          <button type="button" style={btn.ghost} onClick={reset}>Reset</button>
        </div>
      </form>

      {error && <div style={styles.error}>{error}</div>}

      <div style={styles.card}>
        {!data ? (
          <Spinner />
        ) : data.items.length === 0 ? (
          <div style={styles.empty}>No activity matches these filters.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  {["When", "Admin", "Action", "Module", "What happened", ""].map((h) => <th key={h} style={styles.th}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.items.map((log) => {
                  const a = ACTION_MAP[log.action] || ACTION_MAP.action;
                  const open = expanded === log.id;
                  return (
                    <Fragment key={log.id}>
                      <tr style={{ background: open ? colors.tableRowHover : "transparent" }}>
                        <td style={{ ...styles.td, whiteSpace: "nowrap" }}>{new Date(log.created_at).toLocaleString()}</td>
                        <td style={styles.td}>
                          <div style={{ fontWeight: 600 }}>{log.actor_name || "—"}</div>
                          <div style={{ fontSize: "11.5px", color: colors.textMuted }}>@{log.actor_username}</div>
                        </td>
                        <td style={styles.td}><span style={{ ...styles.tag, background: a.bg, color: a.text }}>{a.label}</span></td>
                        <td style={{ ...styles.td, whiteSpace: "nowrap" }}>{log.module_label}</td>
                        <td style={{ ...styles.td, minWidth: "260px" }}>{log.description}</td>
                        <td style={styles.td}>
                          <button type="button" style={styles.detailBtn} onClick={() => setExpanded(open ? null : log.id)} aria-expanded={open}>
                            {open ? "Hide" : "Details"}
                          </button>
                        </td>
                      </tr>
                      {open && (
                        <tr>
                          <td colSpan={6} style={styles.detailCell}>
                            <ChangesTable changes={log.changes} />
                            <div style={styles.meta}>
                              {log.method && <span>{log.method} {log.path}</span>}
                              {log.ip_address && <span>IP {log.ip_address}</span>}
                              {log.model_name && <span>{log.model_name} #{log.object_id}</span>}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > 0 && (
          <div style={styles.pager}>
            <span>{data.total} {data.total === 1 ? "entry" : "entries"} · page {data.page} of {data.pages}</span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button style={btn.ghost} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Newer</button>
              <button style={btn.ghost} disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>Older →</button>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}

const styles = {
  filters: {
    display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "flex-end",
    background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg,
    padding: "16px 18px", marginBottom: "16px",
  },
  filter: { display: "flex", flexDirection: "column", gap: "5px", flex: "1 1 150px", minWidth: 0 },
  filterLabel: { fontSize: "11px", fontWeight: 600, color: colors.textSecondary, letterSpacing: "0.04em", textTransform: "uppercase" },
  card: { background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, overflow: "hidden" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "13px", fontFamily: fonts.body },
  th: {
    textAlign: "left", padding: "11px 14px", background: colors.tableHeaderBg, color: colors.textSecondary,
    fontSize: "11px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  td: { padding: "11px 14px", borderBottom: `1px solid ${colors.tableRowBorder}`, color: colors.textPrimary, verticalAlign: "top" },
  tag: { fontSize: "11px", fontWeight: 700, padding: "3px 9px", borderRadius: "999px", whiteSpace: "nowrap" },
  detailBtn: { ...btn.ghost, padding: "4px 10px", fontSize: "12px" },
  detailCell: { padding: "12px 18px 16px", background: colors.pageBg, borderBottom: `1px solid ${colors.borderLight}` },
  diffTable: { borderCollapse: "collapse", fontSize: "12.5px", background: "#fff", borderRadius: radius.md, overflow: "hidden", minWidth: "320px" },
  diffTh: { textAlign: "left", padding: "7px 12px", background: colors.tableHeaderBg, color: colors.textSecondary, fontSize: "11px", fontWeight: 700 },
  diffTd: { padding: "7px 12px", borderTop: `1px solid ${colors.tableRowBorder}`, wordBreak: "break-word", maxWidth: "420px" },
  meta: { display: "flex", flexWrap: "wrap", gap: "14px", marginTop: "10px", fontSize: "11.5px", color: colors.textMuted },
  pager: {
    display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px",
    padding: "12px 16px", borderTop: `1px solid ${colors.borderLight}`, fontSize: "12.5px", color: colors.textSecondary,
  },
  empty: { padding: "40px 16px", textAlign: "center", color: colors.textMuted, fontSize: "13px" },
  error: { color: colors.dangerText, background: colors.dangerBg, borderRadius: radius.md, padding: "10px 12px", marginBottom: "12px", fontSize: "13px" },
};

export default ActivityLogs;
