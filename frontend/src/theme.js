
export const colors = {
  // Core brand
  navyDeep:    "#0b2d42",   // sidebar background
  navyMid:     "#0f3a55",   // navbar background
  navyLight:   "#1a4a68",   // hover on sidebar
  accent:      "#288dc4",   // sky blue — active indicator, dots, fills
  accentStrong:"#1d79ad",   // accent behind white text (buttons, badges): 4.8:1, WCAG AA
  accentLight: "#62a1be",   // lighter blue — secondary badges, hover tints
  accentGlow:  "rgba(40, 141, 196, 0.12)", // subtle glow for active bg

  // Page surface
  pageBg:      "#f0f4f8",   // main content background
  cardBg:      "#ffffff",
  borderLight: "#e2e8f0",
  borderMid:   "#cbd5e1",

  // Text
  textPrimary:   "#0f1f2d",
  textSecondary: "#4a6178",
  textMuted:     "#5b7489",   // secondary labels; 4.9:1 on white (AA)
  textOnDark:    "#ffffff",
  textOnDarkDim: "rgba(255,255,255,0.45)",

  // Status
  successBg:   "#eaf7ee",
  successText: "#1e6e3c",
  successDot:  "#22c55e",
  warningBg:   "#fff8e6",
  warningText: "#92650a",
  warningDot:  "#f59e0b",
  dangerBg:    "#fef2f2",
  dangerText:  "#c0392b",
  dangerDot:   "#ef4444",
  infoBg:      "#e8f4fd",
  infoText:    "#1a5e8a",
  infoDot:     "#288dc4",
  neutralBg:   "#f1f5f9",
  neutralText: "#4a6178",

  // Table
  tableHeaderBg:    "#f8fafc",
  tableRowHover:    "rgba(40, 141, 196, 0.04)",
  tableRowAlt:      "#fafcff",
  tableRowBorder:   "#edf2f7",
};

export const fonts = {
  heading: "'Outfit', 'DM Sans', sans-serif",
  body:    "'DM Sans', system-ui, sans-serif",
};

export const radius = {
  sm:  "6px",
  md:  "10px",
  lg:  "14px",
  xl:  "20px",
  pill:"999px",
};

export const shadow = {
  card:   "0 1px 3px rgba(11,45,66,0.08), 0 4px 16px rgba(11,45,66,0.04)",
  modal:  "0 24px 64px rgba(11,45,66,0.22)",
  navbar: "0 1px 0 rgba(0,0,0,0.12)",
};

// ── Shared component style helpers ──────────────────────────────────────────

export const card = {
  background:   colors.cardBg,
  borderRadius: radius.lg,
  boxShadow:    shadow.card,
  border:       `1px solid ${colors.borderLight}`,
  padding:      "24px",
  marginBottom: "20px",
};

export const badge = (variant = "neutral") => {
  const map = {
    success: { background: colors.successBg, color: colors.successText },
    warning: { background: colors.warningBg, color: colors.warningText },
    danger:  { background: colors.dangerBg,  color: colors.dangerText  },
    info:    { background: colors.infoBg,    color: colors.infoText    },
    neutral: { background: colors.neutralBg, color: colors.neutralText },
  };
  return {
    ...(map[variant] || map.neutral),
    fontSize:     "11px",
    fontWeight:   "600",
    padding:      "3px 10px",
    borderRadius: radius.pill,
    display:      "inline-flex",
    alignItems:   "center",
    gap:          "5px",
    letterSpacing:"0.02em",
    textTransform:"uppercase",
  };
};

export const btn = {
  primary: {
    background:   colors.accentStrong,
    color:        "#fff",
    border:       "none",
    borderRadius: radius.md,
    padding:      "9px 18px",
    fontSize:     "13px",
    fontWeight:   "600",
    cursor:       "pointer",
    letterSpacing:"-0.01em",
    transition:   "background 0.15s",
  },
  ghost: {
    background:   "transparent",
    color:        colors.textSecondary,
    border:       `1px solid ${colors.borderMid}`,
    borderRadius: radius.md,
    padding:      "9px 18px",
    fontSize:     "13px",
    fontWeight:   "500",
    cursor:       "pointer",
  },
  danger: {
    background:   colors.dangerBg,
    color:        colors.dangerText,
    border:       `1px solid rgba(192,57,43,0.2)`,
    borderRadius: radius.md,
    padding:      "9px 18px",
    fontSize:     "13px",
    fontWeight:   "600",
    cursor:       "pointer",
  },
};

// ── Input style ──────────────────────────────────────────────────────────────
export const input = {
  background:   "#fff",
  border:       `1px solid ${colors.borderMid}`,
  borderRadius: radius.md,
  padding:      "9px 13px",
  fontSize:     "13px",
  color:        colors.textPrimary,
  outline:      "none",
  width:        "100%",
  boxSizing:    "border-box",
  fontFamily:   fonts.body,
};