import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MeshGradient } from "@paper-design/shaders-react";
import { signup } from "../../services/transportService";
import { validateField } from "../../utils/validation";
import { ErrorText } from "../../components/ui";

function Signup() {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    username: "",
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    roll_number: "",
    department: "",
    batch: "",
    phone: "",
    address: "",
  });

  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleNext = (e) => {
    e.preventDefault();
    const nextErrors = {};

    const u = validateField(formData.username, [
      { check: "required", message: "Username is required" },
    ]);
    if (u) nextErrors.username = u;

    const em = validateField(formData.email, [
      { check: "required", message: "Email is required" },
      { check: "email", message: "Enter a valid email" },
    ]);
    if (em) nextErrors.email = em;

    const p = validateField(formData.password, [
      { check: "required", message: "Password is required" },
      { check: "minLength", arg: 8, message: "Password must be at least 8 characters" },
    ]);
    if (p) nextErrors.password = p;

    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    setErrors({});
    setError("");
    setStep(2);
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setErrors({});

    try {
      const step2Errors = {};

      const r = validateField(formData.roll_number, [
        { check: "required", message: "Roll number is required" },
        { check: "roll", message: "Enter a valid roll number" },
      ]);
      if (r) step2Errors.roll_number = r;

      const ph = formData.phone
        ? validateField(formData.phone, [
            { check: "phone", message: "Enter a valid phone number" },
          ])
        : null;
      if (ph) step2Errors.phone = ph;

      if (Object.keys(step2Errors).length) {
        setErrors(step2Errors);
        setLoading(false);
        return;
      }

      await signup(formData);
      localStorage.setItem("otp_email", formData.email);
      navigate("/verify-otp", {
        state: {
          email: formData.email,
          username: formData.username,
          password: formData.password,
        },
      });
    } catch (err) {
      setError(JSON.stringify(err.response?.data || "Signup failed"));
    } finally {
      setLoading(false);
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
        {/* Brand */}
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

        {/* Card */}
        <div style={styles.card}>
          {/* Header */}
          <div style={styles.cardHeader}>
            <div style={styles.stepRow}>
              <div style={styles.stepPip(step >= 1)} />
              <div style={styles.stepLine(step >= 2)} />
              <div style={styles.stepPip(step >= 2)} />
            </div>
            <h2 style={styles.cardTitle}>
              {step === 1 ? "Create account" : "Student details"}
            </h2>
            <p style={styles.cardDesc}>
              {step === 1
                ? "Step 1 of 2 — Set up your credentials"
                : "Step 2 of 2 — Tell us about yourself"}
            </p>
          </div>

          {/* Error */}
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

          {/* Step 1 */}
          {step === 1 && (
            <form onSubmit={handleNext} style={styles.form}>
              <div style={styles.field}>
                <label style={styles.label}>
                  Username <span style={styles.req}>*</span>
                </label>
                <input
                  name="username"
                  type="text"
                  placeholder="e.g. shayan_22k"
                  value={formData.username}
                  onChange={handleChange}
                  required
                  style={styles.input}
                  onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                  onBlur={(e) => Object.assign(e.target.style, styles.input)}
                />
                {errors.username && <ErrorText>{errors.username}</ErrorText>}
              </div>

              {/* First Name + Last Name */}
              <div style={styles.grid}>
                <div style={styles.field}>
                  <label style={styles.label}>First Name</label>
                  <input
                    name="first_name"
                    type="text"
                    placeholder="e.g. Shayan"
                    value={formData.first_name}
                    onChange={handleChange}
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                </div>
                <div style={styles.field}>
                  <label style={styles.label}>Last Name</label>
                  <input
                    name="last_name"
                    type="text"
                    placeholder="e.g. Khan"
                    value={formData.last_name}
                    onChange={handleChange}
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                </div>
              </div>

              <div style={styles.field}>
                <label style={styles.label}>
                  Email <span style={styles.req}>*</span>
                </label>
                <input
                  name="email"
                  type="email"
                  placeholder="you@nu.edu.pk"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  style={styles.input}
                  onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                  onBlur={(e) => Object.assign(e.target.style, styles.input)}
                />
                {errors.email && <ErrorText>{errors.email}</ErrorText>}
              </div>

              <div style={styles.field}>
                <label style={styles.label}>
                  Password <span style={styles.req}>*</span>
                </label>
                <input
                  name="password"
                  type="password"
                  placeholder="Min. 8 characters"
                  value={formData.password}
                  onChange={handleChange}
                  required
                  style={styles.input}
                  onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                  onBlur={(e) => Object.assign(e.target.style, styles.input)}
                />
                {errors.password && <ErrorText>{errors.password}</ErrorText>}
              </div>

              <button
                type="submit"
                style={styles.button}
                onMouseEnter={(e) => Object.assign(e.target.style, styles.buttonHover)}
                onMouseLeave={(e) => Object.assign(e.target.style, styles.button)}
              >
                Continue →
              </button>
            </form>
          )}

          {/* Step 2 */}
          {step === 2 && (
            <form onSubmit={handleSignup} style={styles.form}>
              <div style={styles.grid}>
                <div style={styles.field}>
                  <label style={styles.label}>
                    Roll Number <span style={styles.req}>*</span>
                  </label>
                  <input
                    name="roll_number"
                    type="text"
                    placeholder="22K-1234"
                    value={formData.roll_number}
                    onChange={handleChange}
                    required
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                  {errors.roll_number && <ErrorText>{errors.roll_number}</ErrorText>}
                </div>

                <div style={styles.field}>
                  <label style={styles.label}>Batch</label>
                  <input
                    name="batch"
                    type="text"
                    placeholder="e.g. 2022"
                    value={formData.batch}
                    onChange={handleChange}
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                </div>

                <div style={styles.field}>
                  <label style={styles.label}>Department</label>
                  <input
                    name="department"
                    type="text"
                    placeholder="e.g. CS, SE"
                    value={formData.department}
                    onChange={handleChange}
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                </div>

                <div style={styles.field}>
                  <label style={styles.label}>Phone</label>
                  <input
                    name="phone"
                    type="text"
                    placeholder="+92 300 0000000"
                    value={formData.phone}
                    onChange={handleChange}
                    style={styles.input}
                    onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                    onBlur={(e) => Object.assign(e.target.style, styles.input)}
                  />
                  {errors.phone && <ErrorText>{errors.phone}</ErrorText>}
                </div>
              </div>

              <div style={styles.field}>
                <label style={styles.label}>Home Address</label>
                <input
                  name="address"
                  type="text"
                  placeholder="Your pickup area"
                  value={formData.address}
                  onChange={handleChange}
                  style={styles.input}
                  onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                  onBlur={(e) => Object.assign(e.target.style, styles.input)}
                />
              </div>

              <div style={styles.btnRow}>
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  style={styles.backButton}
                  onMouseEnter={(e) => Object.assign(e.target.style, styles.backButtonHover)}
                  onMouseLeave={(e) => Object.assign(e.target.style, styles.backButton)}
                >
                  ← Back
                </button>

                <button
                  type="submit"
                  disabled={loading}
                  style={
                    loading
                      ? { ...styles.button, ...styles.buttonDisabled, flex: 1 }
                      : { ...styles.button, flex: 1 }
                  }
                  onMouseEnter={(e) => {
                    if (!loading) Object.assign(e.target.style, { ...styles.buttonHover, flex: 1 });
                  }}
                  onMouseLeave={(e) => {
                    if (!loading) Object.assign(e.target.style, { ...styles.button, flex: 1 });
                  }}
                >
                  {loading ? <span style={styles.spinner} /> : "Create Account"}
                </button>
              </div>
            </form>
          )}

          <p style={styles.footer}>
            Already have an account?{" "}
            <Link to="/login" style={styles.link}>
              Sign in
            </Link>
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
    overflow: "auto",
    background: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'DM Sans', 'Helvetica Neue', sans-serif",
    padding: "20px 0",
    boxSizing: "border-box",
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
    gap: "28px",
    width: "100%",
    maxWidth: "420px",
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
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "20px",
    padding: "clamp(20px, 5vw, 32px) clamp(18px, 4vw, 30px)",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    boxShadow: "0 32px 64px rgba(0,0,0,0.6)",
    boxSizing: "border-box",
  },
  cardHeader: {
    marginBottom: "24px",
  },
  stepRow: {
    display: "flex",
    alignItems: "center",
    gap: "0",
    marginBottom: "18px",
  },
  stepPip: (active) => ({
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: active ? "#fff" : "rgba(255,255,255,0.18)",
    transition: "background 0.3s ease",
    flexShrink: 0,
  }),
  stepLine: (active) => ({
    flex: 1,
    height: "1px",
    background: active ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.12)",
    transition: "background 0.3s ease",
    margin: "0 6px",
  }),
  cardTitle: {
    margin: "0 0 5px",
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
  errorBox: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    background: "rgba(255,107,107,0.08)",
    border: "1px solid rgba(255,107,107,0.2)",
    borderRadius: "10px",
    padding: "10px 14px",
    marginBottom: "18px",
    fontSize: "13px",
    color: "#ff6b6b",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  label: {
    fontSize: "11px",
    fontWeight: 600,
    color: "rgba(255,255,255,0.5)",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
  },
  req: {
    color: "rgba(255,100,100,0.7)",
  },
  input: {
    background: "rgba(255,255,255,0.08)",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: "10px",
    padding: "11px 13px",
    fontSize: "13.5px",
    color: "#fff",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  },
  inputFocus: {
    background: "rgba(255,255,255,0.07)",
    border: "1px solid rgba(255,255,255,0.28)",
    borderRadius: "10px",
    padding: "11px 13px",
    fontSize: "13.5px",
    color: "#fff",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  },
  btnRow: {
    display: "flex",
    gap: "10px",
    marginTop: "4px",
  },
  button: {
    marginTop: "2px",
    background: "#fff",
    color: "#000",
    border: "none",
    borderRadius: "10px",
    padding: "12px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "-0.01em",
    boxSizing: "border-box",
    boxShadow: "0 0 12px rgba(255,255,255,0.5)",
  },
  buttonHover: {
    marginTop: "2px",
    background: "#288dc4",
    color: "#fff",
    border: "none",
    borderRadius: "10px",
    padding: "12px",
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
    boxShadow: "0 0 14px rgba(40,141,196,0.45)",
  },
  buttonDisabled: {
    background: "rgba(255,255,255,0.12)",
    color: "rgba(255,255,255,0.4)",
    cursor: "not-allowed",
  },
  backButton: {
    background: "rgba(255,255,255,0.07)",
    color: "rgba(255,255,255,0.6)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "10px",
    padding: "12px 18px",
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "-0.01em",
    boxSizing: "border-box",
    flexShrink: 0,
  },
  backButtonHover: {
    background: "rgba(255,255,255,0.12)",
    color: "rgba(255,255,255,0.9)",
    border: "1px solid rgba(255,255,255,0.2)",
    borderRadius: "10px",
    padding: "12px 18px",
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    letterSpacing: "-0.01em",
    boxSizing: "border-box",
    flexShrink: 0,
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
    marginTop: "18px",
    textAlign: "center",
    fontSize: "13px",
    color: "rgba(255,255,255,0.35)",
    marginBottom: 0,
  },
  link: {
    color: "rgba(255,255,255,0.75)",
    textDecoration: "none",
    fontWeight: 500,
    borderBottom: "1px solid rgba(255,255,255,0.2)",
    paddingBottom: "1px",
  },
  bottomNote: {
    fontSize: "11px",
    color: "rgba(255,255,255,0.18)",
    letterSpacing: "0.03em",
    textAlign: "center",
    margin: 0,
  },
};

export default Signup;