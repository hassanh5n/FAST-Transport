import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, FormModal, Pill, FormCard, Field } from "../../components/ui";
import { inputStyle, selectStyle } from "../../styles/formStyles";
import { colors, btn } from "../../theme";
import { getSemesters, createSemester, updateSemester, deleteSemester } from "../../services/transportService";

const actionBtn = { ...btn.ghost, padding: "7px 12px", fontSize: "12px" };

// ── Toggle switch ─────────────────────────────────────────────────────────────
function Toggle({ name, checked, onChange, label }) {
  const handleClick = () => onChange({ target: { name, type: "checkbox", checked: !checked } });
  return (
    <label style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "5px", cursor: "pointer", userSelect: "none", alignSelf: "flex-end" }}>
      <span
        onClick={handleClick}
        style={{
          width: "44px", height: "24px", borderRadius: "12px",
          background: checked ? colors.accent : colors.borderMid,
          position: "relative", transition: "background 0.2s", cursor: "pointer", flexShrink: 0, display: "block",
        }}
      >
        <span style={{
          position: "absolute", top: "3px", left: checked ? "23px" : "3px",
          width: "18px", height: "18px", borderRadius: "50%",
          background: "#fff", transition: "left 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        }} />
      </span>
      <span style={{ fontSize: "11px", color: colors.textSecondary, fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</span>
    </label>
  );
}

function SemestersPage() {
  const [semesters, setSemesters] = useState([]);
  const [form, setForm] = useState({ year: "", term: "", start_date: "", end_date: "", registration_deadline: "", transport_fee: "50000", faculty_transport_fee: "9000", is_active: false, registration_open: false });
  const [pendingToggle, setPendingToggle] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [editingSemester, setEditingSemester] = useState(null);
  const [editForm, setEditForm] = useState({ year: "", term: "", start_date: "", end_date: "", registration_deadline: "", transport_fee: "", faculty_transport_fee: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchSemesters = () =>
    getSemesters().then((res) => setSemesters(res.data)).catch(() => alert("Failed to fetch semesters."));

  const handleToggle = (id, field, currentValue) => {
    if (field === "is_active" && currentValue) setPendingToggle({ id, field, currentValue });
    else doToggle(id, field, currentValue);
  };

  const doToggle = async (id, field, currentValue) => {
    try {
      await updateSemester(id, { [field]: !currentValue });
      fetchSemesters();
    } catch (err) {
      alert(`Failed to update semester: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  useEffect(() => { fetchSemesters(); }, []);

  const handleDelete = (semester) => setPendingDelete(semester);

  const confirmDelete = async () => {
    try {
      await deleteSemester(pendingDelete.id);
      setPendingDelete(null);
      fetchSemesters();
    } catch (err) {
      alert(`Failed to delete semester: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleEditOpen = (semester) => {
    setEditingSemester(semester);
    setEditForm({
      year: semester.year ?? "",
      term: semester.term || "",
      start_date: semester.start_date || "",
      end_date: semester.end_date || "",
      // <input type="datetime-local"> wants "YYYY-MM-DDTHH:MM" with no zone.
      registration_deadline: semester.registration_deadline
        ? semester.registration_deadline.slice(0, 16)
        : "",
      transport_fee: semester.transport_fee ?? "",
      faculty_transport_fee: semester.faculty_transport_fee ?? "",
    });
  };

  const handleEditChange = (e) => {
    const { name, value } = e.target;
    setEditForm({ ...editForm, [name]: value });
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.year || !editForm.term || !editForm.start_date || !editForm.end_date) {
      alert("All fields are required."); return;
    }
    setSavingEdit(true);
    try {
      await updateSemester(editingSemester.id, {
        year: Number(editForm.year),
        term: editForm.term,
        start_date: editForm.start_date,
        end_date: editForm.end_date,
        registration_deadline: editForm.registration_deadline || null,
        transport_fee: editForm.transport_fee === "" ? undefined : editForm.transport_fee,
        faculty_transport_fee: editForm.faculty_transport_fee === "" ? undefined : editForm.faculty_transport_fee,
        name: `${editForm.term} ${editForm.year}`,
      });
      setEditingSemester(null);
      fetchSemesters();
    } catch (err) {
      alert(`Failed to update semester: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.year || !form.term || !form.start_date || !form.end_date) {
      alert("All fields are required."); return;
    }
    try {
      const payload = Object.fromEntries(
        Object.entries({ ...form, name: `${form.term} ${form.year}` }).filter(([, v]) => v !== "")
      );
      await createSemester(payload);
      setForm({ year: "", term: "", start_date: "", end_date: "", registration_deadline: "", transport_fee: "50000", faculty_transport_fee: "9000", is_active: false, registration_open: false });
      fetchSemesters();
    } catch (err) {
      alert(`Failed to add semester: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const columns = [
    { key: "name", label: "Name" },
    { key: "year", label: "Year" },
    { key: "term", label: "Term" },
    { key: "start_date", label: "Start Date" },
    { key: "end_date", label: "End Date" },
    {
      key: "transport_fee",
      label: "Student Fee",
      render: (row) => (row.transport_fee != null ? `PKR ${row.transport_fee}` : "—"),
    },
    {
      key: "faculty_transport_fee",
      label: "Faculty Fee",
      render: (row) => (row.faculty_transport_fee != null ? `PKR ${row.faculty_transport_fee}` : "—"),
    },
    {
      key: "registration_deadline",
      label: "Reg. Deadline",
      render: (row) =>
        row.registration_deadline
          ? new Date(row.registration_deadline).toLocaleString()
          : "—",
    },
    {
      key: "is_active", label: "Active",
      render: (row) => (
        <Pill
          label={row.is_active ? "Active" : "Inactive"}
          variant={row.is_active ? "success" : "neutral"}
          onClick={() => handleToggle(row.id, "is_active", row.is_active)}
          style={{ cursor: "pointer" }}
        />
      ),
    },
    {
      key: "registration_open", label: "Registration",
      render: (row) => (
        <Pill
          label={row.registration_open ? "Open" : "Closed"}
          variant={row.registration_open ? "info" : "neutral"}
          onClick={() => handleToggle(row.id, "registration_open", row.registration_open)}
          style={{ cursor: "pointer" }}
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
    <PageShell role="staff" title="Admin — Semesters">
      {pendingToggle && (
        <ConfirmModal
          title="Deactivate Semester?"
          message="Setting this semester to inactive will also deactivate all corresponding assignments linked to it."
          confirmLabel="Yes, Deactivate"
          onConfirm={() => { doToggle(pendingToggle.id, pendingToggle.field, pendingToggle.currentValue); setPendingToggle(null); }}
          onCancel={() => setPendingToggle(null)}
        />
      )}

      {pendingDelete && (
        <ConfirmModal
          title="Delete Semester?"
          message={`Deleting semester ${pendingDelete.name} will remove registrations, fee verifications, route assignments, seat allocations, and related data for that term. This cannot be undone.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editingSemester && (
        <FormModal
          title="Edit Semester"
          sub="Update the semester details. Active and registration status are managed separately."
          submitLabel="Save Changes"
          loading={savingEdit}
          onClose={() => setEditingSemester(null)}
          onSubmit={handleEditSubmit}
          width="700px"
        >
          <Field label="Year" required flex="0 1 110px">
            <input name="year" type="number" placeholder="2026" value={editForm.year} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Term" required flex="0 1 150px">
            <select name="term" value={editForm.term} onChange={handleEditChange} style={selectStyle}>
              <option value="">Select Term</option>
              <option value="Spring">Spring</option>
              <option value="Fall">Fall</option>
              <option value="Summer">Summer</option>
            </select>
          </Field>
          <Field label="Start Date" required flex="0 1 150px">
            <input name="start_date" type="date" value={editForm.start_date} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="End Date" required flex="0 1 150px">
            <input name="end_date" type="date" value={editForm.end_date} onChange={handleEditChange} style={inputStyle} />
          </Field>
          <Field label="Student Fee (PKR)" flex="0 1 160px">
            <input
              name="transport_fee"
              type="number"
              min="0"
              value={editForm.transport_fee}
              onChange={handleEditChange}
              style={inputStyle}
            />
          </Field>
          <Field label="Faculty Fee (PKR)" flex="0 1 160px">
            <input
              name="faculty_transport_fee"
              type="number"
              min="0"
              value={editForm.faculty_transport_fee}
              onChange={handleEditChange}
              style={inputStyle}
            />
          </Field>
          <Field label="Registration Deadline" flex="1 1 220px">
            <input
              name="registration_deadline"
              type="datetime-local"
              value={editForm.registration_deadline}
              onChange={handleEditChange}
              style={inputStyle}
            />
          </Field>
        </FormModal>
      )}

      <PageTitle sub="Manage academic semesters and registration windows.">Semesters</PageTitle>

      <FormCard title="Add New Semester" onSubmit={handleSubmit} submitLabel="Add Semester">
        <Field label="Year" required flex="0 1 100px">
          <input name="year" type="number" placeholder="2026" value={form.year} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="Term" required flex="0 1 130px">
          <select name="term" value={form.term} onChange={handleChange} style={selectStyle}>
            <option value="">Select Term</option>
            <option value="Spring">Spring</option>
            <option value="Fall">Fall</option>
            <option value="Summer">Summer</option>
          </select>
        </Field>
        <Field label="Student Fee (PKR)" flex="0 1 150px">
          <input
            name="transport_fee"
            type="number"
            min="0"
            placeholder="50000"
            value={form.transport_fee}
            onChange={handleChange}
            style={inputStyle}
          />
        </Field>
        <Field label="Faculty Fee (PKR)" flex="0 1 150px">
          <input
            name="faculty_transport_fee"
            type="number"
            min="0"
            placeholder="9000"
            value={form.faculty_transport_fee}
            onChange={handleChange}
            style={inputStyle}
          />
        </Field>
        <Field label="Registration Deadline" flex="1 1 210px">
          <input
            name="registration_deadline"
            type="datetime-local"
            value={form.registration_deadline}
            onChange={handleChange}
            style={inputStyle}
          />
        </Field>
        <Field label="Start Date" required flex="0 1 150px">
          <input name="start_date" type="date" value={form.start_date} onChange={handleChange} style={inputStyle} />
        </Field>
        <Field label="End Date" required flex="0 1 150px">
          <input name="end_date" type="date" value={form.end_date} onChange={handleChange} style={inputStyle} />
        </Field>
        <Toggle name="is_active" checked={form.is_active} onChange={handleChange} label="Active" />
        <Toggle name="registration_open" checked={form.registration_open} onChange={handleChange} label="Reg. Open" />
      </FormCard>

      <Table columns={columns} rows={semesters} />
    </PageShell>
  );
}

export default SemestersPage;
