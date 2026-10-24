import { useState } from "react";

// Password field with a show/hide toggle. Takes the page's own input styles so it
// matches each auth form; focus styling is handled here instead of in onFocus/onBlur.
export default function PasswordInput({ style, focusStyle, onFocus, onBlur, ...props }) {
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState(false);
  const inputStyle = { ...style, ...(focused ? focusStyle : null), paddingRight: "44px" };

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <input
        {...props}
        type={visible ? "text" : "password"}
        style={inputStyle}
        onFocus={(e) => { setFocused(true); onFocus?.(e); }}
        onBlur={(e) => { setFocused(false); onBlur?.(e); }}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        onMouseDown={(e) => e.preventDefault()} // keep the cursor in the field
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        title={visible ? "Hide password" : "Show password"}
        style={toggleStyle}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {visible ? (
            <>
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
              <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </>
          ) : (
            <>
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </>
          )}
        </svg>
      </button>
    </div>
  );
}

const toggleStyle = {
  position: "absolute", right: "6px", top: "50%", transform: "translateY(-50%)",
  width: "32px", height: "32px", padding: 0, border: "none", borderRadius: "8px",
  background: "transparent", color: "rgba(255,255,255,0.6)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
};
