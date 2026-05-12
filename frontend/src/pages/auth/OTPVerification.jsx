import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { MeshGradient } from "@paper-design/shaders-react";
import api from "../../services/api";
import { getToken, getUser } from "../../services/transportService";
import { validateField } from "../../utils/validation";
import { ErrorText } from "../../components/ui";

function OTPVerification() {
  const location = useLocation();
  const navigate = useNavigate();

  const email = location.state?.email || localStorage.getItem("otp_email");
  const username = location.state?.username || "";
  const password = location.state?.password || "";

  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fieldError, setFieldError] = useState("");

  const handleVerify = async () => {
    const v = validateField(otp, [{ check: "required", message: "Please enter your OTP" }, { check: "otp6", message: "Enter a 6-digit numeric code" }]);
    if (v) { setFieldError(v); return; }
    setFieldError("");
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await api.post("/api/verify-otp/", { email, otp });
      localStorage.removeItem("otp_email");
      setSuccess("Email verified! Logging you in...");
    } catch (err) {
      setError(err.response?.data?.detail || "OTP verification failed");
      setLoading(false);
      return; // stop here if verify failed
    }

    // Verify succeeded — now auto-login
    try {
      const tokenRes = await getToken({ username, password });
      localStorage.setItem("access", tokenRes.data.access);
      localStorage.setItem("refresh", tokenRes.data.refresh);
      const userRes = await getUser();
      localStorage.setItem("is_staff", userRes.data.is_staff ? "true" : "false");
      localStorage.setItem("username", userRes.data.username);
      localStorage.setItem("full_name", userRes.data.full_name || "");
      navigate(userRes.data.is_staff ? "/admin/dashboard" : "/student/dashboard");
    } catch {
      // Auto-login failed (e.g. credentials not in state) — graceful fallback
      navigate("/login", { state: { message: "Account verified! Please log in." } });
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError("");
    setSuccess("");
    try {
      await api.post("/api/resend-otp/", { email });
      setSuccess("A new OTP has been sent to your email.");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to resend OTP");
    }
  };

  return (
    <div style={styles.root}>
      <MeshGradient
        style={styles.shader}
        colors={["#0f3247", "#62a1be", "#f5f8de", "#288dc4"]}
        distortion={0.5}
        swirl={0.3}
        speed={0.5}
      />
      <div style={styles.grain} />

      <div style={styles.container}>
        <div style={styles.brand}>
          <div style={styles.logoMark}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <rect x="2" y="8" width="24" height="12" rx="2" stroke="white" strokeWidth="1.5" />
              <circle cx="8" cy="22" r="3" fill="white" />
              <circle cx="20" cy="22" r="3" fill="white" />
              <path d="M2 12h6l2-4h8l2 4" stroke="white" strokeWidth="1.5" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <p style={styles.brandSub}>FAST NUCES</p>
            <h1 style={styles.brandName}>Transport Portal</h1>
          </div>
        </div>

        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <h2 style={styles.cardTitle}>Verify your email</h2>
            <p style={styles.cardDesc}>
              Enter the 6-digit code sent to <span style={styles.emailHighlight}>{email}</span>
            </p>
          </div>

          {error && (
            <div style={styles.errorBox}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff6b6b" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div style={styles.successBox}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4caf50" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="9 12 11 14 15 10" />
              </svg>
              <span>{success}</span>
            </div>
          )}

          <div style={styles.form}>
            <div style={styles.field}>
              <label style={styles.label}>OTP Code</label>
              <input
                type="text"
                placeholder="Enter 6-digit code"
                value={otp}
                maxLength={6}
                onChange={(e) => setOtp(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleVerify()}
                style={styles.input}
                onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                onBlur={(e) => Object.assign(e.target.style, styles.input)}
              />
                  {fieldError && <ErrorText>{fieldError}</ErrorText>}
            </div>

            <button
              onClick={handleVerify}
              disabled={loading}
              style={loading ? { ...styles.button, ...styles.buttonDisabled } : styles.button}
              onMouseEnter={(e) => { if (!loading) Object.assign(e.target.style, styles.buttonHover); }}
              onMouseLeave={(e) => { if (!loading) Object.assign(e.target.style, styles.button); }}
            >
              {loading ? <span style={styles.spinner} /> : "Verify & Continue"}
            </button>
          </div>

          <p style={styles.footer}>
            Didn&apos;t receive a code?{" "}
            <button onClick={handleResend} style={styles.resendBtn}>Resend OTP</button>
          </p>
        </div>

        <p style={styles.bottomNote}>
          © {new Date().getFullYear()} FAST-NUCES · Transport Management System
        </p>
      </div>
    </div>
  );
}

const styles = {
  root: {
    position: "relative",
    width: "100vw",
    minHeight: "100vh",
    overflow: "hidden",
    background: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'DM Sans', 'Helvetica Neue', sans-serif",
  },
  shader: {
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
    zIndex: 0,
  },
  grain: {
    position: "absolute",
    inset: 0,
    zIndex: 1,
    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E")`,
    backgroundRepeat: "repeat",
    backgroundSize: "128px 128px",
    pointerEvents: "none",
  },
  container: {
    position: "relative",
    zIndex: 2,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "32px",
    width: "100%",
    maxWidth: "400px",
    padding: "0 20px",
    boxSizing: "border-box",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "14px",
  },
  logoMark: {
    width: "52px",
    height: "52px",
    borderRadius: "14px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.12)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backdropFilter: "blur(8px)",
  },
  brandSub: {
    margin: 0,
    fontSize: "10px",
    letterSpacing: "0.2em",
    color: "rgba(255,255,255,0.35)",
    textTransform: "uppercase",
    fontWeight: 500,
  },
  brandName: {
    margin: 0,
    fontSize: "20px",
    fontWeight: 700,
    color: "#fff",
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
  },
  card: {
    width: "100%",
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(255,255,255,0.10)",
    borderRadius: "20px",
    padding: "36px 32px",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    boxShadow: "0 32px 64px rgba(0,0,0,0.6)",
    boxSizing: "border-box",
  },
  cardHeader: {
    marginBottom: "28px",
  },
  cardTitle: {
    margin: "0 0 6px",
    fontSize: "22px",
    fontWeight: 700,
    color: "#fff",
    letterSpacing: "-0.03em",
  },
  cardDesc: {
    margin: 0,
    fontSize: "13px",
    color: "rgba(255,255,255,0.4)",
  },
  emailHighlight: {
    color: "rgba(255,255,255,0.7)",
    fontWeight: 500,
  },
  errorBox: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    background: "rgba(255,107,107,0.08)",
    border: "1px solid rgba(255,107,107,0.2)",
    borderRadius: "10px",
    padding: "10px 14px",
    marginBottom: "20px",
    fontSize: "13px",
    color: "#ff6b6b",
  },
  successBox: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    background: "rgba(76,175,80,0.08)",
    border: "1px solid rgba(76,175,80,0.2)",
    borderRadius: "10px",
    padding: "10px 14px",
    marginBottom: "20px",
    fontSize: "13px",
    color: "#4caf50",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "18px",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "7px",
  },
  label: {
    fontSize: "12px",
    fontWeight: 500,
    color: "rgba(255,255,255,0.5)",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  },
  input: {
    background: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: "10px",
    padding: "12px 14px",
    fontSize: "14px",
    color: "#fff",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
    letterSpacing: "0.15em",
  },
  inputFocus: {
    background: "rgba(255,255,255,0.07)",
    border: "1px solid rgba(255,255,255,0.28)",
    borderRadius: "10px",
    padding: "12px 14px",
    fontSize: "14px",
    color: "#fff",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
    letterSpacing: "0.15em",
  },
  button: {
    marginTop: "6px",
    background: "#fff",
    color: "#000",
    border: "none",
    borderRadius: "10px",
    padding: "13px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "-0.01em",
    boxSizing: "border-box",
  },
  buttonHover: {
    marginTop: "6px",
    background: "#288dc4",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    padding: "13px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "-0.01em",
    boxSizing: "border-box",
    transform: "translateY(-1px)",
    boxShadow:
      "0 0 12px rgba(40, 141, 196, 0.55), 0 0 28px rgba(40, 141, 196, 0.25)",
  },
  buttonDisabled: {
    background: "rgba(255,255,255,0.12)",
    color: "rgba(255,255,255,0.4)",
    cursor: "not-allowed",
  },
  spinner: {
    width: "16px",
    height: "16px",
    border: "2px solid rgba(255,255,255,0.3)",
    borderTopColor: "#fff",
    borderRadius: "50%",
    animation: "spin 0.7s linear infinite",
    display: "inline-block",
  },
  footer: {
    marginTop: "20px",
    textAlign: "center",
    fontSize: "13px",
    color: "rgba(255,255,255,0.35)",
    marginBottom: 0,
  },
  resendBtn: {
    background: "none",
    border: "none",
    padding: 0,
    color: "rgba(255,255,255,0.75)",
    fontWeight: 500,
    fontSize: "13px",
    cursor: "pointer",
    borderBottom: "1px solid rgba(255,255,255,0.2)",
    paddingBottom: "1px",
    fontFamily: "inherit",
  },
  bottomNote: {
    fontSize: "11px",
    color: "rgba(255,255,255,0.18)",
    letterSpacing: "0.03em",
    textAlign: "center",
    margin: 0,
  },
};

export default OTPVerification;