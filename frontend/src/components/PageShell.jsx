// frontend/src/components/PageShell.jsx
import { useState } from "react";
import Sidebar from "./Sidebar";
import Navbar  from "./Navbar";
import { useBreakpoint } from "../utils/useBreakpoint";
import { colors, fonts } from "../theme";

function PageShell({ role = "student", title, children, maxWidth }) {
  const isMobile = useBreakpoint(768);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div style={styles.root}>
      <Sidebar
        role={role}
        isMobile={isMobile}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div style={styles.main}>
        <Navbar
          title={title}
          isMobile={isMobile}
          onMenuToggle={() => setSidebarOpen(true)}
        />
        <div
          className="page-content"
          style={{
            ...styles.content,
            padding: isMobile ? "16px" : "28px",
            ...(maxWidth ? { maxWidth } : {}),
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

// ── Section heading helper ────────────────────────────────────────────────────
export function PageTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: sub ? "20px" : "24px" }}>
      <h2 style={styles.pageH2}>{children}</h2>
      {sub && <p style={styles.pageSub}>{sub}</p>}
    </div>
  );
}

// ── Content card ─────────────────────────────────────────────────────────────
export function ContentCard({ children, style }) {
  return (
    <div style={{ ...styles.card, ...style }}>
      {children}
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────
const styles = {
  root: {
    display:    "flex",
    minHeight:  "100vh",
    background: colors.pageBg,
    fontFamily: fonts.body,
  },
  main: {
    flex:          1,
    display:       "flex",
    flexDirection: "column",
    minWidth:      0,
  },
  content: {
    flex:     1,
    minWidth: 0,
  },
  pageH2: {
    margin:        0,
    fontSize:      "22px",
    fontWeight:    "700",
    color:         colors.textPrimary,
    letterSpacing: "-0.02em",
    fontFamily:    fonts.heading,
  },
  pageSub: {
    margin:     "5px 0 0",
    fontSize:   "13.5px",
    color:      colors.textSecondary,
    lineHeight: 1.6,
  },
  card: {
    background:   "#fff",
    borderRadius: "12px",
    border:       `1px solid ${colors.borderLight}`,
    padding:      "24px",
    marginBottom: "20px",
    boxShadow:    "0 1px 3px rgba(11,45,66,0.06)",
  },
};

export default PageShell;