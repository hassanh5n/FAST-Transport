// frontend/src/components/Table.jsx
import { useLayoutEffect, useRef, useState } from "react";
import { colors, fonts } from "../theme";
import { useBreakpoint } from "../utils/useBreakpoint";

// Each column needs about this much room before cells start wrapping word by word.
const MIN_COLUMN_WIDTH = 100;

// The width of an element, kept up to date as it resizes.
function useWidth(ref) {
  const [width, setWidth] = useState(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

// On phones and tablets, when the table has too little room for its columns, each row
// becomes a card of label/value pairs with the "actions" column as a full-width footer,
// so nothing is crushed or scrolls sideways. Desktop (1100px+) always keeps the table
// and scrolls it if it is wider than the page.
// Pass stackOnMobile={false} to keep the scrolling table instead; `style` overrides the wrapper.
function Table({ columns, rows, emptyMessage = "No data available.", onRowHover, stackOnMobile = true, style }) {
  const wrapperRef = useRef(null);
  const width = useWidth(wrapperRef);
  const isDesktop = !useBreakpoint(1100);
  const stacked = stackOnMobile && !isDesktop && width !== null
    && width < Math.max(400, columns.length * MIN_COLUMN_WIDTH); // 400: the table's own min-width

  return (
    <div ref={wrapperRef} style={{ ...styles.wrapper, ...style }}>
      {rows.length === 0 ? (
        <EmptyState message={emptyMessage} />
      ) : stacked ? (
        <ul style={styles.cardList}>
          {rows.map((row, i) => (
            <RowCard key={row.id ?? i} row={row} columns={columns} />
          ))}
        </ul>
      ) : (
        <div style={styles.tableScroll}>
          <table style={styles.table}>
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col.key ?? col} scope="col" style={{ ...styles.th, ...(col.width ? { width: col.width } : {}) }}>
                    {col.label ?? col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <TableRow key={row.id ?? i} row={row} columns={columns} index={i} onRowHover={onRowHover} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 && (
        <div style={styles.footer}>
          {rows.length} {rows.length === 1 ? "record" : "records"}
        </div>
      )}
    </div>
  );
}

const cellValue = (row, col) => (col.render ? col.render(row) : (row[col.key ?? col] ?? "—"));

function EmptyState({ message }) {
  return (
    <div style={styles.emptyState}>
      <div style={styles.emptyIcon}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={colors.textMuted} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          <path d="M11 8v6"/><path d="M8 11h6"/>
        </svg>
      </div>
      <p style={styles.emptyText}>{message}</p>
    </div>
  );
}

// ── Row with hover state via useState ────────────────────────────────────────
function TableRow({ row, columns, index, onRowHover }) {
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
      onMouseEnter={() => { setHovered(true); onRowHover?.(row); }}
      onMouseLeave={() => { setHovered(false); onRowHover?.(null); }}
    >
      {columns.map((col) => (
        <td key={col.key ?? col} className={col.key === "actions" ? "table-actions" : undefined} style={{ ...styles.td, ...(col.width ? { width: col.width } : {}) }}>
          {cellValue(row, col)}
        </td>
      ))}
    </tr>
  );
}

// ── Phone layout: one card per row ───────────────────────────────────────────
function RowCard({ row, columns }) {
  const fields = columns.filter((col) => col.key !== "actions");
  const actions = columns.find((col) => col.key === "actions");

  return (
    <li style={styles.card}>
      <dl style={styles.cardFields}>
        {fields.map((col) => {
          const label = col.label ?? col;
          return (
            <div key={col.key ?? col} style={styles.cardField}>
              {label !== "" && <dt style={styles.cardLabel}>{label}</dt>}
              <dd style={styles.cardValue}>{cellValue(row, col)}</dd>
            </div>
          );
        })}
      </dl>
      {actions && <div className="table-actions" style={styles.cardActions}>{cellValue(row, actions)}</div>}
    </li>
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
  cardList: {
    listStyle: "none",
    margin:    0,
    padding:   0,
  },
  card: {
    padding:      "14px 16px",
    borderBottom: `1px solid ${colors.tableRowBorder}`,
  },
  cardFields: {
    margin:              0,
    display:             "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap:                 "10px 16px",
  },
  cardField: {
    minWidth: 0,
  },
  cardLabel: {
    fontSize:      "11px",
    fontWeight:    "700",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color:         colors.textSecondary,
    marginBottom:  "2px",
  },
  cardValue: {
    margin:       0,
    fontSize:     "13.5px",
    color:        colors.textPrimary,
    overflowWrap: "anywhere",
  },
  cardActions: {
    marginTop:  "12px",
    paddingTop: "12px",
    borderTop:  `1px dashed ${colors.borderLight}`,
  },
  emptyState: {
    display:       "flex",
    flexDirection: "column",
    alignItems:    "center",
    gap:           "10px",
    padding:       "48px 16px",
    textAlign:     "center",
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
    color:     colors.textSecondary,
    fontWeight:"500",
  },
  footer: {
    padding:        "10px 16px",
    borderTop:      `1px solid ${colors.tableRowBorder}`,
    fontSize:       "12px",
    color:          colors.textSecondary,
    fontWeight:     "500",
    background:     colors.tableHeaderBg,
    textAlign:      "right",
  },
};

export default Table;
