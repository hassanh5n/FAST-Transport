import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, StatusBadge, FormCard, Field, SectionBlock } from "../../components/ui";
import { inputStyle } from "../../styles/formStyles";
import { btn, colors } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import { getRoutes, createRoute, updateRoute, deleteRoute, getRoutesMap, watchRoutesMap, getRoutePlans } from "../../services/transportService";
import { useContractor, ContractorSwitch, ContractorSelect } from "../../components/ContractorSwitch";
import RoadLineBuilder from "../../components/RoadLineBuilder";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };

const routeLinkStyle = {
  color: colors.accent,
  fontWeight: 600,
  textDecoration: "none",
  borderBottom: `1px dotted ${colors.accent}`,
  cursor: "pointer",
};

const routeButton = {
  display: "grid",
  textAlign: "left",
  gap: 4,
  border: "1px solid",
  borderRadius: 8,
  background: "#fff",
  padding: "10px 12px",
  cursor: "pointer",
  color: colors.textPrimary,
  fontSize: 13,
};

function RoutesPage() {
  const contractor = useContractor();
  const [allRoutes, setRoutes] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", contractor: "" });
  const [pendingToggle, setPendingToggle] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [allMapRoutes, setMapRoutes] = useState([]);
  const routes = allRoutes.filter((r) => contractor.matches(r.contractor));
  const mapRoutes = allMapRoutes.filter((r) => contractor.matches(r.contractor));
  const [selectedRouteId, setSelectedRouteId] = useState(null);
  const [activePlan, setActivePlan] = useState(null);

  const fetchRoutes = () =>
    getRoutes().then((res) => setRoutes(res.data)).catch(() => alert("Failed to fetch routes."));

  const showMap = (data) => {
    const nextRoutes = data?.routes || [];
    setMapRoutes(nextRoutes);
    setSelectedRouteId((current) => current ?? nextRoutes[0]?.id ?? null);
  };

  useEffect(() => {
    getRoutePlans().then((res) => setActivePlan(res.data.find((plan) => plan.is_active) || null)).catch(() => {});
    // The saved network shows at once; a failed refresh keeps it on screen.
    let shown = false;
    watchRoutesMap((data) => { shown = true; showMap(data); }).catch(() => { if (!shown) setMapRoutes([]); });
  }, []);

  const handleToggle = (id, currentValue) => {
    if (currentValue) setPendingToggle({ id, currentValue });
    else doToggle(id, currentValue);
  };

  const doToggle = async (id, currentValue) => {
    try {
      await updateRoute(id, { is_active: !currentValue });
      fetchRoutes();
    } catch (err) {
      alert(`Failed to update route: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });
  useEffect(() => { fetchRoutes(); }, []);

  const handleDelete = (route) => setPendingDelete(route);

  const confirmDelete = async () => {
    try {
      await deleteRoute(pendingDelete.id);
      setPendingDelete(null);
      fetchRoutes();
    } catch (err) {
      alert(`Failed to delete route: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name) { alert("Route name is required"); return; }
    try {
      await createRoute({ ...form, contractor: form.contractor || null });
      setForm({ name: "", description: "", contractor: "" });
      fetchRoutes();
    } catch (err) {
      alert(`Failed to add route: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const selectedRoute = useMemo(() =>
    mapRoutes.find((route) => Number(route.id) === Number(selectedRouteId)) || mapRoutes[0] || null,
    [mapRoutes, selectedRouteId]
  );

  const columns = [
    { key: "id", label: "ID", width: "6%" },
    {
      key: "name",
      label: "Name",
      width: "25%",
      render: (row) => (
        <Link to={`/admin/routes/${row.id}`} style={routeLinkStyle} title="View route details and registered students">
          {row.name}
        </Link>
      ),
    },
    { key: "contractor", label: "Contractor", width: "10%", render: (row) => contractor.nameOf(row.contractor) || "—" },
    { key: "description", label: "Description", width: "20%" },
    {
      key: "is_active", label: "Status",
      width: "15%",
      render: (row) => <StatusBadge active={row.is_active} onClick={() => handleToggle(row.id, row.is_active)} />,
    },
    {
      key: "actions",
      label: "Actions",
      width: "35%",
      render: (row) => (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-start" }}>
          <Link to={`/admin/routes/${row.id}`} style={{ ...actionBtn, textDecoration: "none" }}>View Details</Link>
          <Link to={`/admin/routes/${row.id}/edit`} style={{ ...actionBtn, textDecoration: "none" }}>Edit Route</Link>
          <button onClick={() => handleDelete(row)} style={{ ...btn.danger, padding: "7px 12px", fontSize: "12px" }}>Delete</button>
        </div>
      ),
    },
  ];

  return (
    <PageShell role="staff" title="Admin — Routes">
      {pendingToggle && (
        <ConfirmModal
          title="Deactivate Route?"
          message="Setting this route to inactive will also automatically deactivate all corresponding assignments linked to it."
          confirmLabel="Yes, Deactivate"
          onConfirm={() => { doToggle(pendingToggle.id, pendingToggle.currentValue); setPendingToggle(null); }}
          onCancel={() => setPendingToggle(null)}
        />
      )}

      {pendingDelete && (
        <ConfirmModal
          title="Delete Route?"
          message={`Deleting route ${pendingDelete.name} will remove its route stops, active assignments, and any registrations or change requests that point to it. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      <PageTitle sub="Manage transport routes. Use the map to browse route coverage, then open a route for full administration.">Routes</PageTitle>
      <ContractorSwitch value={contractor} />
      <RoadLineBuilder onDone={() => getRoutesMap({ noCache: true }).then((res) => showMap(res.data)).catch(() => {})} />
      {activePlan && (
        <p style={{ margin: "-8px 0 16px", fontSize: 13, color: colors.textSecondary }}>
          Active route plan: <strong>{activePlan.name}</strong>. Changes here go live for everyone.{" "}
          <Link to="/admin/route-plans" style={routeLinkStyle}>Switch or export plans</Link>
        </p>
      )}

      <ContentCard style={{ marginBottom: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 320px) minmax(0, 1fr)", gap: 16, alignItems: "start" }}>
          <div>
            <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>Route network</h3>
            <div style={{ display: "grid", gap: 8, maxHeight: 420, overflowY: "auto" }}>
              {mapRoutes.length ? mapRoutes.map((route) => (
                <button
                  key={route.id}
                  type="button"
                  onClick={() => setSelectedRouteId(route.id)}
                  style={{
                    ...routeButton,
                    borderColor: Number(selectedRouteId) === Number(route.id) ? colors.accent : colors.borderLight,
                    background: Number(selectedRouteId) === Number(route.id) ? "#eff6ff" : "#fff",
                  }}
                >
                  <strong>{route.name}</strong>
                  <span>{route.stops?.length ?? 0} stop{(route.stops?.length ?? 0) === 1 ? "" : "s"}{route.contractor ? ` · ${contractor.nameOf(route.contractor)}` : ""}</span>
                  <small style={{ color: colors.textMuted }}>{route.status || "published"}</small>
                </button>
              )) : <span style={{ color: colors.textMuted, fontSize: 13 }}>Map data is not available yet.</span>}
            </div>
          </div>
          <div>
            <RouteMap routes={mapRoutes} selectedRouteId={selectedRouteId} onRouteSelect={setSelectedRouteId} height={420} />
            {selectedRoute && (
              <div style={{ marginTop: 12, padding: "12px 14px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                  <strong style={{ fontSize: 14 }}>{selectedRoute.name}</strong>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <Link to={`/admin/routes/${selectedRoute.id}`} style={routeLinkStyle}>View Details</Link>
                    <Link to={`/admin/routes/${selectedRoute.id}/edit`} style={routeLinkStyle}>Edit Route</Link>
                  </div>
                </div>
                <p style={{ margin: 0, color: colors.textSecondary, fontSize: 13 }}>{selectedRoute.description || "No description provided."}</p>
                <div style={{ marginTop: 10, display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, color: colors.textSecondary }}>
                  <span><strong>{selectedRoute.stops?.length ?? 0}</strong> stops</span>
                  <span><strong>{selectedRoute.status || "published"}</strong> status</span>
                  <span>{selectedRoute.is_active ? "Active" : "Inactive"}</span>
                </div>
                <div style={{ marginTop: 10, fontSize: 12, color: colors.textSecondary }}>
                  {selectedRoute.stops?.slice(0, 6).map((stop, index) => (
                    <div key={stop.route_stop_id || `${stop.id}-${index}`} style={{ marginTop: 4 }}>{index + 1}. {stop.name}</div>
                  ))}
                  {(selectedRoute.stops?.length ?? 0) > 6 && <div style={{ marginTop: 4 }}>…and {selectedRoute.stops.length - 6} more stops</div>}
                </div>
              </div>
            )}
          </div>
        </div>
      </ContentCard>

      <FormCard title="Add New Route" onSubmit={handleSubmit} submitLabel="Add Route">
        <Field label="Route Name" required flex="1 1 160px">
          <input name="name" placeholder="e.g. Gulshan Route" value={form.name} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Description" flex="2 1 280px">
          <input name="description" placeholder="Brief description" value={form.description} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Contractor" flex="1 1 140px">
          <ContractorSelect contractors={contractor.contractors} value={form.contractor} onChange={handleChange} />
        </Field>
      </FormCard>

      <SectionBlock title="Active Routes">
        <Table columns={columns} rows={routes.filter(r => r.is_active)} emptyMessage="No active routes." />
      </SectionBlock>

      <SectionBlock title="Inactive Routes">
        <Table columns={columns} rows={routes.filter(r => !r.is_active)} emptyMessage="No inactive routes." />
      </SectionBlock>
    </PageShell>
  );
}

export default RoutesPage;
