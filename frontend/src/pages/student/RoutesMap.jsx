import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Banner, Spinner } from "../../components/ui";
import { colors } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getRoutesMap } from "../../services/transportService";

export default function RoutesMap() {
  const [routes, setRoutes] = useState([]);
  const [selectedRouteId, setSelectedRouteId] = useState(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRoutesMap()
      .then((response) => {
        const nextRoutes = response.data.routes || [];
        setRoutes(nextRoutes);
        setSelectedRouteId(nextRoutes[0]?.id || null);
      })
      .catch(() => setError("Routes could not be loaded. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  const visibleRoutes = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return routes;
    return routes.filter((route) =>
      [route.name, route.description, ...route.stops.flatMap((stop) => [stop.name, stop.address])]
        .filter(Boolean).some((value) => value.toLowerCase().includes(query))
    );
  }, [routes, search]);
  const selectedRoute = routes.find((route) => route.id === selectedRouteId) || visibleRoutes[0];

  return (
    <PageShell role="student" title="Route Map">
      <PageTitle sub="Explore every available route and its pickup stops visually.">Route Map</PageTitle>
      {error && <Banner variant="danger">{error}</Banner>}
      {loading && <Spinner />}
      {!loading && !routes.length && error === "" && <Banner variant="info">No published routes are available yet.</Banner>}
      {!!routes.length && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 340px) minmax(0, 1fr)", gap: 16, alignItems: "start" }}>
          <ContentCard style={{ marginBottom: 0 }}>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search route or stop…" style={searchStyle} aria-label="Search routes and stops" />
            <div style={{ display: "grid", gap: 8, marginTop: 14, maxHeight: 420, overflowY: "auto" }}>
              {visibleRoutes.map((route) => (
                <button key={route.id} onClick={() => setSelectedRouteId(route.id)} style={{ ...routeButton, borderColor: route.id === selectedRoute?.id ? colors.accent : colors.borderLight }}>
                  <strong>{route.name}</strong>
                  <span>{route.stops.length} stop{route.stops.length === 1 ? "" : "s"}</span>
                </button>
              ))}
              {!visibleRoutes.length && <span style={{ color: colors.textMuted, fontSize: 13 }}>No routes match your search.</span>}
            </div>
          </ContentCard>
          <div>
            <RouteMap routes={visibleRoutes} selectedRouteId={selectedRoute?.id} onRouteSelect={setSelectedRouteId} height={480} />
            {selectedRoute && (
              <ContentCard style={{ marginTop: 16 }}>
                <h3 style={{ margin: "0 0 4px" }}>{selectedRoute.name}</h3>
                <p style={{ margin: "0 0 12px", color: colors.textSecondary, fontSize: 13 }}>{selectedRoute.description}</p>
                <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
                  {selectedRoute.stops.map((stop) => <li key={stop.route_stop_id} style={{ fontSize: 13 }}><strong>{stop.name}</strong>{stop.est_morning_eta && ` · AM ${stop.est_morning_eta}`}{stop.est_evening_eta && ` · PM ${stop.est_evening_eta}`}</li>)}
                </ol>
              </ContentCard>
            )}
          </div>
        </div>
      )}
    </PageShell>
  );
}

const searchStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${colors.borderMid}`, borderRadius: 8, padding: "10px 12px", fontSize: 14 };
const routeButton = { display: "grid", textAlign: "left", gap: 4, border: "1px solid", borderRadius: 8, background: "#fff", padding: "10px 12px", cursor: "pointer", color: colors.textPrimary, fontSize: 13 };
