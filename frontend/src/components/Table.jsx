// frontend/src/components/Table.jsx
import { colors, fonts } from "../theme";

function Table({ columns, rows, emptyMessage = "No data available." }) {
  return (
    <div style={styles.wrapper}>
      <div style={styles.tableScroll}>
        <table style={styles.table}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key ?? col} style={styles.th}>
                  {col.label ?? col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={styles.emptyCell}>
                  <div style={styles.emptyState}>
                    <div style={styles.emptyIcon}>
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={colors.textMuted} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                        <path d="M11 8v6"/><path d="M8 11h6"/>
                      </svg>
                    </div>
                    <p style={styles.emptyText}>{emptyMessage}</p>
                  </div>
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <TableRow key={row.id ?? i} row={row} columns={columns} index={i} />
              ))
            )}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <div style={styles.footer}>
          {rows.length} {rows.length === 1 ? "record" : "records"}
        </div>
      )}
    </div>
  );
}

// ── Row with hover state via useState ────────────────────────────────────────
import { useState } from "react";

function TableRow({ row, columns, index }) {
  const [hovered, setHovered] = useState(false);

  const rowStyle = {
    ...styles.tr,
    background: hovered
      ? colors.tableRowHover
      : index % 2 === 1
        ? colors.tableRowAlt
        : "#fff",
  };

  return (
    <tr
      style={rowStyle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {columns.map((col) => (
        <td key={col.key ?? col} style={styles.td}>
          {col.render ? col.render(row) : (row[col.key ?? col] ?? "—")}
        </td>
      ))}
    </tr>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────
const styles = {
  wrapper: {
    background:   "#fff",
    borderRadius: "12px",
    border:       `1px solid ${colors.borderLight}`,
    overflow:     "hidden",
    boxShadow:    "0 1px 3px rgba(11,45,66,0.06)",
    fontFamily:   fonts.body,
  },
  tableScroll: {
    overflowX: "auto",
  },
  table: {
    width:           "100%",
    borderCollapse:  "collapse",
    fontSize:        "13px",
    color:           colors.textPrimary,
    minWidth:        "400px",
  },
  th: {
    padding:         "12px 16px",
    textAlign:       "left",
    fontSize:        "11px",
    fontWeight:      "700",
    textTransform:   "uppercase",
    letterSpacing:   "0.06em",
    color:           colors.textSecondary,
    background:      colors.tableHeaderBg,
    borderBottom:    `1px solid ${colors.borderLight}`,
    whiteSpace:      "nowrap",
  },
  tr: {
    borderBottom: `1px solid ${colors.tableRowBorder}`,
    transition:   "background 0.1s",
  },
  td: {
    padding:     "11px 16px",
    verticalAlign:"middle",
    color:       colors.textPrimary,
    fontSize:    "13.5px",
  },
  emptyCell: {
    padding:   "48px 16px",
    textAlign: "center",
  },
  emptyState: {
    display:       "flex",
    flexDirection: "column",
    alignItems:    "center",
    gap:           "10px",
  },
  emptyIcon: {
    width:          "52px",
    height:         "52px",
    borderRadius:   "50%",
    background:     colors.pageBg,
    border:         `1px solid ${colors.borderLight}`,
    display:        "flex",
    alignItems:     "center",
    justifyContent: "center",
  },
  emptyText: {
    margin:    0,
    fontSize:  "13px",
    color:     colors.textMuted,
    fontWeight:"500",
  },
  footer: {
    padding:        "10px 16px",
    borderTop:      `1px solid ${colors.tableRowBorder}`,
    fontSize:       "12px",
    color:          colors.textMuted,
    fontWeight:     "500",
    background:     colors.tableHeaderBg,
    textAlign:      "right",
  },
};

export default Table;