// Readability layer for the auth pages (login, signup, OTP, forgot/reset).
// The mesh gradient swings from deep navy to near-cream, so faint white text
// on a clear card disappeared on the light swirls. This tints the glass and
// lifts text contrast; each page keeps its own layout and sizing.

const patch = {
  card: {
    background: "rgba(6,28,44,0.40)",
    border: "1px solid rgba(255,255,255,0.18)",
    backdropFilter: "blur(24px) saturate(150%)",
    WebkitBackdropFilter: "blur(24px) saturate(150%)",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.12), 0 32px 64px rgba(0,16,28,0.45)",
  },
  cardDesc: { color: "rgba(255,255,255,0.78)", fontSize: "14px", lineHeight: 1.5 },
  emailHighlight: { color: "#fff" },
  label: { color: "rgba(255,255,255,0.88)", textTransform: "none", letterSpacing: 0, fontSize: "13px", fontWeight: 500 },
  input: { background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.24)" },
  inputFocus: { background: "rgba(255,255,255,0.14)", border: "1px solid rgba(255,255,255,0.6)" },
  button: { color: "#00254D" },
  forgotLink: { color: "rgba(255,255,255,0.85)", fontSize: "12px" },
  footer: { color: "rgba(255,255,255,0.75)" },
  link: { color: "#fff", borderBottom: "1px solid rgba(255,255,255,0.5)" },
  resendBtn: { color: "#fff", borderBottom: "1px solid rgba(255,255,255,0.5)" },
  bottomNote: { color: "rgba(255,255,255,0.7)", fontSize: "12px", textShadow: "0 1px 8px rgba(0,22,38,0.4)" },
};

const scrim = {
  position: "absolute",
  inset: 0,
  zIndex: 1,
  pointerEvents: "none",
  background:
    "radial-gradient(ellipse 70% 65% at 50% 50%, rgba(4,26,42,0.36) 0%, rgba(4,26,42,0.18) 55%, rgba(4,26,42,0) 90%)",
};

export function refineAuthStyles(styles) {
  const out = { ...styles, scrim };
  for (const [key, extra] of Object.entries(patch)) {
    if (out[key] && typeof out[key] === "object") out[key] = { ...out[key], ...extra };
  }
  return out;
}
