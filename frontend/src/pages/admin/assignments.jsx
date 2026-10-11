import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, StatusBadge, FormCard, Field, SectionBlock } from "../../components/ui";
import { selectStyle } from "../../styles/formStyles";
import { btn } from "../../theme";
import {
  getAssignments, createAssignment, updateAssignment, deleteAssignment,
  getRoutes, getBuses, getDrivers, getSemesters,
} from "../../services/transportService";
import { useContractor, ContractorSwitch } from "../../components/ContractorSwitch";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };

const getOptionsWithCurrent = (options, currentItem) => {
  if (!currentItem) return options;
  return options.some((option) => option.id === currentItem.id)
    ? options
    : [...options, currentItem];
};

function AssignmentsPage() {
  const contractor = useContractor();
  const [allAssignments, setAssignments] = useState([]);
  const assignments = allAssignments.filter((a) => contractor.matches(a.route?.contractor));
  const [routes, setRoutes] = useState([]);
  const [buses, setBuses] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [form, setForm] = useState({ route_id: "", bus_id: "", driver_id: "", semester_id: "" });
  const [pendingDelete, setPendingDelete] = useState(null);
  const [editingAssignment, setEditingAssignment] = useState(null);
  const [editForm, setEditForm] = useState({ route_id: "", bus_id: "", driver_id: "", semester_id: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchAssignments = () =>
    getAssignments().then((res) => setAssignments(res.data)).catch(() => alert("Failed to fetch assignments."));

  const handleToggle = async (id, currentValue) => {
    try {
      await updateAssignment(id, { is_active: !currentValue });
      fetchAssignments();
    } catch (err) {
      alert(`Failed to update assignment: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleEditOpen = (assignment) => {
    setEditingAssignment(assignment);
    setEditForm({
      route_id: assignment.route?.id ?? assignment.route_id ?? "",
      bus_id: assignment.bus?.id ?? assignment.bus_id ?? "",
      driver_id: assignment.driver?.id ?? assignment.driver_id ?? "",
      semester_id: assignment.semester?.id ?? assignment.semester_id ?? "",
    });
  };

  const handleEditChange = (e) => setEditForm({ ...editForm, [e.target.name]: e.target.value });

  const handleDelete = (assignment) => setPendingDelete(assignment);

  const confirmDelete = async () => {
    try {
      await deleteAssignment(pendingDelete.id);
      setPendingDelete(null);
      fetchAssignments();
    } catch (err) {
      alert(`Failed to delete assignment: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.route_id || !editForm.bus_id || !editForm.driver_id || !editForm.semester_id) {
      alert("All fields are required."); return;
    }
    setSavingEdit(true);
    try {
      await updateAssignment(editingAssignment.id, editForm);
      setEditingAssignment(null);
      fetchAssignments();
    } catch (err) {
      alert(`Failed to update assignment: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingEdit(false);
    }
  };

  useEffect(() => {
    fetchAssignments();
    Promise.all([getRoutes(), getBuses(), getDrivers(), getSemesters()])
      .then(([r, b, d, s]) => { setRoutes(r.data); setBuses(b.data); setDrivers(d.data); setSemesters(s.data); })
      .catch(() => alert("Failed to fetch dropdown data."));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.route_id || !form.bus_id || !form.driver_id || !form.semester_id) {
      alert("All fields are required."); return;
    }
    try {
      await createAssignment(form);
      setForm({ route_id: "", bus_id: "", driver_id: "", semester_id: "" });
      fetchAssignments();
    } catch (err) {
      alert(`Failed to add assignment: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const columns = [
    { key: "route",    label: "Route",    render: (row) => row.route?.name },
    { key: "contractor", label: "Contractor", render: (row) => contractor.nameOf(row.route?.contractor) || "—" },
    { key: "bus",      label: "Bus",      render: (row) => row.bus?.bus_number },
    { key: "driver",   label: "Driver",   render: (row) => row.driver?.name },
    { key: "semester", label: "Semester", render: (row) => row.semester?.name },
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

  // Once a route is picked, only that contractor's buses and drivers (or ones with no contractor) fit it.
  const sameOwner = (routeId) => {
    const owner = routes.find((r) => String(r.id) === String(routeId))?.contractor;
    return (item) => owner == null || item.contractor == null || item.contractor === owner;
  };
  const activeRoutes     = routes.filter(r => r.is_active && contractor.matches(r.contractor));
  const activeBuses      = buses.filter(b => b.is_active && contractor.matches(b.contractor));
  const availDrivers     = drivers.filter(d => d.is_available && contractor.matches(d.contractor));
  const activeSemesters  = semesters.filter(s => s.is_active);
  const formBuses = activeBuses.filter(sameOwner(form.route_id));
  const formDrivers = availDrivers.filter(sameOwner(form.route_id));
  const editRoutes = getOptionsWithCurrent(activeRoutes, editingAssignment?.route);
  const editBuses = getOptionsWithCurrent(activeBuses.filter(sameOwner(editForm.route_id)), editingAssignment?.bus);
  const editDrivers = getOptionsWithCurrent(availDrivers.filter(sameOwner(editForm.route_id)), editingAssignment?.driver);
  const editSemesters = getOptionsWithCurrent(activeSemesters, editingAssignment?.semester);

  return (
    <PageShell role="staff" title="Admin — Assignments">
      <PageTitle sub="Assign buses and drivers to routes for each semester.">Route Assignments</PageTitle>
      <ContractorSwitch value={contractor} />

      {pendingDelete && (
        <ConfirmModal
          title="Delete Assignment?"
          message={`Deleting this assignment will remove any allocated seats and waitlist effects tied to it. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editingAssignment && (
        <FormModal
          title="Edit Assignment"
          sub="Update the route, bus, driver, or semester for this assignment."
          submitLabel="Save Changes"
          loading={savingEdit}
          onClose={() => setEditingAssignment(null)}
          onSubmit={handleEditSubmit}
          width="760px"
        >
          <Field label="Route" required flex="1 1 150px">
            <select name="route_id" value={editForm.route_id} onChange={handleEditChange} style={selectStyle}>
              <option value="">Select Route</option>
              {editRoutes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
          <Field label="Bus" required flex="1 1 150px">
            <select name="bus_id" value={editForm.bus_id} onChange={handleEditChange} style={selectStyle}>
              <option value="">Select Bus</option>
              {editBuses.map(b => <option key={b.id} value={b.id}>{b.bus_number}</option>)}
            </select>
          </Field>
          <Field label="Driver" required flex="1 1 150px">
            <select name="driver_id" value={editForm.driver_id} onChange={handleEditChange} style={selectStyle}>
              <option value="">Select Driver</option>
              {editDrivers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="Semester" required flex="1 1 150px">
            <select name="semester_id" value={editForm.semester_id} onChange={handleEditChange} style={selectStyle}>
              <option value="">Select Semester</option>
              {editSemesters.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        </FormModal>
      )}

      <FormCard title="Create Assignment" onSubmit={handleSubmit} submitLabel="Add Assignment">
        <Field label="Route" required flex="1 1 140px">
          <select name="route_id" value={form.route_id} onChange={handleChange} style={selectStyle}>
            <option value="">Select Route</option>
            {activeRoutes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        <Field label="Bus" required flex="1 1 140px">
          <select name="bus_id" value={form.bus_id} onChange={handleChange} style={selectStyle}>
            <option value="">Select Bus</option>
            {formBuses.map(b => <option key={b.id} value={b.id}>{b.bus_number}</option>)}
          </select>
        </Field>
        <Field label="Driver" required flex="1 1 140px">
          <select name="driver_id" value={form.driver_id} onChange={handleChange} style={selectStyle}>
            <option value="">Select Driver</option>
            {formDrivers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <Field label="Semester" required flex="1 1 140px">
          <select name="semester_id" value={form.semester_id} onChange={handleChange} style={selectStyle}>
            <option value="">Select Semester</option>
            {activeSemesters.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
      </FormCard>

      <SectionBlock title="Active Assignments">
        <Table columns={columns} rows={assignments.filter(a => a.is_active)} emptyMessage="No active assignments." />
      </SectionBlock>

      <SectionBlock title="Inactive Assignments">
        <Table columns={columns} rows={assignments.filter(a => !a.is_active)} emptyMessage="No inactive assignments." />
      </SectionBlock>
    </PageShell>
  );
}

export default AssignmentsPage;
