import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Banner, Spinner } from "../../components/ui";
import { colors } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getRoutesMap } from "../../services/transportService";

function ViewRoutes() {
  const [routes, setRoutes] = useState([]);
  const [selectedRouteId, setSelectedRouteId] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getRoutesMap()
      .then((response) => {
        const nextRoutes = response.data?.routes || [];
        setRoutes(nextRoutes);
        setSelectedRouteId(nextRoutes[0]?.id ?? null);
      })
      .catch(() => setError("Routes could not be loaded. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  const visibleRoutes = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return routes;
    return routes.filter((route) =>
      [route.name, route.description, ...(route.stops || []).flatMap((stop) => [stop.name, stop.address])]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [routes, search]);

  const selectedRoute = visibleRoutes.find((route) => Number(route.id) === Number(selectedRouteId)) || visibleRoutes[0] || null;

  return (
    <PageShell role="student" title="Routes">
      <PageTitle sub="Browse the route map and the stop list in one organized view.">Routes</PageTitle>

      {error && <Banner variant="danger">{error}</Banner>}
      {loading && <Spinner />}
      {!loading && !routes.length && !error && <Banner variant="info">No published routes are available yet.</Banner>}

      {!loading && !!routes.length && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 340px) minmax(0, 1fr)", gap: 18, alignItems: "start" }}>
          <ContentCard style={{ marginBottom: 0, padding: 14 }}>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: "block", fontSize: 12, color: colors.textSecondary, marginBottom: 6 }}>Search routes or stops</label>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by route, stop, or area…"
                style={{ width: "100%", boxSizing: "border-box", border: `1px solid ${colors.borderMid}`, borderRadius: 8, padding: "10px 12px", fontSize: 14 }}
              />
            </div>

            <div style={{ display: "grid", gap: 10, maxHeight: 520, overflowY: "auto" }}>
              {visibleRoutes.length ? visibleRoutes.map((route) => (
                <button
                  key={route.id}
                  type="button"
                  onClick={() => setSelectedRouteId(route.id)}
                  style={{
                    display: "grid",
                    gap: 4,
                    textAlign: "left",
                    border: `1px solid ${Number(selectedRoute?.id) === Number(route.id) ? colors.accent : colors.borderLight}`,
                    borderRadius: 10,
                    background: Number(selectedRoute?.id) === Number(route.id) ? "#eef6ff" : "#fff",
                    padding: "12px 14px",
                    cursor: "pointer",
                    color: colors.textPrimary,
                  }}
                >
                  <strong style={{ fontSize: 14 }}>{route.name}</strong>
                  <span style={{ fontSize: 12, color: colors.textSecondary }}>{route.stops?.length ?? 0} stop{(route.stops?.length ?? 0) === 1 ? "" : "s"}</span>
                  <small style={{ fontSize: 11, color: colors.textMuted }}>{route.description || "No description available."}</small>
                </button>
              )) : <span style={{ color: colors.textMuted, fontSize: 13, padding: "8px 4px" }}>No routes match your search.</span>}
            </div>
          </ContentCard>

          <div style={{ display: "grid", gap: 16 }}>
            <ContentCard style={{ marginBottom: 0, padding: 12 }}>
              <RouteMap routes={visibleRoutes} selectedRouteId={selectedRoute?.id} onRouteSelect={setSelectedRouteId} height={480} />
            </ContentCard>

            {selectedRoute && (
              <ContentCard style={{ marginBottom: 0, padding: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 18 }}>{selectedRoute.name}</h3>
                  <span style={{ fontSize: 12, background: "#edf7ed", color: "#1d7a3a", borderRadius: 999, padding: "6px 10px", fontWeight: 600 }}>
                    {selectedRoute.status || "Published"}
                  </span>
                </div>

                <p style={{ margin: "0 0 14px", color: colors.textSecondary, fontSize: 13 }}>{selectedRoute.description || "No description provided."}</p>

                <div style={{ display: "grid", gap: 8 }}>
                  {selectedRoute.stops?.map((stop, index) => (
                    <div key={stop.route_stop_id || `${stop.id}-${index}`} style={{ display: "grid", gridTemplateColumns: "22px minmax(0, 1fr) auto auto", gap: 10, alignItems: "center", border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: "8px 10px", background: "#fff" }}>
                      <strong style={{ color: colors.accent }}>{index + 1}</strong>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{stop.name}</div>
                        {stop.address && <div style={{ fontSize: 12, color: colors.textSecondary }}>{stop.address}</div>}
                      </div>
                      <span style={{ fontSize: 11, color: colors.textSecondary }}>{stop.est_morning_eta ? `AM ${stop.est_morning_eta}` : "AM —"}</span>
                      <span style={{ fontSize: 11, color: colors.textSecondary }}>{stop.est_evening_eta ? `PM ${stop.est_evening_eta}` : "PM —"}</span>
                    </div>
                  ))}
                </div>
              </ContentCard>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}

export default ViewRoutes;