import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { MeshGradient } from "@paper-design/shaders-react";
import { getToken, getUser } from "../../services/transportService";

function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const tokenRes = await getToken({ username, password });
      localStorage.setItem("access",  tokenRes.data.access);
      localStorage.setItem("refresh", tokenRes.data.refresh);
      const userRes = await getUser();
      localStorage.setItem("is_staff", userRes.data.is_staff ? "true" : "false");
      localStorage.setItem("username", userRes.data.username);
      navigate(userRes.data.is_staff ? "/admin/dashboard" : "/student/dashboard");
    } catch {
      setError("Invalid username or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.root}>
      <MeshGradient
        style={styles.shader}
        colors={["#0f3247", "#62a1be", "#f5f8de", "#288dc4"]}
        distortion={0.5} swirl={0.3} speed={0.5}
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
            <h2 style={styles.cardTitle}>Welcome Back</h2>
            <p style={styles.cardDesc}>Sign in to your account</p>
          </div>

          {error && (
            <div style={styles.errorBox}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff6b6b" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} style={styles.form}>
            <div style={styles.field}>
              <label style={styles.label}>Username</label>
              <input
                type="text" placeholder="Enter your username"
                value={username} onChange={(e) => setUsername(e.target.value)}
                required style={styles.input}
                onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                onBlur={(e)  => Object.assign(e.target.style, styles.input)}
              />
            </div>

            <div style={styles.field}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <label style={styles.label}>Password</label>
                {/* ── Forgot password link ── */}
                <Link to="/forgot-password" style={styles.forgotLink}>
                  Forgot password?
                </Link>
              </div>
              <input
                type="password" placeholder="Enter your password"
                value={password} onChange={(e) => setPassword(e.target.value)}
                required style={styles.input}
                onFocus={(e) => Object.assign(e.target.style, styles.inputFocus)}
                onBlur={(e)  => Object.assign(e.target.style, styles.input)}
              />
            </div>

            <button
              type="submit" disabled={loading}
              style={loading ? { ...styles.button, ...styles.buttonDisabled } : styles.button}
              onMouseEnter={(e) => { if (!loading) Object.assign(e.target.style, styles.buttonHover); }}
              onMouseLeave={(e) => { if (!loading) Object.assign(e.target.style, styles.button); }}
            >
              {loading ? <span style={styles.spinner} /> : "Sign In"}
            </button>
          </form>

          <p style={styles.footer}>
            Don&apos;t have an account?{" "}
            <Link to="/signup" style={styles.link}>Create one</Link>
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
  root: { position:"relative", width:"100vw", height:"100vh", overflow:"hidden", background:"#000", display:"flex", alignItems:"center", justifyContent:"center", fontFamily:"'DM Sans','Helvetica Neue',sans-serif" },
  shader: { position:"absolute", inset:0, width:"100%", height:"100%", zIndex:0 },
  grain: { position:"absolute", inset:0, zIndex:1, backgroundImage:`url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E")`, backgroundRepeat:"repeat", backgroundSize:"128px 128px", pointerEvents:"none" },
  container: { position:"relative", zIndex:2, display:"flex", flexDirection:"column", alignItems:"center", gap:"32px", width:"100%", maxWidth:"400px", padding:"0 20px", boxSizing:"border-box" },
  brand: { display:"flex", alignItems:"center", gap:"14px" },
  logoMark: { width:"52px", height:"52px", borderRadius:"14px", background:"rgba(255,255,255,0.05)", border:"1px solid rgba(255,255,255,0.12)", display:"flex", alignItems:"center", justifyContent:"center", backdropFilter:"blur(8px)" },
  brandSub: { margin:0, fontSize:"10px", letterSpacing:"0.2em", color:"rgba(255,255,255,0.35)", textTransform:"uppercase", fontWeight:500 },
  brandName: { margin:0, fontSize:"20px", fontWeight:700, color:"#fff", letterSpacing:"-0.02em", lineHeight:1.2 },
  card: { width:"100%", background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.10)", borderRadius:"20px", padding:"36px 32px", backdropFilter:"blur(20px)", WebkitBackdropFilter:"blur(20px)", boxShadow:"0 0 0 1px rgba(255,255,255,0.03), 0 32px 64px rgba(0,0,0,0.5)", boxSizing:"border-box" },
  cardHeader: { marginBottom:"28px" },
  cardTitle: { margin:"0 0 6px", fontSize:"22px", fontWeight:700, color:"#fff", letterSpacing:"-0.03em" },
  cardDesc: { margin:0, fontSize:"13px", color:"rgba(255,255,255,0.4)" },
  errorBox: { display:"flex", alignItems:"center", gap:"8px", background:"rgba(255,107,107,0.08)", border:"1px solid rgba(255,107,107,0.2)", borderRadius:"10px", padding:"10px 14px", marginBottom:"20px", fontSize:"13px", color:"#ff6b6b" },
  form: { display:"flex", flexDirection:"column", gap:"18px" },
  field: { display:"flex", flexDirection:"column", gap:"7px" },
  label: { fontSize:"12px", fontWeight:500, color:"rgba(255,255,255,0.5)", letterSpacing:"0.04em", textTransform:"uppercase" },
  forgotLink: { fontSize:"11px", color:"rgba(255,255,255,0.4)", textDecoration:"none", fontWeight:500, transition:"color 0.15s" },
  input: { background:"rgba(255,255,255,0.05)", border:"1px solid rgba(255,255,255,0.10)", borderRadius:"10px", padding:"12px 14px", fontSize:"14px", color:"#fff", outline:"none", width:"100%", boxSizing:"border-box" },
  inputFocus: { background:"rgba(255,255,255,0.07)", border:"1px solid rgba(255,255,255,0.28)", borderRadius:"10px", padding:"12px 14px", fontSize:"14px", color:"#fff", outline:"none", width:"100%", boxSizing:"border-box" },
  button: { marginTop:"6px", background:"#fff", color:"#000", border:"none", borderRadius:"10px", padding:"13px", fontSize:"14px", fontWeight:600, cursor:"pointer", width:"100%", display:"flex", alignItems:"center", justifyContent:"center", letterSpacing:"-0.01em", boxSizing:"border-box" },
  buttonHover: { marginTop:"6px", background:"#e0e0e0", color:"#000", border:"none", borderRadius:"10px", padding:"13px", fontSize:"14px", fontWeight:600, cursor:"pointer", width:"100%", display:"flex", alignItems:"center", justifyContent:"center", letterSpacing:"-0.01em", boxSizing:"border-box" },
  buttonDisabled: { background:"rgba(255,255,255,0.12)", color:"rgba(255,255,255,0.4)", cursor:"not-allowed" },
  spinner: { width:"16px", height:"16px", border:"2px solid rgba(0,0,0,0.2)", borderTopColor:"#000", borderRadius:"50%", animation:"spin 0.7s linear infinite", display:"inline-block" },
  footer: { marginTop:"20px", textAlign:"center", fontSize:"13px", color:"rgba(255,255,255,0.35)", marginBottom:0 },
  link: { color:"rgba(255,255,255,0.75)", textDecoration:"none", fontWeight:500, borderBottom:"1px solid rgba(255,255,255,0.2)", paddingBottom:"1px" },
  bottomNote: { fontSize:"11px", color:"rgba(255,255,255,0.18)", letterSpacing:"0.03em", textAlign:"center", margin:0 },
};

export default Login;