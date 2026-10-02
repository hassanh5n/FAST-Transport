import { useNavigate } from "react-router-dom";
import { MeshGradient } from "@paper-design/shaders-react";

function Home() {
  const navigate = useNavigate();

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
        {/* Logo — full lockup; the dark variant has a white wordmark for
            this dark hero, and it replaces the separate text eyebrow. */}
        <img
          src="/fleetcentric-primary-light.svg"
          alt="Fleetcentric.ai"
          style={styles.logoLockup}
        />

        {/* Headline */}
        <h1 style={styles.headline}>
          <span style={styles.glowText}>Student Transport</span><br />
          <span style={styles.headlineDim}>Made Simple</span>
        </h1>

        {/* Subtext */}
        <p style={styles.sub}>
          Track your bus, manage your route, and stay on schedule —<br />
          all in one place.
        </p>

        {/* CTA Buttons */}
        <div style={styles.actions}>
          <button
            style={styles.btnPrimary}
            onClick={() => navigate("/login")}
            onMouseEnter={(e) => Object.assign(e.target.style, styles.btnPrimaryHover)}
            onMouseLeave={(e) => Object.assign(e.target.style, styles.btnPrimary)}
          >
            Sign In
          </button>
          <button
            style={styles.btnSecondary}
            onClick={() => navigate("/signup")}
            onMouseEnter={(e) => Object.assign(e.target.style, styles.btnSecondaryHover)}
            onMouseLeave={(e) => Object.assign(e.target.style, styles.btnSecondary)}
          >
            Create Account
          </button>
        </div>

        {/* Bottom note */}
        <p style={styles.note}>
          © {new Date().getFullYear()} Fleetcentric.ai · Transport Management System
        </p>
      </div>
    </div>
  );
}

const styles = {
  root: {
    position: "relative",
    width: "100vw",
    height: "100vh",
    overflow: "hidden",
    background: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'DM Sans', 'Helvetica Neue', sans-serif",
  },
  glowText: {
    color: "#ffffff",
    textShadow: "0 0 8px rgba(255,255,255,0.35), 0 0 18px rgba(96, 165, 250, 0.25)",
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
    textAlign: "center",
    gap: "20px",
    padding: "0 24px",
    maxWidth: "540px",
    width: "100%",
  },
  logoLockup: {
    width: "min(300px, 72vw)",
    height: "auto",
    display: "block",
    marginBottom: "6px",
  },
  headline: {
    margin: 0,
    fontSize: "clamp(36px, 7vw, 58px)",
    fontWeight: 700,
    color: "#ffffff",
    letterSpacing: "-0.04em",
    lineHeight: 1.1,
  },
  headlineDim: {
    color: "rgba(255,255,255,0.3)",
  },
  sub: {
    margin: 0,
    fontSize: "15px",
    color: "rgba(255,255,255,0.4)",
    lineHeight: 1.7,
    maxWidth: "380px",
  },
  actions: {
    display: "flex",
    gap: "12px",
    marginTop: "8px",
    flexWrap: "wrap",
    justifyContent: "center",
  },
  btnPrimary: {
    background: "#fff",
    color: "#000",
    border: "none",
    borderRadius: "10px",
    padding: "13px 32px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "-0.01em",
    transition: "background 0.2s",
  },
  btnPrimaryHover: {
    background: "#e0e0e0",
    color: "#000",
    border: "none",
    borderRadius: "10px",
    padding: "13px 32px",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "-0.01em",
  },
  btnSecondary: {
    background: "rgba(255,255,255,0.07)",
    color: "rgba(255,255,255,0.8)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: "10px",
    padding: "13px 32px",
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
    letterSpacing: "-0.01em",
    backdropFilter: "blur(8px)",
    transition: "background 0.2s",
  },
  btnSecondaryHover: {
    background: "rgba(255,255,255,0.12)",
    color: "rgba(255,255,255,0.95)",
    border: "1px solid rgba(255,255,255,0.2)",
    borderRadius: "10px",
    padding: "13px 32px",
    fontSize: "14px",
    fontWeight: 500,
    cursor: "pointer",
    letterSpacing: "-0.01em",
    backdropFilter: "blur(8px)",
  },
  note: {
    marginTop: "20px",
    fontSize: "11px",
    color: "rgba(255,255,255,0.15)",
    letterSpacing: "0.03em",
  },
};

export default Home;