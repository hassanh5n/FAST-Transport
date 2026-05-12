import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import { getRouteStops, getDriverById } from "../../services/transportService";
import { colors, fonts, radius } from "../../theme";
import { useBreakpoint } from "../../utils/useBreakpoint";

function ViewRoutes() {
  const [routeStops, setRouteStops] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [driverLoading, setDriverLoading] = useState(false);
  const isMobile = useBreakpoint(768);

  useEffect(() => {
    const loadData = async () => {
      try {
        const res = await getRouteStops();
        setRouteStops(res.data);
      } catch (err) {
        alert("Failed to load routes");
      }
    };
    loadData();
  }, []);

  // ── Fetch driver details on badge click ──
  const handleDriverClick = async (driverId, driverName) => {
    if (!driverId) return;
    setSelectedDriver({ name: driverName, loading: true });
    setDriverLoading(true);
    try {
      const res = await getDriverById(driverId);
      setSelectedDriver(res.data);
    } catch (err) {
      setSelectedDriver({ name: driverName, error: "Could not load driver details." });
    } finally {
      setDriverLoading(false);
    }
  };

  // ── Group by route ──
  const groupedRoutes = routeStops.reduce((acc, rs) => {
    if (!acc[rs.route_name]) acc[rs.route_name] = [];
    acc[rs.route_name].push(rs);
    return acc;
  }, {});

  // ── Filter ──
  const query = searchQuery.toLowerCase().trim();
  const filteredRoutes = Object.keys(groupedRoutes).reduce((acc, routeName) => {
    const stops = groupedRoutes[routeName];
    const busNumber = stops.find((s) => s.bus_number)?.bus_number || "";
    const driverName = stops.find((s) => s.driver_name)?.driver_name || "";
    const routeMatches =
      busNumber.toLowerCase().includes(query) ||
      driverName.toLowerCase().includes(query) ||
      routeName.toLowerCase().includes(query);
    const matchingStops = stops.filter((s) =>
      s.stop_name?.toLowerCase().includes(query)
    );
    if (routeMatches) acc[routeName] = stops;
    else if (matchingStops.length > 0) acc[routeName] = matchingStops;
    return acc;
  }, {});

  const displayRoutes = query ? filteredRoutes : groupedRoutes;

  return (
    <PageShell role="student" title="View Routes">

      {/* ── Top bar ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: "12px", marginBottom: "16px",
      }}>
        <PageTitle sub="Browse all active routes, stops, and drivers.">Available Routes</PageTitle>
        <div style={{
          display: "flex", alignItems: "center",
          border: `1px solid ${colors.borderMid}`, borderRadius: radius.md,
          padding: "6px 12px", background: "#fff", gap: "8px",
          width: isMobile ? "100%" : "320px", maxWidth: "100%",
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)", boxSizing: "border-box",
        }}>
          <input
            type="text"
            placeholder="Search by stop, bus or driver..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ border: "none", outline: "none", fontSize: "14px", flex: 1, background: "transparent", color: colors.textPrimary }}
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} style={{ background: "none", border: "none", cursor: "pointer", color: colors.textMuted, fontSize: "13px" }}>✕</button>
          )}
        </div>
      </div>

      {query && (
        <p style={{ fontSize: "13px", color: colors.textSecondary, marginBottom: "12px" }}>
          {Object.keys(displayRoutes).length === 0
            ? "No results found."
            : `Showing ${Object.keys(displayRoutes).length} route(s) matching "${searchQuery}"`}
        </p>
      )}

      {/* ── Route cards ── */}
      {Object.keys(displayRoutes).map((routeName) => {
        const stops = displayRoutes[routeName];
        const busNumber = stops.find((s) => s.bus_number)?.bus_number || "-";
        const driverName = stops.find((s) => s.driver_name)?.driver_name || "-";
        const driverId = stops.find((s) => s.driver_id)?.driver_id || null;

        return (
          <div key={routeName} style={{
            marginBottom: "20px", padding: isMobile ? "14px" : "16px",
            border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg,
            background: "#fff", boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
          }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              flexWrap: "wrap", gap: "8px",
            }}>
              <h3 style={{ margin: 0, fontSize: "15px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading }}>{routeName}</h3>
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <span style={badgeStyle}>{busNumber}</span>
                <span
                  style={{ ...badgeStyle, cursor: "pointer", textDecoration: "underline dotted" }}
                  onClick={() => handleDriverClick(driverId, driverName)}
                  title="Click to view driver details"
                >
                  Driver: {driverName}
                </span>
              </div>
            </div>

            {/* Table with horizontal scroll on mobile */}
            <div style={{ overflowX: "auto", marginTop: "12px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "360px" }}>
                <thead>
                  <tr style={{ background: colors.tableHeaderBg }}>
                    <th style={thStyle}>Stop</th>
                    <th style={thStyle}>Order</th>
                    <th style={thStyle}>Morning ETA</th>
                    <th style={thStyle}>Evening ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {stops.map((s, idx) => (
                    <tr
                      key={s.id || idx}
                      style={{
                        borderBottom: `1px solid ${colors.tableRowBorder}`,
                        background: highlightStop(s, query) ? "#fffbeb" : "transparent",
                      }}
                    >
                      <td style={tdStyle}>{highlightText(s.stop_name, query)}</td>
                      <td style={tdStyle}>{s.stop_order}</td>
                      <td style={tdStyle}>{s.morning_eta || "-"}</td>
                      <td style={tdStyle}>{s.evening_eta || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      {/* ── Driver Modal ── */}
      {selectedDriver && (
        <div style={overlayStyle} onClick={() => setSelectedDriver(null)}>
          <div style={{ ...modalStyle, width: isMobile ? "90%" : "320px" }} onClick={(e) => e.stopPropagation()}>
            <button style={closeBtnStyle} onClick={() => setSelectedDriver(null)}>✕</button>
            <div style={avatarCircleStyle}>DR</div>
            <h3 style={{ textAlign: "center", margin: "12px 0 4px", fontFamily: fonts.heading }}>
              {selectedDriver.name || "Driver"}
            </h3>
            <p style={{ textAlign: "center", color: colors.textSecondary, fontSize: "13px", margin: "0 0 16px" }}>
              Driver Details
            </p>

            {driverLoading ? (
              <p style={{ textAlign: "center", color: colors.textMuted }}>Loading...</p>
            ) : selectedDriver.error ? (
              <p style={{ textAlign: "center", color: colors.dangerText }}>{selectedDriver.error}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                <ModalDetailRow label="Phone" value={selectedDriver.phone} />
                <ModalDetailRow label="License No." value={selectedDriver.license_number} />
                <ModalDetailRow label="Available" value={selectedDriver.is_available ? "Yes" : "No"} />
              </div>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}

// ── Small reusable row inside modal ──
function ModalDetailRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", background: colors.pageBg, borderRadius: radius.md }}>
      <span style={{ fontSize: "13px", color: colors.textSecondary }}>{label}</span>
      <span style={{ fontSize: "13px", fontWeight: "600", color: colors.textPrimary }}>{value || "-"}</span>
    </div>
  );
}

// ── Helpers ──
function highlightText(text, query) {
  if (!query || !text) return text;
  const regex = new RegExp(`(${query})`, "gi");
  return text.split(regex).map((part, i) =>
    regex.test(part)
      ? <mark key={i} style={{ background: "#fde68a", borderRadius: "3px", padding: "0 2px" }}>{part}</mark>
      : part
  );
}

function highlightStop(stop, query) {
  return query && stop.stop_name?.toLowerCase().includes(query);
}

// ── Styles ──
const badgeStyle = { padding: "4px 10px", borderRadius: "20px", background: colors.infoBg, color: colors.infoText, fontSize: "13px", fontWeight: "500", border: `1px solid rgba(40,141,196,0.2)` };
const thStyle = { textAlign: "left", padding: "8px 12px", fontWeight: "600", fontSize: "11px", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" };
const tdStyle = { padding: "8px 12px", fontSize: "13.5px", color: colors.textPrimary };
const overlayStyle = { position: "fixed", inset: 0, background: "rgba(11,45,66,0.45)", backdropFilter: "blur(3px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 };
const modalStyle = { background: "#fff", borderRadius: "16px", padding: "28px 24px", position: "relative", boxShadow: "0 24px 64px rgba(11,45,66,0.22)", maxWidth: "90%" };
const closeBtnStyle = { position: "absolute", top: "12px", right: "14px", background: "none", border: "none", fontSize: "16px", cursor: "pointer", color: colors.textMuted };
const avatarCircleStyle = { width: "60px", height: "60px", borderRadius: "50%", background: colors.infoBg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "28px", margin: "0 auto", color: colors.accent };

export default ViewRoutes;