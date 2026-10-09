import { useNavigate } from "react-router-dom";
import { MeshGradient } from "@paper-design/shaders-react";
import { BrandMark, BrandWordmark } from "../components/Brand";

function Home() {
  const navigate = useNavigate();

  return (
    <div style={styles.root}>
      <MeshGradient
  style={styles.shader}
  colors={["#0f3247", "#1186d4", "#f5f8de", "#7ccfc4"]}
  distortion={0.5}
  swirl={0.3}
  speed={0.5}
/>

      <div style={styles.grain} />
      {/* Barely-there centre veil so the copy holds up on the light swirls */}
      <div style={styles.veil} />

      <main className="fc-hero" style={styles.container}>
        <div style={styles.brand} translate="no">
          <BrandMark size={76} />
          <BrandWordmark height={36} />
        </div>

        <h1 style={styles.headline}>
          <span style={styles.headlineGlow}>AI-Enabled Transport</span><br />
          <span style={styles.headlineSoft}>Management System</span>
        </h1>

        <p style={styles.sub}>
          Track your bus, manage your route, and stay on schedule, all in one place.
        </p>

        <div style={styles.actions}>
          <button className="fc-btn fc-btn--primary" onClick={() => navigate("/login")}>
            Sign In
          </button>
          <button className="fc-btn fc-btn--glass" onClick={() => navigate("/signup")}>
            Create Account
          </button>
        </div>
      </main>

      <p style={styles.note}>© {new Date().getFullYear()} Fleetcentric.ai</p>
    </div>
  );
}

// One soft shadow for all copy: lifts it off light swirls without looking embossed.
const softShadow = "0 1px 16px rgba(0,22,38,0.22)";

const styles = {
  root: {
    position: "relative",
    width: "100vw",
    minHeight: "100dvh",
    overflow: "hidden",
    background: "#0f3247",
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
  veil: {
    position: "absolute",
    inset: 0,
    zIndex: 1,
    pointerEvents: "none",
    background:
      "radial-gradient(ellipse 55% 45% at 50% 50%, rgba(8,36,56,0.26) 0%, rgba(8,36,56,0.10) 60%, rgba(8,36,56,0) 100%)",
  },
  container: {
    position: "relative",
    zIndex: 2,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    padding: "0 24px",
    maxWidth: "1240px",
    width: "100%",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "14px",
    marginBottom: "34px",
  },
  headline: {
    margin: 0,
    fontSize: "clamp(26px, 2.8vw, 36px)",
    fontWeight: 700,
    color: "#ffffff",
    letterSpacing: "-0.03em",
    lineHeight: 1.12,
  },
  headlineGlow: {
    color: "#ffffff",
    textShadow: "0 0 8px rgba(255,255,255,0.35), 0 0 18px rgba(96,165,250,0.25)",
  },
  headlineSoft: {
    fontSize: "0.86em",
    color: "rgba(255,255,255,0.45)",
  },
  sub: {
    margin: "18px 0 0",
    fontSize: "clamp(13px, 1.1vw, 15px)",
    fontWeight: 400,
    color: "rgba(255,255,255,0.78)",
    lineHeight: 1.6,
    textShadow: softShadow,
  },
  actions: {
    display: "flex",
    gap: "10px",
    marginTop: "28px",
    flexWrap: "wrap",
    justifyContent: "center",
    width: "min(100%, 300px)",
  },
  note: {
    position: "absolute",
    bottom: "22px",
    left: 0,
    right: 0,
    zIndex: 2,
    margin: 0,
    textAlign: "center",
    fontSize: "11px",
    color: "rgba(255,255,255,0.7)",
    letterSpacing: "0.03em",
    textShadow: softShadow,
  },
};

export default Home;
