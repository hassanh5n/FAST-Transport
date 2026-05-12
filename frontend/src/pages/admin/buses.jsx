import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, StatusBadge, FormCard, Field, SectionBlock, inputStyle } from "../../components/ui";
import { colors, fonts, radius, btn } from "../../theme";
import { getBuses, createBus, updateBus, deleteBus } from "../../services/transportService";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };

function BusesPage() {
  const [buses, setBuses] = useState([]);
  const [form, setForm] = useState({ bus_number: "", capacity: "", model: "", tracker_token: "" });
  const [pendingToggle, setPendingToggle] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [editingBus, setEditingBus] = useState(null);
  const [editForm, setEditForm] = useState({ bus_number: "", capacity: "", model: "", tracker_token: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchBuses = () =>
    getBuses().then((res) => setBuses(res.data)).catch(() => alert("Failed to fetch buses."));

  const handleToggle = (id, currentValue) => {
    if (currentValue) setPendingToggle({ id, currentValue });
    else doToggle(id, currentValue);
  };

  const doToggle = async (id, currentValue) => {
    try {
      await updateBus(id, { is_active: !currentValue });
      fetchBuses();
    } catch (err) {
      alert(`Failed to update bus: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });
  useEffect(() => { fetchBuses(); }, []);

  const handleEditOpen = (bus) => {
    setEditingBus(bus);
    setEditForm({
      bus_number: bus.bus_number || "",
      capacity: bus.capacity ?? "",
      model: bus.model || "",
      tracker_token: bus.tracker_token || "",
    });
  };

  const handleEditChange = (e) => setEditForm({ ...editForm, [e.target.name]: e.target.value });

  const handleDelete = (bus) => setPendingDelete(bus);

  const confirmDelete = async () => {
    try {
      await deleteBus(pendingDelete.id);
      setPendingDelete(null);
      fetchBuses();
    } catch (err) {
      alert(`Failed to delete bus: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.bus_number || !editForm.capacity) { alert("Bus number and capacity are required"); return; }
    setSavingEdit(true);
    try {
      await updateBus(editingBus.id, {
        bus_number: editForm.bus_number,
        capacity: Number(editForm.capacity),
        model: editForm.model,
        tracker_token: editForm.tracker_token,
      });
      setEditingBus(null);
      fetchBuses();
    } catch (err) {
      alert(`Failed to update bus: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.bus_number || !form.capacity) { alert("Bus number and capacity are required"); return; }
    try {
      await createBus(form);
      setForm({ bus_number: "", capacity: "", model: "", tracker_token: "" });
      fetchBuses();
    } catch (err) {
      alert(`Failed to add bus: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const columns = [
    { key: "bus_number", label: "Bus Number" },
    { key: "total_seats", label: "Total Seats", render: (row) => row.total_seats ?? row.capacity },
    { key: "available_seats", label: "Available Seats", render: (row) => row.available_seats ?? row.capacity },
    { key: "model", label: "Model" },
    {
      key: "tracker_token", label: "Tracker Token",
      render: (row) => row.tracker_token || <span style={{ color: colors.textMuted, fontStyle: "italic" }}>Not set</span>,
    },
    {
      key: "is_active", label: "Status",
      render: (row) => <StatusBadge active={row.is_active} onClick={() => handleToggle(row.id, row.is_active)} />,
    },
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

  const totalSeats = buses.reduce((s, b) => s + Number(b.total_seats ?? b.capacity ?? 0), 0);
  const availSeats = buses.reduce((s, b) => s + Number(b.available_seats ?? b.capacity ?? 0), 0);

  return (
    <PageShell role="staff" title="Admin — Buses">
      {pendingToggle && (
        <ConfirmModal
          title="Deactivate Bus?"
          message="Setting this bus to inactive will also automatically deactivate all corresponding assignments linked to it."
          confirmLabel="Yes, Deactivate"
          onConfirm={() => { doToggle(pendingToggle.id, pendingToggle.currentValue); setPendingToggle(null); }}
          onCancel={() => setPendingToggle(null)}
        />
      )}

      {pendingDelete && (
        <ConfirmModal
          title="Delete Bus?"
          message={`Deleting bus ${pendingDelete.bus_number} will also remove related route assignments and seat allocations. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editingBus && (
        <FormModal
          title="Edit Bus"
          sub="Update the bus details. Status is managed separately."
          submitLabel="Save Changes"
          loading={savingEdit}
          onClose={() => setEditingBus(null)}
          onSubmit={handleEditSubmit}
          width="620px"
        >
          <Field label="Bus Number" required flex="1 1 160px">
            <input name="bus_number" placeholder="e.g. KHI-001" value={editForm.bus_number} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Capacity" required flex="0 1 120px">
            <input name="capacity" type="number" placeholder="50" value={editForm.capacity} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Model" flex="1 1 160px">
            <input name="model" placeholder="e.g. Hino 700" value={editForm.model} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="GPS Tracker Token" flex="1 1 180px">
            <input name="tracker_token" placeholder="e.g. YgIw0Z" value={editForm.tracker_token} onChange={handleEditChange} style={inputStyle} />
          </Field>
        </FormModal>
      )}

      <PageTitle sub="Manage fleet and seat availability.">Buses</PageTitle>

      {/* Seat summary */}
      <div className="stat-cards-row">
        {[["Total Seats", totalSeats], ["Available Seats", availSeats]].map(([label, val]) => (
          <div key={label} style={{ background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, padding: "14px 20px", minWidth: "130px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)", flex: "1 1 130px" }}>
            <div style={{ fontSize: "11px", fontWeight: "600", color: colors.textMuted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
            <div style={{ fontSize: "28px", fontWeight: "800", color: colors.textPrimary, fontFamily: fonts.heading, lineHeight: 1.2, marginTop: "4px" }}>{val}</div>
          </div>
        ))}
      </div>

      <FormCard title="Add New Bus" onSubmit={handleSubmit} submitLabel="Add Bus">
        <Field label="Bus Number" required flex="1 1 140px">
          <input name="bus_number" placeholder="e.g. KHI-001" value={form.bus_number} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Capacity" required flex="0 1 110px">
          <input name="capacity" type="number" placeholder="50" value={form.capacity} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Model" flex="1 1 140px">
          <input name="model" placeholder="e.g. Hino 700" value={form.model} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="GPS Tracker Token" flex="1 1 160px">
          <input name="tracker_token" placeholder="e.g. YgIw0Z" value={form.tracker_token} onChange={handleChange} style={inputStyle} />
        </Field>
      </FormCard>

      <SectionBlock title="Active Buses">
        <Table columns={columns} rows={buses.filter(b => b.is_active)} emptyMessage="No active buses." />
      </SectionBlock>

      <SectionBlock title="Inactive Buses">
        <Table columns={columns} rows={buses.filter(b => !b.is_active)} emptyMessage="No inactive buses." />
      </SectionBlock>
    </PageShell>
  );
}

export default BusesPage;