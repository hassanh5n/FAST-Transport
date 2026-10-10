import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, FormCard, Field } from "../../components/ui";
import { inputStyle } from "../../styles/formStyles";
import { btn } from "../../theme";
import { getStops, createStop, updateStop, deleteStop } from "../../services/transportService";
import StopLocationPicker from "../../components/maps/StopLocationPicker";
import StopImport from "../../components/StopImport";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };

function StopsPage() {
  const [stops, setStops] = useState([]);
  const [form, setForm] = useState({ name: "", latitude: "", longitude: "", address: "" });
  const [pendingDelete, setPendingDelete] = useState(null);
  const [editingStop, setEditingStop] = useState(null);
  const [editForm, setEditForm] = useState({ name: "", latitude: "", longitude: "", address: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchStops = () =>
    getStops()
      .then((res) => setStops(res.data))
      .catch(() => alert("Failed to fetch stops."));

  useEffect(() => { fetchStops(); }, []);

  const clampCoordinate = (name, value) => {
    if (value === "" || value === null || value === undefined) return "";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "";

    if (name === "latitude") return String(Math.max(-90, Math.min(90, numeric)));
    return String(Math.max(-180, Math.min(180, numeric)));
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });
  const setFormLocation = (location) => setForm((current) => ({ ...current, ...location }));

  const handleEditOpen = (stop) => {
    setEditingStop(stop);
    setEditForm({
      name: stop.name || "",
      latitude: stop.latitude ?? "",
      longitude: stop.longitude ?? "",
      address: stop.address || "",
    });
  };

  const handleEditChange = (e) => {
    const { name, value } = e.target;
    if (name === "latitude" || name === "longitude") {
      setEditForm((current) => ({ ...current, [name]: clampCoordinate(name, value) }));
      return;
    }
    setEditForm({ ...editForm, [name]: value });
  };
  const setEditLocation = (location) => setEditForm((current) => ({ ...current, ...location }));

  const handleDelete = (stop) => setPendingDelete(stop);

  const confirmDelete = async () => {
    try {
      await deleteStop(pendingDelete.id);
      setPendingDelete(null);
      fetchStops();
    } catch (err) {
      alert(`Failed to delete stop: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.name) { alert("Stop name is required"); return; }
    if (!Number.isFinite(Number(editForm.latitude)) || !Number.isFinite(Number(editForm.longitude)) || (Number(editForm.latitude) === 0 && Number(editForm.longitude) === 0)) {
      alert("Choose a valid stop location on the map."); return;
    }
    setSavingEdit(true);
    try {
      const payload = Object.fromEntries(Object.entries(editForm).filter(([, v]) => v !== ""));
      if (payload.latitude !== undefined) payload.latitude = Number(payload.latitude);
      if (payload.longitude !== undefined) payload.longitude = Number(payload.longitude);
      await updateStop(editingStop.id, payload);
      setEditingStop(null);
      fetchStops();
    } catch (err) {
      alert(`Failed to update stop: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name) { alert("Stop name is required"); return; }

    const latitude = Number(form.latitude);
    const longitude = Number(form.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude === 0 && longitude === 0) {
      alert("Choose a valid stop location on the map."); return;
    }

    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ""));
      payload.latitude = Number(clampCoordinate("latitude", payload.latitude));
      payload.longitude = Number(clampCoordinate("longitude", payload.longitude));
      await createStop(payload);
      setForm({ name: "", latitude: "", longitude: "", address: "" });
      fetchStops();
    } catch (err) {
      alert(`Failed to add stop: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const columns = [
    { key: "name", label: "Stop Name" },
    { key: "latitude", label: "Latitude" },
    { key: "longitude", label: "Longitude" },
    { key: "address", label: "Address" },
    { key: "created_at", label: "Created At" },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button onClick={() => handleEditOpen(row)} style={actionBtn}>Edit</button>
          <button onClick={() => handleDelete(row)} style={{ ...btn.danger, padding: "7px 12px", fontSize: "12px" }}>Delete</button>
        </div>
      ),
    },
  ];

  return (
    <PageShell role="staff" title="Admin — Stops">
      <PageTitle sub="Manage pickup/dropoff stops.">Stops</PageTitle>
      {pendingDelete && (
        <ConfirmModal
          title="Delete Stop?"
          message={`Deleting stop ${pendingDelete.name} will remove any route stops, semester registrations, transport registrations, and route change requests tied to this stop. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
      {editingStop && (
        <FormModal
          title="Edit Stop"
          sub="Update stop details."
          submitLabel="Save Changes"
          loading={savingEdit}
          onClose={() => setEditingStop(null)}
          onSubmit={handleEditSubmit}
          width="700px"
        >
          <Field label="Stop Name" required flex="1 1 180px">
            <input name="name" placeholder="e.g. Gulshan Chowrangi" value={editForm.name} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Latitude" required flex="0 1 140px">
            <input name="latitude" type="number" step="0.000001" placeholder="24.9215" value={editForm.latitude} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Longitude" required flex="0 1 140px">
            <input name="longitude" type="number" step="0.000001" placeholder="67.0847" value={editForm.longitude} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Address" flex="2 1 280px">
            <input name="address" placeholder="Full address" value={editForm.address} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <div style={{ flex: "1 1 100%" }}>
            <StopLocationPicker latitude={editForm.latitude} longitude={editForm.longitude} onChange={setEditLocation} height={250} />
          </div>
        </FormModal>
      )}
      <FormCard title="Add New Stop" onSubmit={handleSubmit} submitLabel="Add Stop">
        <Field label="Stop Name" required flex="1 1 160px">
          <input name="name" placeholder="e.g. Gulshan Chowrangi" value={form.name} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Latitude" required flex="0 1 130px">
          <input name="latitude" type="number" step="0.000001" placeholder="24.9215" value={form.latitude} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Longitude" required flex="0 1 130px">
          <input name="longitude" type="number" step="0.000001" placeholder="67.0847" value={form.longitude} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Address" flex="2 1 280px">
          <input name="address" placeholder="Full address" value={form.address} onChange={handleChange} style={inputStyle} />
        </Field>
        <div style={{ flex: "1 1 100%" }}>
          <StopLocationPicker latitude={form.latitude} longitude={form.longitude} onChange={setFormLocation} height={260} />
        </div>
      </FormCard>
      <StopImport stops={stops} onChanged={fetchStops} />
      <Table columns={columns} rows={stops} />
    </PageShell>
  );
}

export default StopsPage;
