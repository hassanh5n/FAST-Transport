import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, StatusBadge, Pill, FormCard, Field, SectionBlock } from "../../components/ui";
import { inputStyle } from "../../styles/formStyles";
import { btn, colors } from "../../theme";
import { getDrivers, createDriver, updateDriver, deleteDriver } from "../../services/transportService";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };
const EMPTY_FORM = { name: "", cnic: "", license_no: "", phone: "", address: "", username: "", password: "" };

// DRF field errors arrive as { field: ["message"] }; show the first readable one.
const apiError = (err) => {
  const data = err.response?.data;
  if (!data || typeof data !== "object") return err.message;
  const first = Object.values(data)[0];
  return Array.isArray(first) ? first[0] : String(first);
};

function DriversPage() {
  const [drivers, setDrivers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [pendingToggle, setPendingToggle] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [editingDriver, setEditingDriver] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchDrivers = () =>
    getDrivers().then((res) => setDrivers(res.data)).catch(() => alert("Failed to fetch drivers."));

  const handleToggle = (id, currentValue) => {
    if (currentValue) setPendingToggle({ id, currentValue });
    else doToggle(id, currentValue);
  };

  const doToggle = async (id, currentValue) => {
    try {
      await updateDriver(id, { is_available: !currentValue });
      fetchDrivers();
    } catch (err) {
      alert(`Failed to update driver: ${apiError(err)}`);
    }
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });
  useEffect(() => { fetchDrivers(); }, []);

  const handleEditOpen = (driver) => {
    setEditingDriver(driver);
    setEditForm({
      name: driver.name || "",
      cnic: driver.cnic || "",
      license_no: driver.license_no || "",
      phone: driver.phone || "",
      address: driver.address || "",
      username: driver.login_username || "",
      password: "",
    });
  };

  const handleEditChange = (e) => setEditForm({ ...editForm, [e.target.name]: e.target.value });
  const handleDelete = (driver) => setPendingDelete(driver);

  const confirmDelete = async () => {
    try {
      await deleteDriver(pendingDelete.id);
      setPendingDelete(null);
      fetchDrivers();
    } catch (err) {
      alert(`Failed to delete driver: ${apiError(err)}`);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.name || !editForm.cnic) { alert("Name and CNIC are required"); return; }
    setSavingEdit(true);
    try {
      await updateDriver(editingDriver.id, editForm);
      setEditingDriver(null);
      fetchDrivers();
    } catch (err) {
      alert(`Failed to update driver: ${apiError(err)}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.cnic) { alert("Name and CNIC are required"); return; }
    if (Boolean(form.username) !== Boolean(form.password)) {
      alert("Enter both a username and a password to give this driver a login, or leave both empty.");
      return;
    }
    try {
      await createDriver(form);
      setForm(EMPTY_FORM);
      fetchDrivers();
    } catch (err) {
      alert(`Failed to add driver: ${apiError(err)}`);
    }
  };

  const columns = [
    { key: "name", label: "Name" },
    { key: "cnic", label: "CNIC" },
    { key: "license_no", label: "License No" },
    { key: "phone", label: "Phone" },
    { key: "address", label: "Address" },
    {
      key: "login_username", label: "Login",
      render: (row) => row.login_username
        ? <span style={{ fontWeight: 600, color: colors.textPrimary }}>{row.login_username}</span>
        : <Pill label="No login" variant="neutral" />,
    },
    {
      key: "is_available", label: "Status",
      render: (row) => (
        <StatusBadge
          active={row.is_available}
          trueLabel="Available"
          falseLabel="Unavailable"
          onClick={() => handleToggle(row.id, row.is_available)}
        />
      ),
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

  return (
    <PageShell role="staff" title="Admin — Drivers">
      {pendingToggle && (
        <ConfirmModal
          title="Mark Driver Unavailable?"
          message="Setting this driver to unavailable will also automatically deactivate all corresponding assignments linked to this driver."
          confirmLabel="Yes, Mark Unavailable"
          onConfirm={() => { doToggle(pendingToggle.id, pendingToggle.currentValue); setPendingToggle(null); }}
          onCancel={() => setPendingToggle(null)}
        />
      )}

      {pendingDelete && (
        <ConfirmModal
          title="Delete Driver?"
          message={`Deleting driver ${pendingDelete.name} will remove any route assignments that reference this driver${pendingDelete.login_username ? " and their login" : ""}. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editingDriver && (
        <FormModal
          title="Edit Driver"
          sub={editingDriver.login_username
            ? "Update the driver details. Leave the password empty to keep the current one."
            : "Update the driver details. Add a username and password to let this driver sign in."}
          submitLabel="Save Changes"
          loading={savingEdit}
          onClose={() => setEditingDriver(null)}
          onSubmit={handleEditSubmit}
          width="700px"
        >
          <Field label="Full Name" required flex="1 1 180px">
            <input name="name" placeholder="e.g. Ahmed Khan" value={editForm.name} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="CNIC" required flex="1 1 160px">
            <input name="cnic" placeholder="42101-1234567-1" value={editForm.cnic} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="License No" flex="1 1 140px">
            <input name="license_no" placeholder="License number" value={editForm.license_no} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Phone" flex="1 1 140px">
            <input name="phone" placeholder="+92 300 0000000" value={editForm.phone} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Address" flex="2 1 240px">
            <input name="address" placeholder="Home address" value={editForm.address} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Login Username" flex="1 1 180px">
            <input name="username" placeholder="e.g. ahmed.khan" autoComplete="off" value={editForm.username} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label={editingDriver.login_username ? "New Password" : "Password"} flex="1 1 180px">
            <input name="password" type="password" placeholder={editingDriver.login_username ? "Leave empty to keep" : "At least 8 characters"} autoComplete="new-password" value={editForm.password} onChange={handleEditChange} style={inputStyle} />
          </Field>
        </FormModal>
      )}

      <PageTitle sub="Manage bus drivers, their availability and their sign-in accounts.">Drivers</PageTitle>

      <FormCard title="Add New Driver" sub="Username and password are optional — fill both to let the driver sign in and see their route." onSubmit={handleSubmit} submitLabel="Add Driver">
        <Field label="Full Name" required flex="1 1 160px">
          <input name="name" placeholder="e.g. Ahmed Khan" value={form.name} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="CNIC" required flex="1 1 140px">
          <input name="cnic" placeholder="42101-1234567-1" value={form.cnic} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="License No" flex="1 1 130px">
          <input name="license_no" placeholder="License number" value={form.license_no} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Phone" flex="1 1 130px">
          <input name="phone" placeholder="+92 300 0000000" value={form.phone} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Address" flex="2 1 240px">
          <input name="address" placeholder="Home address" value={form.address} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Login Username" flex="1 1 160px">
          <input name="username" placeholder="e.g. ahmed.khan" autoComplete="off" value={form.username} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Password" flex="1 1 160px">
          <input name="password" type="password" placeholder="At least 8 characters" autoComplete="new-password" value={form.password} onChange={handleChange} style={inputStyle} />
        </Field>
      </FormCard>

      <SectionBlock title="Available Drivers">
        <Table columns={columns} rows={drivers.filter(d => d.is_available)} emptyMessage="No available drivers." />
      </SectionBlock>

      <SectionBlock title="Unavailable Drivers">
        <Table columns={columns} rows={drivers.filter(d => !d.is_available)} emptyMessage="No unavailable drivers." />
      </SectionBlock>
    </PageShell>
  );
}

export default DriversPage;