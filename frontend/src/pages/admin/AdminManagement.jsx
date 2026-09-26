// frontend/src/pages/admin/AdminManagement.jsx
// Super admin only: create admins, give them a role (+ per-admin overrides),
// and edit the roles themselves.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { ConfirmModal, Field, FormModal, Pill, Spinner } from "../../components/ui";
import { btn, colors, fonts, input, radius } from "../../theme";
import {
  createAdminRole, createAdminUser, deleteAdminRole, getAdminModules,
  getAdminRoles, getAdminUsers, updateAdminRole, updateAdminUser,
} from "../../services/transportService";

const LEVEL_LABEL = { none: "No access", view: "View", manage: "Manage" };

function errorText(err, fallback) {
  const d = err?.response?.data;
  if (!d) return fallback;
  if (typeof d === "string") return fallback;
  if (d.detail) return d.detail;
  if (Array.isArray(d)) return d.join(" ");
  return Object.entries(d).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : v}`).join("\n");
}

function fullPerms(modules, perms = {}) {
  return Object.fromEntries(modules.map((m) => [m.key, perms[m.key] || "none"]));
}

// ── Permission grid ──────────────────────────────────────────────────────────
// value: {module: level}; base: role permissions (to mark overrides) or null
function PermissionGrid({ modules, value, onChange, base = null, disabled = false }) {
  return (
    <div style={styles.grid}>
      {modules.map((m) => {
        const current = value[m.key] || "none";
        const overridden = base && (base[m.key] || "none") !== current;
        const levels = m.key === "export" ? ["none", "view"] : ["none", "view", "manage"];
        return (
          <div key={m.key} style={styles.gridRow}>
            <div style={{ flex: "1 1 180px", minWidth: 0 }}>
              <div style={styles.moduleName}>
                {m.label}
                {overridden && <span style={styles.customTag}>custom</span>}
              </div>
              <div style={styles.moduleDesc}>{m.description}</div>
            </div>
            <div style={styles.segment} role="radiogroup" aria-label={m.label}>
              {levels.map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange({ ...value, [m.key]: lvl })}
                  style={{
                    ...styles.segBtn,
                    ...(current === lvl ? styles.segBtnOn[lvl] : {}),
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                  aria-pressed={current === lvl}
                >
                  {LEVEL_LABEL[lvl]}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PermSummary({ modules, perms }) {
  const granted = modules.filter((m) => perms[m.key] && perms[m.key] !== "none");
  if (granted.length === 0) return <span style={{ color: colors.textMuted }}>No access</span>;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", maxWidth: "380px" }}>
      {granted.map((m) => (
        <span key={m.key} style={perms[m.key] === "manage" ? styles.chipManage : styles.chipView}>
          {m.label}{perms[m.key] === "view" ? " (view)" : ""}
        </span>
      ))}
    </div>
  );
}

// ── Admin form modal ─────────────────────────────────────────────────────────
function AdminFormModal({ admin, roles, modules, onClose, onSaved }) {
  const isEdit = Boolean(admin);
  const selfUsername = localStorage.getItem("username");
  const [form, setForm] = useState({
    username: admin?.username || "",
    first_name: admin?.first_name || "",
    last_name: admin?.last_name || "",
    email: admin?.email || "",
    password: "",
    is_super_admin: admin?.is_super_admin || false,
    role: admin?.role ?? "",
  });
  const roleOf = (id) => roles.find((r) => String(r.id) === String(id));
  const [perms, setPerms] = useState(() =>
    fullPerms(modules, { ...(roleOf(admin?.role)?.permissions || {}), ...(admin?.custom_permissions || {}) })
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const basePerms = useMemo(() => fullPerms(modules, roleOf(form.role)?.permissions || {}), [form.role, roles]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const changeRole = (e) => {
    const roleId = e.target.value;
    setForm((f) => ({ ...f, role: roleId }));
    setPerms(fullPerms(modules, roleOf(roleId)?.permissions || {})); // start from the role's defaults
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    // Store only what differs from the role as custom overrides.
    const custom = Object.fromEntries(Object.entries(perms).filter(([k, v]) => (basePerms[k] || "none") !== v));
    const payload = {
      username: form.username.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
      is_super_admin: form.is_super_admin,
      role: form.role === "" ? null : Number(form.role),
      custom_permissions: custom,
    };
    if (form.password) payload.password = form.password;
    setSaving(true);
    try {
      if (isEdit) await updateAdminUser(admin.id, payload);
      else await createAdminUser(payload);
      onSaved();
    } catch (err) {
      setError(errorText(err, "Could not save admin."));
    } finally {
      setSaving(false);
    }
  };

  const editingSelf = isEdit && admin.username === selfUsername;

  return (
    <FormModal
      title={isEdit ? `Edit ${admin.username}` : "Add Admin"}
      sub={isEdit ? "Change details, role or individual permissions." : "Create an admin account and choose what they can access."}
      onSubmit={submit}
      onClose={onClose}
      loading={saving}
      submitLabel={isEdit ? "Save changes" : "Create admin"}
      width="760px"
    >
      <Field label="Username" required><input style={input} value={form.username} onChange={set("username")} required disabled={isEdit} /></Field>
      <Field label="Email"><input style={input} type="email" value={form.email} onChange={set("email")} /></Field>
      <Field label="First name"><input style={input} value={form.first_name} onChange={set("first_name")} /></Field>
      <Field label="Last name"><input style={input} value={form.last_name} onChange={set("last_name")} /></Field>
      <Field label={isEdit ? "New password (leave blank to keep)" : "Password"} required={!isEdit} flex="1 1 100%">
        <input style={input} type="password" value={form.password} onChange={set("password")} required={!isEdit} autoComplete="new-password" />
      </Field>

      <label style={styles.superToggle}>
        <input type="checkbox" checked={form.is_super_admin} onChange={set("is_super_admin")} disabled={editingSelf} />
        <span>
          <strong>Super admin</strong>
          <span style={{ display: "block", fontSize: "12px", color: colors.textSecondary }}>
            Full access to everything, including managing admins and viewing activity logs.
            {editingSelf && " (You can't remove this from yourself.)"}
          </span>
        </span>
      </label>

      {!form.is_super_admin && (
        <>
          <Field label="Role" flex="1 1 100%">
            <select style={input} value={form.role ?? ""} onChange={changeRole}>
              <option value="">No preset — custom permissions only</option>
              {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
          <div style={{ flex: "1 1 100%", textAlign: "left" }}>
            <div style={styles.gridHint}>
              Permissions start from the role. Change any module to give this admin a custom exception (marked <span style={styles.customTag}>custom</span>).
            </div>
            <PermissionGrid modules={modules} value={perms} onChange={setPerms} base={form.role ? basePerms : null} />
          </div>
        </>
      )}

      {error && <div style={styles.formError}>{error}</div>}
    </FormModal>
  );
}

// ── Role form modal ──────────────────────────────────────────────────────────
function RoleFormModal({ role, modules, onClose, onSaved }) {
  const [name, setName] = useState(role?.name || "");
  const [description, setDescription] = useState(role?.description || "");
  const [perms, setPerms] = useState(fullPerms(modules, role?.permissions || {}));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    const permissions = Object.fromEntries(Object.entries(perms).filter(([, v]) => v !== "none"));
    try {
      if (role) await updateAdminRole(role.id, { name, description, permissions });
      else await createAdminRole({ name, description, permissions });
      onSaved();
    } catch (err) {
      setError(errorText(err, "Could not save role."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormModal
      title={role ? `Edit role: ${role.name}` : "New Role"}
      sub="Admins with this role get these permissions (unless given a custom exception)."
      onSubmit={submit}
      onClose={onClose}
      loading={saving}
      submitLabel={role ? "Save role" : "Create role"}
      width="760px"
    >
      <Field label="Role name" required><input style={input} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
      <Field label="Description" flex="2 1 260px"><input style={input} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <div style={{ flex: "1 1 100%", textAlign: "left" }}>
        <PermissionGrid modules={modules} value={perms} onChange={setPerms} />
      </div>
      {error && <div style={styles.formError}>{error}</div>}
    </FormModal>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
function AdminManagement() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("admins");
  const [modules, setModules] = useState(null);
  const [admins, setAdmins] = useState([]);
  const [roles, setRoles] = useState([]);
  const [adminModal, setAdminModal] = useState(null); // {admin} | {admin:null}
  const [roleModal, setRoleModal] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = () =>
    Promise.all([getAdminModules(), getAdminUsers(), getAdminRoles()])
      .then(([m, a, r]) => { setModules(m.data.modules); setAdmins(a.data); setRoles(r.data); })
      .catch(() => setLoadError("Failed to load admins. Only the super admin can open this page."));

  useEffect(() => { load(); }, []);

  const toggleActive = async (admin) => {
    try {
      await updateAdminUser(admin.id, { is_active: !admin.is_active });
      load();
    } catch (err) {
      alert(errorText(err, "Could not update admin."));
    } finally {
      setConfirm(null);
    }
  };

  const removeRole = async (role) => {
    try {
      await deleteAdminRole(role.id);
      load();
    } catch (err) {
      alert(errorText(err, "Could not delete role."));
    } finally {
      setConfirm(null);
    }
  };

  if (loadError) return (
    <PageShell role="staff" title="Admins & Roles">
      <div style={{ padding: "48px 0", textAlign: "center", color: colors.dangerText }}>{loadError}</div>
    </PageShell>
  );
  if (!modules) return <PageShell role="staff" title="Admins & Roles"><Spinner /></PageShell>;

  const adminColumns = [
    { key: "name", label: "Admin" },
    { key: "email", label: "Email" },
    { key: "access", label: "Role / Access" },
    { key: "status", label: "Status" },
    { key: "last_login", label: "Last login" },
    { key: "created_by", label: "Added by" },
    { key: "actions", label: "Actions" },
  ];
  const adminRows = admins.map((a) => ({
    id: a.id,
    name: (
      <div>
        <div style={{ fontWeight: 600, color: colors.textPrimary }}>{`${a.first_name} ${a.last_name}`.trim() || a.username}</div>
        <div style={{ fontSize: "12px", color: colors.textMuted }}>@{a.username}</div>
      </div>
    ),
    email: a.email || "-",
    access: a.is_super_admin ? (
      <Pill label="Super Admin" variant="info" />
    ) : (
      <div style={{ display: "grid", gap: "6px" }}>
        <div style={{ fontSize: "13px", fontWeight: 600 }}>
          {a.role_name || "Custom"}
          {a.role_name && Object.keys(a.custom_permissions || {}).length > 0 && (
            <span style={styles.customTag}>+ custom</span>
          )}
        </div>
        <PermSummary modules={modules} perms={a.effective_permissions} />
      </div>
    ),
    status: <Pill label={a.is_active ? "Active" : "Deactivated"} variant={a.is_active ? "success" : "neutral"} />,
    last_login: a.last_login ? new Date(a.last_login).toLocaleString() : "Never",
    created_by: a.created_by || "-",
    actions: (
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        <button style={styles.smallBtn} onClick={() => setAdminModal({ admin: a })}>Edit</button>
        <button style={styles.smallBtn} onClick={() => navigate(`/admin/activity-logs?actor=${a.id}`)}>Logs</button>
        {a.username !== localStorage.getItem("username") && (
          <button
            style={a.is_active ? styles.smallDanger : styles.smallBtn}
            onClick={() => setConfirm({
              title: a.is_active ? "Deactivate admin?" : "Reactivate admin?",
              message: a.is_active
                ? `${a.username} will be signed out and can no longer log in. Their activity log is kept.`
                : `${a.username} will be able to log in again.`,
              label: a.is_active ? "Deactivate" : "Reactivate",
              danger: a.is_active,
              run: () => toggleActive(a),
            })}
          >
            {a.is_active ? "Deactivate" : "Reactivate"}
          </button>
        )}
      </div>
    ),
  }));

  const roleColumns = [
    { key: "name", label: "Role" },
    { key: "perms", label: "Permissions" },
    { key: "count", label: "Admins" },
    { key: "actions", label: "Actions" },
  ];
  const roleRows = roles.map((r) => ({
    id: r.id,
    name: (
      <div>
        <div style={{ fontWeight: 600, color: colors.textPrimary }}>
          {r.name} {r.is_system && <span style={styles.presetTag}>preset</span>}
        </div>
        <div style={{ fontSize: "12px", color: colors.textMuted }}>{r.description || "-"}</div>
      </div>
    ),
    perms: <PermSummary modules={modules} perms={r.permissions} />,
    count: r.admin_count,
    actions: (
      <div style={{ display: "flex", gap: "6px" }}>
        <button style={styles.smallBtn} onClick={() => setRoleModal({ role: r })}>Edit</button>
        {!r.is_system && (
          <button
            style={styles.smallDanger}
            onClick={() => setConfirm({
              title: "Delete role?", message: `Delete “${r.name}”? This cannot be undone.`,
              label: "Delete", danger: true, run: () => removeRole(r),
            })}
          >
            Delete
          </button>
        )}
      </div>
    ),
  }));

  return (
    <PageShell role="staff" title="Admins & Roles">
      <div style={styles.headerRow}>
        <PageTitle sub="Add admins, decide which modules each one can view or manage, and edit the roles.">
          Admins &amp; Roles
        </PageTitle>
        <button
          style={btn.primary}
          onClick={() => (tab === "admins" ? setAdminModal({ admin: null }) : setRoleModal({ role: null }))}
        >
          {tab === "admins" ? "+ Add Admin" : "+ New Role"}
        </button>
      </div>

      <div style={styles.tabs} role="tablist">
        {[["admins", `Admins (${admins.length})`], ["roles", `Roles (${roles.length})`]].map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)} style={tab === key ? styles.tabOn : styles.tab}>
            {label}
          </button>
        ))}
      </div>

      {tab === "admins"
        ? <Table columns={adminColumns} rows={adminRows} emptyMessage="No admins yet." />
        : <Table columns={roleColumns} rows={roleRows} emptyMessage="No roles yet." />}

      {adminModal && (
        <AdminFormModal
          admin={adminModal.admin}
          roles={roles}
          modules={modules}
          onClose={() => setAdminModal(null)}
          onSaved={() => { setAdminModal(null); load(); }}
        />
      )}
      {roleModal && (
        <RoleFormModal
          role={roleModal.role}
          modules={modules}
          onClose={() => setRoleModal(null)}
          onSaved={() => { setRoleModal(null); load(); }}
        />
      )}
      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.label}
          danger={confirm.danger}
          onConfirm={confirm.run}
          onCancel={() => setConfirm(null)}
        />
      )}
    </PageShell>
  );
}

const segOn = (bg, text, border) => ({ background: bg, color: text, borderColor: border, fontWeight: 700 });

const styles = {
  headerRow: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", flexWrap: "wrap" },
  tabs: { display: "flex", gap: "6px", margin: "4px 0 16px", borderBottom: `1px solid ${colors.borderLight}` },
  tab: {
    background: "transparent", border: "none", borderBottom: "2px solid transparent",
    padding: "10px 14px", fontSize: "13.5px", fontWeight: 600, color: colors.textSecondary,
    cursor: "pointer", fontFamily: fonts.body, marginBottom: "-1px",
  },
  tabOn: {
    background: "transparent", border: "none", borderBottom: `2px solid ${colors.accent}`,
    padding: "10px 14px", fontSize: "13.5px", fontWeight: 700, color: colors.accent,
    cursor: "pointer", fontFamily: fonts.body, marginBottom: "-1px",
  },
  grid: { border: `1px solid ${colors.borderLight}`, borderRadius: radius.md, overflow: "hidden" },
  gridRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap",
    padding: "10px 14px", borderBottom: `1px solid ${colors.tableRowBorder}`,
  },
  gridHint: { fontSize: "12px", color: colors.textSecondary, margin: "0 0 8px" },
  moduleName: { fontSize: "13px", fontWeight: 600, color: colors.textPrimary, display: "flex", alignItems: "center", gap: "6px" },
  moduleDesc: { fontSize: "11.5px", color: colors.textMuted, marginTop: "2px" },
  segment: { display: "inline-flex", border: `1px solid ${colors.borderMid}`, borderRadius: radius.md, overflow: "hidden", flexShrink: 0 },
  segBtn: {
    background: "#fff", border: "none", borderRight: `1px solid ${colors.borderLight}`,
    padding: "6px 12px", fontSize: "12px", color: colors.textSecondary, fontFamily: fonts.body,
  },
  segBtnOn: {
    none: segOn(colors.neutralBg, colors.neutralText, colors.borderMid),
    view: segOn(colors.infoBg, colors.infoText, colors.accent),
    manage: segOn(colors.successBg, colors.successText, colors.successDot),
  },
  customTag: {
    fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em",
    color: colors.warningText, background: colors.warningBg, borderRadius: "999px", padding: "1px 7px", marginLeft: "6px",
  },
  presetTag: {
    fontSize: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em",
    color: colors.infoText, background: colors.infoBg, borderRadius: "999px", padding: "1px 7px", marginLeft: "4px",
  },
  chipManage: { fontSize: "11px", padding: "2px 8px", borderRadius: "999px", background: colors.successBg, color: colors.successText, fontWeight: 600 },
  chipView: { fontSize: "11px", padding: "2px 8px", borderRadius: "999px", background: colors.infoBg, color: colors.infoText, fontWeight: 600 },
  superToggle: {
    flex: "1 1 100%", display: "flex", gap: "10px", alignItems: "flex-start", textAlign: "left",
    padding: "12px 14px", border: `1px solid ${colors.borderLight}`, borderRadius: radius.md,
    background: colors.pageBg, fontSize: "13px", color: colors.textPrimary, cursor: "pointer",
  },
  smallBtn: { ...btn.ghost, padding: "5px 10px", fontSize: "12px" },
  smallDanger: { ...btn.danger, padding: "5px 10px", fontSize: "12px" },
  formError: {
    flex: "1 1 100%", whiteSpace: "pre-line", textAlign: "left", fontSize: "13px",
    color: colors.dangerText, background: colors.dangerBg, borderRadius: radius.md, padding: "10px 12px",
  },
};

export default AdminManagement;
