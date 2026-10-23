// Registers the service worker (production builds only) and, when a new version of
// the app has been downloaded, offers a reload instead of swapping it mid-task.
import { useRegisterSW } from "virtual:pwa-register/react";
import { btn, colors } from "../theme";

export default function UpdatePrompt() {
  const { needRefresh: [needRefresh, setNeedRefresh], updateServiceWorker } = useRegisterSW();
  if (!needRefresh) return null;
  return (
    <div
      role="status"
      style={{
        position: "fixed", left: 16, right: 16, bottom: 16, zIndex: 1000, margin: "0 auto", maxWidth: 420,
        display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 10,
        background: colors.navyDeep, color: "#fff", fontSize: 13, boxShadow: "0 6px 20px rgba(11,45,66,0.3)",
      }}
    >
      <span style={{ flex: 1 }}>A new version of Fleetcentric is ready.</span>
      <button type="button" onClick={() => setNeedRefresh(false)} style={{ ...btn.ghost, padding: "6px 10px", fontSize: 12 }}>Later</button>
      <button type="button" onClick={() => updateServiceWorker(true)} style={{ ...btn.primary, padding: "6px 10px", fontSize: 12 }}>Reload</button>
    </div>
  );
}
