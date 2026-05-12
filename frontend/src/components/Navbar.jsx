// frontend/src/components/Navbar.jsx
import { useNavigate } from "react-router-dom";
import { colors, fonts, shadow } from "../theme";

// Props:
//   title         – page title string
//   isMobile      – boolean (injected by PageShell)
//   onMenuToggle  – callback to open the sidebar drawer on mobile
function Navbar({ title = "FAST Transport", isMobile = false, onMenuToggle }) {
  const navigate = useNavigate();

  const isStaff  = localStorage.getItem("is_staff") === "true";
  const fullName = localStorage.getItem("full_name")
                || localStorage.getItem("username")
                || "";

  const initials = fullName
    ? fullName.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : isStaff ? "AD" : "ST";

  const handleLogout = () => {
    localStorage.clear();
    navigate("/login");
  };

  return (
    <header style={styles.navbar}>
      <div style={styles.left}>
        {/* Hamburger — mobile only */}
        {isMobile && (
          <button onClick={onMenuToggle} style={styles.hamburger} aria-label="Open menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="6"  x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
        )}

        <div style={styles.titleWrap}>
          {/* Hide eyebrow on mobile to save space */}
          {!isMobile && (
            <p style={styles.eyebrow}>FAST NUCES · Transport</p>
          )}
          <h1 style={isMobile ? styles.titleMobile : styles.title}>{title}</h1>
        </div>
      </div>

      <div style={styles.right}>
        {/* Role badge — hide on mobile */}
        {!isMobile && (
          <span style={isStaff ? styles.roleAdmin : styles.roleStudent}>
            {isStaff ? "Admin" : "Student"}
          </span>
        )}

        {/* Divider — hide on mobile */}
        {!isMobile && <div style={styles.divider} />}

        {/* User chip: show avatar always, name only on desktop */}
        <div style={styles.userChip}>
          <div style={styles.avatar}>{initials}</div>
          {!isMobile && fullName && (
            <span style={styles.username}>{fullName}</span>
          )}
        </div>

        {/* Logout: icon-only on mobile, icon+text on desktop */}
        <button onClick={handleLogout} style={isMobile ? styles.logoutBtnIcon : styles.logoutBtn} title="Sign out">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
          {!isMobile && <span>Sign Out</span>}
        </button>
      </div>
    </header>
  );
}

const styles = {
  navbar: {
    display:        "flex",
    alignItems:     "center",
    justifyContent: "space-between",
    padding:        "0 16px",
    height:         "60px",
    background:     "#fff",
    borderBottom:   `1px solid ${colors.borderLight}`,
    boxShadow:      shadow.navbar,
    fontFamily:     fonts.body,
    gap:            "12px",
    flexShrink:     0,
    position:       "sticky",
    top:            0,
    zIndex:         200,
  },
  left: {
    display:    "flex",
    alignItems: "center",
    gap:        "10px",
    minWidth:   0,
    flex:       1,
  },
  hamburger: {
    background:   "transparent",
    border:       `1px solid ${colors.borderLight}`,
    borderRadius: "8px",
    padding:      "6px",
    cursor:       "pointer",
    display:      "flex",
    alignItems:   "center",
    justifyContent:"center",
    color:        colors.textSecondary,
    flexShrink:   0,
  },
  titleWrap: {
    display:       "flex",
    flexDirection: "column",
    gap:           "1px",
    overflow:      "hidden",
    minWidth:      0,
  },
  eyebrow: {
    margin:        0,
    fontSize:      "10px",
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color:         colors.textMuted,
    fontWeight:    500,
    whiteSpace:    "nowrap",
  },
  title: {
    margin:        0,
    fontSize:      "16px",
    fontWeight:    "700",
    color:         colors.textPrimary,
    letterSpacing: "-0.02em",
    whiteSpace:    "nowrap",
    overflow:      "hidden",
    textOverflow:  "ellipsis",
    fontFamily:    fonts.heading,
  },
  titleMobile: {
    margin:        0,
    fontSize:      "15px",
    fontWeight:    "700",
    color:         colors.textPrimary,
    letterSpacing: "-0.02em",
    whiteSpace:    "nowrap",
    overflow:      "hidden",
    textOverflow:  "ellipsis",
    fontFamily:    fonts.heading,
  },
  right: {
    display:    "flex",
    alignItems: "center",
    gap:        "8px",
    flexShrink: 0,
  },
  roleAdmin: {
    fontSize:      "10.5px",
    fontWeight:    "700",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    padding:       "4px 10px",
    borderRadius:  "999px",
    background:    "rgba(40,141,196,0.1)",
    color:         colors.accent,
    border:        `1px solid rgba(40,141,196,0.2)`,
  },
  roleStudent: {
    fontSize:      "10.5px",
    fontWeight:    "700",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    padding:       "4px 10px",
    borderRadius:  "999px",
    background:    "rgba(34,197,94,0.08)",
    color:         "#15803d",
    border:        "1px solid rgba(34,197,94,0.2)",
  },
  divider: {
    width:      "1px",
    height:     "22px",
    background: colors.borderLight,
  },
  userChip: {
    display:      "flex",
    alignItems:   "center",
    gap:          "8px",
    padding:      "4px 8px 4px 4px",
    borderRadius: "999px",
    background:   colors.pageBg,
    border:       `1px solid ${colors.borderLight}`,
  },
  avatar: {
    width:          "28px",
    height:         "28px",
    borderRadius:   "50%",
    background:     colors.accent,
    color:          "#fff",
    fontSize:       "10px",
    fontWeight:     "800",
    display:        "flex",
    alignItems:     "center",
    justifyContent: "center",
    letterSpacing:  "0.04em",
    flexShrink:     0,
  },
  username: {
    fontSize:     "13px",
    fontWeight:   "600",
    color:        colors.textPrimary,
    maxWidth:     "140px",
    overflow:     "hidden",
    textOverflow: "ellipsis",
    whiteSpace:   "nowrap",
  },
  logoutBtn: {
    display:      "flex",
    alignItems:   "center",
    gap:          "6px",
    padding:      "7px 14px",
    background:   "transparent",
    border:       `1px solid ${colors.borderMid}`,
    borderRadius: "9px",
    color:        colors.textSecondary,
    fontSize:     "13px",
    fontWeight:   "500",
    cursor:       "pointer",
    fontFamily:   fonts.body,
    flexShrink:   0,
  },
  // Icon-only variant for mobile
  logoutBtnIcon: {
    display:       "flex",
    alignItems:    "center",
    justifyContent:"center",
    padding:       "7px",
    background:    "transparent",
    border:        `1px solid ${colors.borderMid}`,
    borderRadius:  "9px",
    color:         colors.textSecondary,
    cursor:        "pointer",
    fontFamily:    fonts.body,
    flexShrink:    0,
  },
};

export default Navbar;