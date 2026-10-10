import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageShell, { ContentCard, PageTitle } from "../../components/PageShell";
import { Banner, Spinner, Pill, ConfirmModal, FormModal, Field } from "../../components/ui";
import { inputStyle } from "../../styles/formStyles";
import { btn, colors } from "../../theme";
import RouteMap from "../../components/maps/RouteMap";
import StopLocationPicker from "../../components/maps/StopLocationPicker";
import { getRouteMapDetail, getStops, saveRouteBuilder, createStop, updateRoute, updateStop } from "../../services/transportService";
import { routeGeometry } from "../../services/routingService";
import StopImport from "../../components/StopImport";

const usableStops = (res) => (res.data?.results || res.data || [])
  .filter((stop) => stop.is_active !== false && Number(stop.latitude) !== 0 && Number(stop.longitude) !== 0);

const stopCardStyle = {
  display: "grid",
  gridTemplateColumns: "1fr auto",
  alignItems: "start",
  gap: 12,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 10,
  padding: 12,
  background: "#fff",
};

const stopHeaderStyle = {
  display: "grid",
  gap: 4,
};

const stopMetaStyle = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
  fontSize: 12,
  color: colors.textSecondary,
  marginTop: 6,
};

const etaRowStyle = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 8,
  marginTop: 10,
};

const etaFieldStyle = {
  display: "grid",
  gap: 4,
};

const etaLabelStyle = {
  fontSize: 11,
  color: colors.textSecondary,
  fontWeight: 500,
};

const controlsStyle = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  alignItems: "stretch",
};

export default function RouteBuilder() {
  const { id } = useParams();
  const [route, setRoute] = useState(null);
  const [routeMeta, setRouteMeta] = useState({ name: "", description: "" });
  const [allStops, setAllStops] = useState([]);
  const [selectedStops, setSelectedStops] = useState([]);
  const [saving, setSaving] = useState(false);
  const [savingRouteMeta, setSavingRouteMeta] = useState(false);
  const [pendingRouteMetaSave, setPendingRouteMetaSave] = useState(false);
  const [message, setMessage] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [expandedStops, setExpandedStops] = useState(new Set());
  const [etaEditingStops, setEtaEditingStops] = useState(new Set());
  const [showCreateStop, setShowCreateStop] = useState(false);
  const [showEditStop, setShowEditStop] = useState(false);
  const [newStopForm, setNewStopForm] = useState({ name: "", latitude: "", longitude: "", address: "" });
  const [editingStop, setEditingStop] = useState(null);
  const [editStopForm, setEditStopForm] = useState({ name: "", latitude: "", longitude: "", address: "" });
  const [creatingStop, setCreatingStop] = useState(false);
  const [savingEditStop, setSavingEditStop] = useState(false);
  const [previewGeometry, setPreviewGeometry] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reloadStops = () => getStops().then((res) => setAllStops(usableStops(res))).catch(() => {});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getRouteMapDetail(id), getStops()])
      .then(([routeResponse, stopsResponse]) => {
        if (cancelled) return;
        const routeData = routeResponse.data;
        setRoute(routeData);
        setRouteMeta({ name: routeData.name || "", description: routeData.description || "" });
        const orderedStops = routeData.stops || [];
        setSelectedStops(orderedStops);
        setExpandedStops(new Set(orderedStops.map((stop) => Number(stop.id))));
        setEtaEditingStops(new Set());
        setAllStops(usableStops(stopsResponse));
        setError("");
      })
      .catch(() => {
        if (!cancelled) {
          setError("Route data could not be loaded.");
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const addStop = (stop) => {
    const stopId = Number(stop.stopId ?? stop.id);
    if (selectedStops.some((item) => Number(item.id) === stopId)) return;
    const source = allStops.find((item) => Number(item.id) === stopId);
    if (!source) return;
    setSelectedStops((items) => [...items, { ...source, morning_eta: "", evening_eta: "", stop_order: items.length + 1 }]);
    setExpandedStops((prev) => new Set([...prev, stopId]));
  };

  const removeStop = (stopId) => setSelectedStops((items) => items.filter((item) => Number(item.id) !== Number(stopId)));
  const moveStop = (index, direction) => setSelectedStops((items) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= items.length) return items;
    const next = [...items];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    return next.map((item, itemIndex) => ({ ...item, stop_order: itemIndex + 1 }));
  });
  const setEta = (index, field, value) => setSelectedStops((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item));
  const toggleStopExpanded = (stopId) => setExpandedStops((prev) => {
    const next = new Set(prev);
    next.has(stopId) ? next.delete(stopId) : next.add(stopId);
    return next;
  });

  const handleEtaEdit = (stopId) => {
    setExpandedStops((prev) => new Set(prev).add(Number(stopId)));
    setEtaEditingStops((prev) => {
      const next = new Set(prev);
      next.has(Number(stopId)) ? next.delete(Number(stopId)) : next.add(Number(stopId));
      return next;
    });
  };

  const handleCreateStopChange = (e) => {
    const { name, value } = e.target;
    if (name === "latitude" || name === "longitude") {
      const numeric = Number(value);
      if (value === "" || !Number.isFinite(numeric)) {
        setNewStopForm({ ...newStopForm, [name]: "" });
      } else if (name === "latitude") {
        setNewStopForm({ ...newStopForm, [name]: String(Math.max(-90, Math.min(90, numeric))) });
      } else {
        setNewStopForm({ ...newStopForm, [name]: String(Math.max(-180, Math.min(180, numeric))) });
      }
      return;
    }
    setNewStopForm({ ...newStopForm, [name]: value });
  };

  const setNewStopLocation = (location) => setNewStopForm((current) => ({ ...current, ...location }));

  const openEditStop = (stop) => {
    setEditingStop(stop);
    setEditStopForm({
      name: stop.name || "",
      latitude: stop.latitude ?? "",
      longitude: stop.longitude ?? "",
      address: stop.address || "",
    });
    setShowEditStop(true);
  };

  const handleEditStopChange = (e) => {
    const { name, value } = e.target;
    if (name === "latitude" || name === "longitude") {
      const numeric = Number(value);
      if (value === "" || !Number.isFinite(numeric)) {
        setEditStopForm((current) => ({ ...current, [name]: "" }));
      } else if (name === "latitude") {
        setEditStopForm((current) => ({ ...current, [name]: String(Math.max(-90, Math.min(90, numeric))) }));
      } else {
        setEditStopForm((current) => ({ ...current, [name]: String(Math.max(-180, Math.min(180, numeric))) }));
      }
      return;
    }
    setEditStopForm((current) => ({ ...current, [name]: value }));
  };

  const setEditStopLocation = (location) => setEditStopForm((current) => ({ ...current, ...location }));

  const handleCreateStop = async (e) => {
    e.preventDefault();
    if (!newStopForm.name) { alert("Stop name is required"); return; }
    const lat = Number(newStopForm.latitude);
    const lng = Number(newStopForm.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) {
      alert("Choose a valid stop location on the map."); return;
    }
    setCreatingStop(true);
    try {
      const payload = {
        name: newStopForm.name,
        latitude: lat,
        longitude: lng,
        address: newStopForm.address || "",
      };
      const response = await createStop(payload);
      const newStop = response.data;
      setAllStops((prev) => [...prev, newStop]);
      addStop(newStop);
      setNewStopForm({ name: "", latitude: "", longitude: "", address: "" });
      setShowCreateStop(false);
      setMessage(`Stop "${newStop.name}" created and added to route.`);
    } catch (err) {
      alert(`Failed to create stop: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setCreatingStop(false);
    }
  };

  const handleEditStop = async (e) => {
    e.preventDefault();
    if (!editingStop) return;
    if (!editStopForm.name) { alert("Stop name is required"); return; }
    const lat = Number(editStopForm.latitude);
    const lng = Number(editStopForm.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) {
      alert("Choose a valid stop location on the map."); return;
    }
    setSavingEditStop(true);
    try {
      const payload = {
        name: editStopForm.name.trim(),
        latitude: lat,
        longitude: lng,
        address: editStopForm.address || "",
      };
      const response = await updateStop(editingStop.id, payload);
      const updatedStop = response.data;
      setAllStops((prev) => prev.map((stop) => Number(stop.id) === Number(updatedStop.id) ? updatedStop : stop));
      setSelectedStops((prev) => prev.map((stop) => Number(stop.id) === Number(updatedStop.id) ? { ...stop, ...updatedStop } : stop));
      setMessage(`Stop "${updatedStop.name}" updated successfully.`);
      setShowEditStop(false);
      setEditingStop(null);
      setEditStopForm({ name: "", latitude: "", longitude: "", address: "" });
    } catch (err) {
      alert(`Failed to update stop: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingEditStop(false);
    }
  };

  const selectedStopIds = new Set(selectedStops.map((s) => Number(s.id)));
  const filteredStops = allStops.filter((stop) => {
    if (!searchTerm.trim()) return true;
    const query = searchTerm.toLowerCase();
    return (
      stop.name?.toLowerCase().includes(query) ||
      stop.address?.toLowerCase().includes(query)
    );
  });
  const availableStops = filteredStops.filter((s) => !selectedStopIds.has(Number(s.id)));

  useEffect(() => {
    let cancelled = false;
    if (selectedStops.length < 2) {
      setPreviewGeometry(null);
      return undefined;
    }
    setPreviewGeometry(null);
    routeGeometry(selectedStops).then((geometry) => {
      if (!cancelled) setPreviewGeometry(geometry);
    });
    return () => { cancelled = true; };
  }, [selectedStops]);

  const previewMap = useMemo(() => route ? [{ ...route, stops: selectedStops, geometry: previewGeometry || { type: "LineString", coordinates: selectedStops.map((stop) => [Number(stop.longitude), Number(stop.latitude)]) } }] : [], [route, selectedStops, previewGeometry]);

  const handleRouteMetaChange = (e) => {
    const { name, value } = e.target;
    setRouteMeta((current) => ({ ...current, [name]: value }));
  };

  const saveRouteMetaDetails = async () => {
    if (!routeMeta.name.trim()) {
      setMessage("Route name is required.");
      return;
    }
    setSavingRouteMeta(true);
    setMessage("");
    try {
      const response = await updateRoute(id, {
        name: routeMeta.name.trim(),
        description: routeMeta.description.trim(),
      });
      setRoute(response.data);
      setRouteMeta({ name: response.data.name || "", description: response.data.description || "" });
      setMessage("Route details updated successfully.");
    } catch (err) {
      setMessage(`Failed to update route details: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingRouteMeta(false);
    }
  };

  const confirmRouteMetaSave = async () => {
    setPendingRouteMetaSave(false);
    await saveRouteMetaDetails();
  };

  const save = async () => {
    if (!selectedStops.length) { setMessage("Add at least one stop before saving."); return; }
    setSaving(true); setMessage("");
    try {
      const geometry = await routeGeometry(selectedStops);
      const response = await saveRouteBuilder(id, {
        stops: selectedStops.map((stop) => ({ stop_id: stop.id, morning_eta: stop.morning_eta || null, evening_eta: stop.evening_eta || null })),
        geometry,
        status: "published",
      });
      setRoute(response.data);
      setSelectedStops(response.data.stops);
      setMessage("Route saved and published successfully.");
      setShowSaveConfirm(false);
    } catch (error) {
      setMessage(error.response?.data?.stops?.[0] || "The route could not be saved.");
    } finally { setSaving(false); }
  };

  if (loading) return <PageShell role="staff" title="Route Builder"><Spinner /></PageShell>;
  if (error) return <PageShell role="staff" title="Route Builder"><Banner variant="danger">{error}</Banner></PageShell>;

  return (
    <PageShell role="staff" title="Route Manager">
      {showSaveConfirm && (
        <ConfirmModal
          title="Publish Route?"
          message={`This will save ${selectedStops.length} stop${selectedStops.length !== 1 ? "s" : ""} and publish the route. Existing registrations will not be affected.`}
          confirmLabel="Publish"
          onConfirm={save}
          onCancel={() => setShowSaveConfirm(false)}
        />
      )}

      {pendingRouteMetaSave && (
        <ConfirmModal
          title="Save Route Details?"
          message="This will update the route name and description for the current route. Continue?"
          confirmLabel="Save Changes"
          onConfirm={confirmRouteMetaSave}
          onCancel={() => setPendingRouteMetaSave(false)}
        />
      )}

      {showEditStop && editingStop && (
        <FormModal
          title="Edit Stop"
          sub="Update the stop details and map location."
          submitLabel="Save Stop"
          loading={savingEditStop}
          onClose={() => { setShowEditStop(false); setEditingStop(null); setEditStopForm({ name: "", latitude: "", longitude: "", address: "" }); }}
          onSubmit={handleEditStop}
          width="700px"
        >
          <Field label="Stop Name" required flex="1 1 180px">
            <input name="name" placeholder="e.g. Gulshan Chowrangi" value={editStopForm.name} onChange={handleEditStopChange} style={inputStyle} />
          </Field>
          <Field label="Latitude" required flex="0 1 140px">
            <input name="latitude" type="number" step="0.000001" placeholder="24.9215" value={editStopForm.latitude} onChange={handleEditStopChange} style={inputStyle} />
          </Field>
          <Field label="Longitude" required flex="0 1 140px">
            <input name="longitude" type="number" step="0.000001" placeholder="67.0847" value={editStopForm.longitude} onChange={handleEditStopChange} style={inputStyle} />
          </Field>
          <Field label="Address" flex="2 1 280px">
            <input name="address" placeholder="Full address" value={editStopForm.address} onChange={handleEditStopChange} style={inputStyle} />
          </Field>
          <div style={{ flex: "1 1 100%" }}>
            <StopLocationPicker latitude={editStopForm.latitude} longitude={editStopForm.longitude} onChange={setEditStopLocation} height={250} />
          </div>
        </FormModal>
      )}

      {showCreateStop && (
        <FormModal
          title="Create New Stop"
          sub="Add a new pickup/dropoff stop to the system. You'll add it to the route immediately after."
          submitLabel="Create Stop"
          loading={creatingStop}
          onClose={() => { setShowCreateStop(false); setNewStopForm({ name: "", latitude: "", longitude: "", address: "" }); }}
          onSubmit={handleCreateStop}
          width="700px"
        >
          <Field label="Stop Name" required flex="1 1 180px">
            <input name="name" placeholder="e.g. Gulshan Chowrangi" value={newStopForm.name} onChange={handleCreateStopChange} style={inputStyle} />
          </Field>
          <Field label="Latitude" required flex="0 1 140px">
            <input name="latitude" type="number" step="0.000001" placeholder="24.9215" value={newStopForm.latitude} onChange={handleCreateStopChange} style={inputStyle} />
          </Field>
          <Field label="Longitude" required flex="0 1 140px">
            <input name="longitude" type="number" step="0.000001" placeholder="67.0847" value={newStopForm.longitude} onChange={handleCreateStopChange} style={inputStyle} />
          </Field>
          <Field label="Address" flex="2 1 280px">
            <input name="address" placeholder="Full address" value={newStopForm.address} onChange={handleCreateStopChange} style={inputStyle} />
          </Field>
          <div style={{ flex: "1 1 100%" }}>
            <StopLocationPicker latitude={newStopForm.latitude} longitude={newStopForm.longitude} onChange={setNewStopLocation} height={250} />
          </div>
        </FormModal>
      )}

      <Link to="/admin/routes" style={{ color: colors.textSecondary, fontSize: 13 }}>← Back to routes</Link>
      <PageTitle sub="View and edit route stops, track registrations, and monitor driver/bus assignments.">{route?.name || "Route Manager"}</PageTitle>

      {message && <Banner variant={message.includes("saved") || message.includes("successfully") ? "success" : "danger"}>{message}</Banner>}

      <ContentCard
        style={{
          marginBottom: 18,
          background: colors.bgTertiary,
          border: `1px solid ${colors.borderLight}`,
          boxShadow: "none",
          padding: 14,
        }}
      >
        <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 600, color: colors.textSecondary }}>Route details</h3>
        <div style={{ display: "grid", gap: 12 }}>
          <Field label="Route Name" required flex="1 1 240px">
            <input name="name" value={routeMeta.name} onChange={handleRouteMetaChange} placeholder="e.g. Gulshan Route" style={inputStyle} />
          </Field>
          <Field label="Description" flex="1 1 100%">
            <textarea name="description" value={routeMeta.description} onChange={handleRouteMetaChange} placeholder="Brief route description" rows={3} style={{ ...inputStyle, resize: "vertical", minHeight: 80 }} />
          </Field>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
          <button onClick={() => setPendingRouteMetaSave(true)} disabled={savingRouteMeta} style={{ ...btn.ghost, minWidth: 150, fontSize: 13 }}>
            {savingRouteMeta ? "Saving…" : "Save Details"}
          </button>
        </div>
      </ContentCard>

      {/* ─── Route Builder Section ─────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 1fr)", gap: 16, alignItems: "start", marginBottom: 24 }}>
        {/* Left: Maps and Stop Selection */}
        <div style={{ display: "grid", gap: 16 }}>
          <ContentCard>
            <h3 style={{ margin: "0 0 12px", fontSize: 15, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              Route Preview
              <span style={{ fontSize: 12, color: colors.textSecondary }}>
                {selectedStops.length} stop{selectedStops.length !== 1 ? "s" : ""}
              </span>
            </h3>
            {selectedStops.length > 0 ? (
              <RouteMap routes={previewMap} height={360} />
            ) : (
              <div style={{ height: 360, display: "flex", alignItems: "center", justifyContent: "center", background: colors.bgTertiary, borderRadius: 10, color: colors.textMuted, fontSize: 14 }}>
                No stops selected yet. Add stops from the list below.
              </div>
            )}
            <p style={{ marginTop: 10, fontSize: 12, color: colors.textSecondary }}>
              {selectedStops.length > 1
                ? `Route with ${selectedStops.length} stops.`
                : selectedStops.length === 1
                ? "Add at least one more stop to form a route."
                : "Click on stops to add them to your route."}
            </p>
          </ContentCard>

          <ContentCard>
            <h3 style={{ margin: "0 0 12px", fontSize: 15 }}>Available Stops</h3>
            <input
              type="text"
              placeholder="Search stops by name or address…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ ...inputStyle, marginBottom: 12, width: "100%" }}
            />
            <button
              onClick={() => setShowCreateStop(true)}
              type="button"
              style={{ ...btn.ghost, marginBottom: 12, width: "100%", fontSize: 13 }}
            >
              + Create New Stop
            </button>
            <StopImport stops={allStops} onChanged={reloadStops} />
            <div style={{ display: "grid", gap: 8, maxHeight: 400, overflowY: "auto" }}>
              {availableStops.length > 0 ? (
                availableStops.map((stop) => (
                  <div key={stop.id} style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 8, alignItems: "stretch" }}>
                    <button
                      onClick={() => addStop(stop)}
                      type="button"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr auto",
                        gap: 10,
                        alignItems: "start",
                        border: `1px solid ${colors.borderLight}`,
                        borderRadius: 8,
                        padding: 10,
                        background: "#fff",
                        cursor: "pointer",
                        textAlign: "left",
                        transition: "all 0.2s",
                        fontSize: 13,
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = colors.accent)}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = colors.borderLight)}
                    >
                      <div>
                        <strong>{stop.name}</strong>
                        <div style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>{stop.address}</div>
                      </div>
                      <div style={{ fontSize: 11, color: colors.accent, fontWeight: 600, whiteSpace: "nowrap" }}>+ Add</div>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); openEditStop(stop); }}
                      style={{ ...btn.ghost, padding: "8px 10px", fontSize: 11, minWidth: 52 }}
                    >
                      Edit
                    </button>
                  </div>
                ))
              ) : (
                <div style={{ color: colors.textMuted, fontSize: 13, padding: "20px 10px", textAlign: "center" }}>
                  {selectedStopIds.size > 0 ? "All stops added!" : "No stops found."}
                </div>
              )}
            </div>
          </ContentCard>
        </div>

        {/* Right: Route Configuration */}
        <ContentCard>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h3 style={{ margin: 0, fontSize: 15 }}>Route Configuration</h3>
            {route && <Pill label={route.status || "published"} variant={route.status === "draft" ? "warning" : "success"} />}
          </div>

          <div style={{ display: "grid", gap: 3, marginBottom: 16, padding: "10px 12px", background: colors.bgTertiary, borderRadius: 8, fontSize: 13 }}>
            <div><strong>Total Stops:</strong> {selectedStops.length}</div>
            <div><strong>Status:</strong> {route?.status === "draft" ? "Draft (not published)" : "Ready to publish"}</div>
          </div>

          {selectedStops.length === 0 ? (
            <div style={{ padding: "20px 12px", textAlign: "center", color: colors.textMuted, fontSize: 13 }}>
              No stops selected. Add stops from the available list to configure this route.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {selectedStops.map((stop, index) => (
                <div key={stop.id} style={stopCardStyle}>
                  <div style={stopHeaderStyle}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                      <strong style={{ fontSize: 16, color: colors.accent, minWidth: "24px" }}>{index + 1}.</strong>
                      <button
                        onClick={() => toggleStopExpanded(stop.id)}
                        type="button"
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          textAlign: "left",
                          padding: 0,
                          fontSize: 13,
                          fontWeight: 600,
                          color: colors.textPrimary,
                        }}
                      >
                        {stop.name}
                      </button>
                    </div>
                    <div style={stopMetaStyle}>
                      <span>{stop.address}</span>
                    </div>
                    {expandedStops.has(stop.id) && (
                      <div style={etaRowStyle}>
                        <div style={etaFieldStyle}>
                          <label style={etaLabelStyle}>Morning ETA</label>
                          <input
                            type="time"
                            value={stop.morning_eta || ""}
                            onChange={(e) => setEta(index, "morning_eta", e.target.value)}
                            style={{ ...inputStyle, opacity: etaEditingStops.has(Number(stop.id)) ? 1 : 0.8 }}
                            aria-label={`Morning ETA for ${stop.name}`}
                            disabled={!etaEditingStops.has(Number(stop.id))}
                          />
                        </div>
                        <div style={etaFieldStyle}>
                          <label style={etaLabelStyle}>Evening ETA</label>
                          <input
                            type="time"
                            value={stop.evening_eta || ""}
                            onChange={(e) => setEta(index, "evening_eta", e.target.value)}
                            style={{ ...inputStyle, opacity: etaEditingStops.has(Number(stop.id)) ? 1 : 0.8 }}
                            aria-label={`Evening ETA for ${stop.name}`}
                            disabled={!etaEditingStops.has(Number(stop.id))}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                  <div style={controlsStyle}>
                    <button onClick={() => moveStop(index, -1)} disabled={index === 0} title="Move up" style={{ ...btn.ghost, padding: "6px 8px", fontSize: 13 }}>↑</button>
                    <button onClick={() => moveStop(index, 1)} disabled={index === selectedStops.length - 1} title="Move down" style={{ ...btn.ghost, padding: "6px 8px", fontSize: 13 }}>↓</button>
                    <button onClick={() => handleEtaEdit(stop.id)} title="Adjust ETA" style={{ ...btn.ghost, padding: "6px 8px", fontSize: 11 }}>Adjust ETA</button>
                    <button onClick={() => removeStop(stop.id)} title="Remove stop" style={{ ...btn.danger, padding: "6px 8px", fontSize: 11 }}>Remove</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={() => setShowSaveConfirm(true)}
            disabled={saving || selectedStops.length === 0}
            style={{ ...btn.primary, marginTop: 16, width: "100%" }}
          >
            {saving ? "Publishing…" : "Save & Publish Route"}
          </button>

          <p style={{ marginTop: 10, fontSize: 12, color: colors.textSecondary, margin: "10px 0 0" }}>
            💡 Tip: Click stop names to expand and set morning/evening ETAs.
          </p>
        </ContentCard>
      </div>

    </PageShell>
  );
}
