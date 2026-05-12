import React from "react";
import { colors, fonts, radius, btn, input } from "../theme";
import { validateField } from "../utils/validation";

// ── Confirm Modal ─────────────────────────────────────────────────────────────
export function ConfirmModal({ title, message, onConfirm, onCancel, confirmLabel = "Confirm", danger = true }) {
  return (
    <div style={modalStyles.overlay}>
      <div style={modalStyles.box}>
        <div style={modalStyles.iconWrap}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={danger ? colors.dangerText : colors.accent} strokeWidth="2" strokeLinecap="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <h3 style={modalStyles.title}>{title}</h3>
        <p style={modalStyles.message}>{message}</p>
        <div style={modalStyles.actions}>
          <button onClick={onCancel} style={modalStyles.cancelBtn}>Cancel</button>
          <button onClick={onConfirm} style={danger ? modalStyles.dangerBtn : modalStyles.confirmBtn}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Form Modal ────────────────────────────────────────────────────────────────
export function FormModal({ title, sub, children, onSubmit, onClose, submitLabel = "Save", loading = false, width = "560px" }) {
  return (
    <div style={modalStyles.overlay} onMouseDown={onClose}>
      <div style={{ ...modalStyles.box, maxWidth: width }} onMouseDown={(e) => e.stopPropagation()}>
        <div style={modalStyles.header}>
          <div>
            <h3 style={modalStyles.title}>{title}</h3>
            {sub && <p style={modalStyles.message}>{sub}</p>}
          </div>
          <button type="button" onClick={onClose} style={modalStyles.closeBtn} aria-label="Close dialog">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18" />
              <path d="M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form onSubmit={onSubmit} style={modalStyles.form}>
          <div style={modalStyles.formBody}>{children}</div>
          <div style={modalStyles.formActions}>
            <button type="button" onClick={onClose} style={modalStyles.cancelBtn}>Cancel</button>
            <button type="submit" disabled={loading} style={loading ? modalStyles.disabledPrimaryBtn : modalStyles.confirmBtn}>
              {loading ? "Saving…" : submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const modalStyles = {
  overlay: {
    position: "fixed", inset: 0,
    background: "rgba(11,45,66,0.45)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 1000, backdropFilter: "blur(3px)",
  },
  box: {
    background: "#fff", borderRadius: radius.xl,
    padding: "28px 24px", maxWidth: "420px", width: "94%",
    boxShadow: "0 24px 64px rgba(11,45,66,0.22)",
    textAlign: "center",
    maxHeight: "90vh", overflowY: "auto",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "16px",
    marginBottom: "18px",
    textAlign: "left",
  },
  iconWrap: {
    width: "48px", height: "48px", borderRadius: "50%",
    background: colors.dangerBg, display: "flex",
    alignItems: "center", justifyContent: "center",
    margin: "0 auto 16px",
  },
  title: { margin: "0 0 10px", fontSize: "17px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading },
  message: { margin: "0 0 24px", fontSize: "13.5px", color: colors.textSecondary, lineHeight: 1.6 },
  actions: { display: "flex", gap: "10px", justifyContent: "center" },
  cancelBtn: { ...btn.ghost, minWidth: "100px" },
  dangerBtn: { ...btn.danger, minWidth: "120px", fontWeight: "700" },
  confirmBtn: { ...btn.primary, minWidth: "120px" },
  disabledPrimaryBtn: { ...btn.primary, minWidth: "120px", opacity: 0.65, cursor: "progress" },
  closeBtn: {
    ...btn.ghost,
    width: "38px",
    height: "38px",
    borderRadius: radius.pill,
    padding: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "0 0 auto",
  },
  form: { display: "flex", flexDirection: "column", gap: "18px" },
  formBody: { display: "flex", flexWrap: "wrap", gap: "12px" },
  formActions: { display: "flex", gap: "10px", justifyContent: "flex-end" },
};

// ── Status Badge (clickable toggle) ──────────────────────────────────────────
export function StatusBadge({ active, trueLabel = "Active", falseLabel = "Inactive", onClick }) {
  const style = active
    ? { background: colors.successBg, color: colors.successText }
    : { background: colors.neutralBg, color: colors.neutralText };
  return (
    <span
      onClick={onClick}
      title={onClick ? "Click to toggle" : undefined}
      style={{
        ...style,
        fontSize: "11px", fontWeight: "700", padding: "3px 10px",
        borderRadius: radius.pill, cursor: onClick ? "pointer" : "default",
        letterSpacing: "0.04em", textTransform: "uppercase",
        display: "inline-block", userSelect: "none",
      }}
    >
      {active ? trueLabel : falseLabel}
    </span>
  );
}

// ── Priority / status badge (no click) ───────────────────────────────────────
export function Pill({ label, variant = "neutral" }) {
  const map = {
    success:  { background: colors.successBg, color: colors.successText },
    warning:  { background: colors.warningBg, color: colors.warningText },
    danger:   { background: colors.dangerBg,  color: colors.dangerText  },
    info:     { background: colors.infoBg,    color: colors.infoText    },
    neutral:  { background: colors.neutralBg, color: colors.neutralText },
  };
  return (
    <span style={{
      ...(map[variant] || map.neutral),
      fontSize: "11px", fontWeight: "700", padding: "3px 10px",
      borderRadius: radius.pill, letterSpacing: "0.04em",
      textTransform: "uppercase", display: "inline-block",
    }}>
      {label}
    </span>
  );
}

// ── Section block with heading ────────────────────────────────────────────────
export function SectionBlock({ title, sub, children, style }) {
  return (
    <div style={{ marginBottom: "28px", ...style }}>
      <div style={{ marginBottom: "14px" }}>
        <h3 style={sectionStyles.heading}>{title}</h3>
        {sub && <p style={sectionStyles.sub}>{sub}</p>}
      </div>
      {children}
    </div>
  );
}
const sectionStyles = {
  heading: { margin: 0, fontSize: "15px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading },
  sub: { margin: "4px 0 0", fontSize: "12.5px", color: colors.textSecondary },
};

// ── Form card with grid layout ────────────────────────────────────────────────
export function FormCard({ title, sub, onSubmit, children, submitLabel = "Add", loading = false }) {
  return (
    <div style={formCardStyles.card}>
      {title && (
        <div style={{ marginBottom: "16px" }}>
          <h3 style={formCardStyles.title}>{title}</h3>
          {sub && <p style={formCardStyles.sub}>{sub}</p>}
        </div>
      )}
      <form onSubmit={onSubmit} style={formCardStyles.form}>
        {children}
        <button type="submit" disabled={loading} style={{ ...btn.primary, alignSelf: "flex-end", minWidth: "120px", opacity: loading ? 0.6 : 1 }}>
          {loading ? "Saving…" : submitLabel}
        </button>
      </form>
    </div>
  );
}
const formCardStyles = {
  card: {
    background: "#fff", borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
    padding: "20px 24px", marginBottom: "24px",
    boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
  },
  title: { margin: 0, fontSize: "14px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading },
  sub: { margin: "3px 0 0", fontSize: "12px", color: colors.textSecondary },
  form: { display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "flex-end" },
};
// Note: FormCard already uses flexWrap on its form, which handles mobile stacking natively.

// ── Labelled field wrapper ────────────────────────────────────────────────────
export function Field({ label, required, children, flex = "1 1 160px", validators = [] }) {
  const [error, setError] = React.useState(null);

  // If validators are provided and there's a single child element, clone it
  const child = React.Children.count(children) === 1 ? React.Children.only(children) : null;

  const handleBlur = (e) => {
    if (!validators || validators.length === 0) return;
    const v = validateField(e.target.value, validators);
    setError(v);
    if (child?.props?.onBlur) child.props.onBlur(e);
  };

  const renderedChild = child
    ? React.cloneElement(child, { onBlur: handleBlur, style: child.props.style })
    : children;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "5px", flex }}>
      {label && (
        <label style={{ fontSize: "11px", fontWeight: "600", color: colors.textSecondary, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          {label}{required && <span style={{ color: colors.dangerText, marginLeft: 2 }}>*</span>}
        </label>
      )}
      {renderedChild}
      {error && <div style={{ color: colors.dangerText, fontSize: "12px", marginTop: "6px" }}>{error}</div>}
    </div>
  );
}

// ── Styled input (use as a styled wrapper) ────────────────────────────────────
export const inputStyle = {
  ...input,
  transition: "border-color 0.15s",
};

export const selectStyle = {
  ...input,
  appearance: "none",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%238faabb'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  paddingRight: "30px",
  cursor: "pointer",
};

// ── Info banner ───────────────────────────────────────────────────────────────
export function Banner({ variant = "info", children }) {
  const map = {
    info:    { bg: colors.infoBg,    border: "rgba(40,141,196,0.2)",  text: colors.infoText    },
    success: { bg: colors.successBg, border: "rgba(34,197,94,0.25)",  text: colors.successText },
    warning: { bg: colors.warningBg, border: "rgba(245,158,11,0.25)", text: colors.warningText },
    danger:  { bg: colors.dangerBg,  border: "rgba(192,57,43,0.25)",  text: colors.dangerText  },
  };
  const v = map[variant] || map.info;
  return (
    <div style={{
      background: v.bg, border: `1px solid ${v.border}`,
      borderRadius: radius.md, padding: "12px 16px",
      fontSize: "13.5px", color: v.text, lineHeight: 1.6,
      marginBottom: "16px",
    }}>
      {children}
    </div>
  );
}

// ── Spinner / loading state ───────────────────────────────────────────────────
export function Spinner() {
  return (
    <div style={{ padding: "48px 0", display: "flex", flexDirection: "column", alignItems: "center", gap: "14px" }}>
      <div style={{
        width: "28px", height: "28px", borderRadius: "50%",
        border: `3px solid ${colors.borderLight}`,
        borderTopColor: colors.accent,
        animation: "spin 0.7s linear infinite",
      }} />
      <p style={{ margin: 0, fontSize: "13px", color: colors.textMuted }}>Loading…</p>
    </div>
  );
}

// ── Detail row (label + value pair) ──────────────────────────────────────
export function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span className="detail-row-label">{label}</span>
      <span className="detail-row-value">{value ?? "—"}</span>
    </div>
  );
}

export function ErrorText({ children }) {
  return (
    <div style={{ color: colors.dangerText, fontSize: "12px", marginTop: "6px" }}>{children}</div>
  );
}

// Validated input: declarative validators prop -> shows inline error
export function ValidatedInput({ as = "input", validators = [], value, onChange, placeholder, type = "text", name, rows = 3, style, ...rest }) {
  const [error, setError] = React.useState(null);
  const handleBlur = (e) => {
    const v = validateField(e.target.value, validators);
    setError(v);
  };
  const common = {
    name,
    value,
    onChange,
    placeholder,
    onBlur: handleBlur,
    style,
    ...rest,
  };
  return (
    <div>
      {as === "textarea" ? (
        <textarea rows={rows} {...common} />
      ) : (
        <input type={type} {...common} />
      )}
      {error && <div style={{ color: colors.dangerText, fontSize: "12px", marginTop: "6px" }}>{error}</div>}
    </div>
  );
}