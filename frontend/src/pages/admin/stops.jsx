import { useEffect, useMemo, useRef, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Banner, ConfirmModal, FormModal, Field, StatusBadge } from "../../components/ui";
import { inputStyle } from "../../styles/formStyles";
import { btn, colors } from "../../theme";
import { getStops, getRouteStops, createStop, updateStop, deleteStop, resolveMapLocation } from "../../services/transportService";
import StopLocationPicker from "../../components/maps/StopLocationPicker";
import StopsMap from "../../components/maps/StopsMap";
import StopImport from "../../components/StopImport";
import Icon from "../../components/Icon";

const EMPTY_FORM = { name: "", latitude: "", longitude: "", address: "" };
const NO_ADDRESS = "N/A"; // the backend's placeholder; it rejects a blank address
const DUPLICATE_RADIUS_M = 25; // same threshold the bulk import uses
const VIEWS = [["split", "Split", "columns"], ["list", "List", "list"], ["map", "Map", "map"]];
const VIEW_KEY = "admin.stops.view";

const savedView = () => {
  try {
    const view = localStorage.getItem(VIEW_KEY);
    return VIEWS.some(([key]) => key === view) ? view : "split";
  } catch {
    return "split";
  }
};

const metresBetween = (a, b) => {
  const toRad = Math.PI / 180;
  const x = (b.longitude - a.longitude) * toRad * Math.cos(((a.latitude + b.latitude) / 2) * toRad);
  const y = (b.latitude - a.latitude) * toRad;
  return Math.hypot(x, y) * 6371000;
};

const errorText = (err) => {
  const data = err.response?.data;
  return data && typeof data === "object" ? Object.values(data).flat().join(" ") : err.message;
};

const clampCoordinate = (name, value) => {
  if (value === "" || value === null || value === undefined) return "";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  const limit = name === "latitude" ? 90 : 180;
  return String(Math.max(-limit, Math.min(limit, numeric)));
};

const withIcon = { display: "inline-flex", alignItems: "center", gap: 6 };
const smallBtn = { ...withIcon, padding: "7px 12px", fontSize: "12px" };
const linkBtn = { border: 0, background: "transparent", padding: 0, color: colors.accent, cursor: "pointer", fontSize: 12, fontWeight: 600 };
const mutedText = { fontSize: 12, color: colors.textSecondary };

function StopsPage() {
  const [stops, setStops] = useState([]);
  const [routeStops, setRouteStops] = useState([]);
  const [view, setView] = useState(savedView);
  const [searchTerm, setSearchTerm] = useState("");
  const [notice, setNotice] = useState(null); // { variant, text }
  const [confirm, setConfirm] = useState(null); // { title, message, confirmLabel, danger, onConfirm }
  const [editor, setEditor] = useState(null); // { stop: null when adding, initial: form values when opened }
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [hoveredId, setHoveredId] = useState(null);
  const lookupSeq = useRef(0);

  const fetchData = () =>
    Promise.all([getStops(), getRouteStops().catch(() => ({ data: [] }))])
      .then(([stopsRes, routeStopsRes]) => { setStops(stopsRes.data); setRouteStops(routeStopsRes.data); })
      .catch(() => setNotice({ variant: "danger", text: "Failed to load stops." }));

  useEffect(() => { fetchData(); }, []);

  const chooseView = (next) => {
    setView(next);
    try { localStorage.setItem(VIEW_KEY, next); } catch { /* preference just won't persist */ }
  };

  const routesByStop = useMemo(() => {
    const map = new Map();
    routeStops.forEach((item) => map.set(item.stop, [...(map.get(item.stop) || []), item.route_name]));
    return map;
  }, [routeStops]);
  const routesOf = (stop) => routesByStop.get(stop.id) || [];

  // ── Add / edit form ────────────────────────────────────────────────────────
  const isDirty = editor !== null && JSON.stringify(form) !== JSON.stringify(editor.initial);
  const okToDiscard = () => !isDirty || window.confirm("Discard your unsaved changes to this stop?");

  // Opens the form for `stop`, or for a new stop when `stop` is null. Returns false if the user kept their edits.
  const openEditor = (stop, preset = {}) => {
    if (!okToDiscard()) return false;
    lookupSeq.current += 1;
    const initial = stop
      ? { name: stop.name || "", latitude: stop.latitude ?? "", longitude: stop.longitude ?? "", address: stop.address === NO_ADDRESS ? "" : stop.address || "" }
      : { ...EMPTY_FORM, ...preset };
    setEditor({ stop, initial });
    setForm(initial);
    setFormError("");
    return true;
  };

  const closeEditor = () => {
    if (!okToDiscard()) return;
    lookupSeq.current += 1;
    setEditor(null);
  };

  // Map click: start a new stop at that point and look its address up in the background.
  const addAt = (location) => {
    if (!openEditor(null, location)) return;
    const seq = lookupSeq.current;
    resolveMapLocation({ action: "reverse", latitude: Number(location.latitude), longitude: Number(location.longitude) })
      .then((res) => {
        const address = res.data.results?.[0]?.label;
        if (!address || seq !== lookupSeq.current) return;
        setForm((current) => (current.address ? current : { ...current, address }));
        setEditor((current) => current && { ...current, initial: { ...current.initial, address } });
      })
      .catch(() => {});
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    const isCoordinate = name === "latitude" || name === "longitude";
    setForm((current) => ({ ...current, [name]: isCoordinate ? clampCoordinate(name, value) : value }));
  };
  const setLocation = (location) => setForm((current) => ({ ...current, ...location }));

  const hasLocation = form.latitude !== "" && form.longitude !== "" && !(Number(form.latitude) === 0 && Number(form.longitude) === 0);
  const formName = form.name.trim().toLowerCase();
  const duplicate = editor && stops.find((stop) => stop.id !== editor.stop?.id && (
    (formName && stop.name?.trim().toLowerCase() === formName) ||
    (hasLocation && metresBetween(
      { latitude: Number(form.latitude), longitude: Number(form.longitude) },
      { latitude: Number(stop.latitude), longitude: Number(stop.longitude) },
    ) <= DUPLICATE_RADIUS_M)
  ));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const name = form.name.trim();
    if (!name) { setFormError("Stop name is required."); return; }
    if (!hasLocation) { setFormError("Choose the stop's location on the map."); return; }
    const payload = { ...form, name, latitude: Number(form.latitude), longitude: Number(form.longitude), address: form.address.trim() || NO_ADDRESS };
    setSaving(true);
    setFormError("");
    try {
      if (editor.stop) await updateStop(editor.stop.id, payload);
      else await createStop(payload);
      setNotice({ variant: "success", text: `Stop "${name}" ${editor.stop ? "updated" : "added"}.` });
      setEditor(null);
      fetchData();
    } catch (err) {
      setFormError(`Could not save the stop: ${errorText(err)}`);
    } finally {
      setSaving(false);
    }
  };

  // ── Row actions ────────────────────────────────────────────────────────────
  const runAction = async (action, successText, failureText) => {
    setConfirm(null);
    try {
      await action();
      setNotice({ variant: "success", text: successText });
      fetchData();
    } catch (err) {
      setNotice({ variant: "danger", text: `${failureText}: ${errorText(err)}` });
    }
  };

  const toggleActive = (stop) => {
    const active = stop.is_active !== false;
    const run = () => runAction(
      () => updateStop(stop.id, { is_active: !active }),
      `Stop "${stop.name}" ${active ? "deactivated" : "reactivated"}.`,
      `Could not ${active ? "deactivate" : "reactivate"} the stop`,
    );
    const routes = routesOf(stop);
    if (!active || routes.length === 0) { run(); return; }
    setConfirm({
      title: "Deactivate Stop?",
      message: `${stop.name} is on ${routes.join(", ")}. While inactive it is left off the route map and the stops students can pick. Nothing is deleted, and you can reactivate it at any time.`,
      confirmLabel: "Deactivate",
      danger: false,
      onConfirm: run,
    });
  };

  const askDelete = (stop) => {
    const routes = routesOf(stop);
    const usage = routes.length ? `${stop.name} is on ${routes.length} route${routes.length === 1 ? "" : "s"}: ${routes.join(", ")}. ` : "";
    setConfirm({
      title: "Delete Stop?",
      message: `${usage}Deleting ${stop.name} also removes any route stops, semester registrations, transport registrations, and route change requests tied to it. This cannot be undone. To keep that history, deactivate the stop instead.`,
      confirmLabel: "Yes, Delete",
      danger: true,
      onConfirm: () => runAction(() => deleteStop(stop.id), `Stop "${stop.name}" deleted.`, "Could not delete the stop"),
    });
  };

  // ── List ───────────────────────────────────────────────────────────────────
  const query = searchTerm.trim().toLowerCase();
  const filteredStops = useMemo(
    () => (query ? stops.filter((stop) => stop.name?.toLowerCase().includes(query) || stop.address?.toLowerCase().includes(query)) : stops),
    [stops, query],
  );
  const otherStops = useMemo(() => stops.filter((stop) => stop.id !== editor?.stop?.id), [stops, editor]);

  const columns = [
    {
      key: "name",
      label: "Stop",
      render: (row) => (
        <div>
          <strong>{row.name}</strong>
          <div style={mutedText}>{row.address && row.address !== NO_ADDRESS ? row.address : "No address"}</div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>{row.latitude}, {row.longitude}</div>
        </div>
      ),
    },
    { key: "routes", label: "Routes", render: (row) => routesOf(row).join(", ") || <span style={{ color: colors.textMuted }}>Not on a route</span> },
    { key: "is_active", label: "Status", render: (row) => <StatusBadge active={row.is_active !== false} onClick={() => toggleActive(row)} /> },
    { key: "created_at", label: "Added", render: (row) => (row.created_at ? new Date(row.created_at).toLocaleDateString() : "—") },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button onClick={() => openEditor(row)} style={{ ...btn.ghost, ...smallBtn }}><Icon name="edit" size={13} /> Edit</button>
          <button onClick={() => askDelete(row)} style={{ ...btn.danger, ...smallBtn }}><Icon name="trash" size={13} /> Delete</button>
        </div>
      ),
    },
  ];
  // The split view's list is half-width, so it keeps only what you need to pick a stop.
  const splitColumns = columns.filter((column) => ["name", "is_active", "actions"].includes(column.key));

  const emptyMessage = query ? "No stops match your search." : "No stops yet. Add one or import a file.";
  const stopsMap = (
    <div>
      <StopsMap stops={filteredStops} height={view === "map" ? 600 : 520} highlightId={hoveredId} onStopClick={openEditor} onMapClick={addAt} />
      <div style={{ ...mutedText, display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
        <span style={withIcon}><Icon name="pin" color="#1976b9" /> Active stop: click to edit</span>
        <span style={withIcon}><Icon name="pin" color="#94a3b8" /> Inactive stop: click to edit</span>
        <span style={withIcon}><Icon name="campus" color="#b45309" /> FAST NUCES Main Campus</span>
        <span style={withIcon}><Icon name="plus" /> Click empty map to add a stop there</span>
      </div>
    </div>
  );

  return (
    <PageShell role="staff" title="Admin — Stops">
      <PageTitle sub="Manage pickup/dropoff stops.">Stops</PageTitle>
      {notice && <Banner variant={notice.variant}>{notice.text}</Banner>}

      {confirm && (
        <ConfirmModal
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.confirmLabel}
          danger={confirm.danger}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}

      {editor && (
        <FormModal
          title={editor.stop ? "Edit Stop" : "Add Stop"}
          sub={editor.stop ? "Update the stop's details or move its pin." : "Name the stop and place its pin on the map."}
          submitLabel={editor.stop ? "Save Changes" : "Add Stop"}
          loading={saving}
          onClose={closeEditor}
          onSubmit={handleSubmit}
          width="700px"
        >
          {formError && <div style={{ flex: "1 1 100%", textAlign: "left" }}><Banner variant="danger">{formError}</Banner></div>}
          {duplicate && (
            <div style={{ flex: "1 1 100%", textAlign: "left" }}>
              <Banner variant="warning">
                This looks like the existing stop "{duplicate.name}" (same name, or within {DUPLICATE_RADIUS_M} m). You can still save it.{" "}
                <button type="button" style={linkBtn} onClick={() => openEditor(duplicate)}>Open that stop instead</button>
              </Banner>
            </div>
          )}
          <Field label="Stop Name" required flex="1 1 200px">
            <input name="name" placeholder="e.g. Gulshan Chowrangi" value={form.name} onChange={handleChange} style={inputStyle} autoFocus />
          </Field>
          <Field label="Latitude" required flex="0 1 140px">
            <input name="latitude" type="number" step="0.000001" placeholder="24.9215" value={form.latitude} onChange={handleChange} style={inputStyle} />
          </Field>
          <Field label="Longitude" required flex="0 1 140px">
            <input name="longitude" type="number" step="0.000001" placeholder="67.0847" value={form.longitude} onChange={handleChange} style={inputStyle} />
          </Field>
          <Field label="Address" flex="2 1 280px">
            <input name="address" placeholder="Filled in from the map, or type it" value={form.address} onChange={handleChange} style={inputStyle} />
          </Field>
          <div style={{ flex: "1 1 100%" }}>
            <StopLocationPicker latitude={form.latitude} longitude={form.longitude} onChange={setLocation} height={280} stops={otherStops} onStopClick={openEditor} />
          </div>
        </FormModal>
      )}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
        <div style={{ position: "relative", flex: "1 1 240px" }}>
          <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", display: "flex", color: colors.textMuted, pointerEvents: "none" }}>
            <Icon name="search" />
          </span>
          <input
            type="search"
            placeholder="Search stops by name or address…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            aria-label="Search stops"
            style={{ ...inputStyle, width: "100%", paddingLeft: 36 }}
          />
        </div>
        <div role="group" aria-label="Layout" style={{ display: "flex", gap: 4 }}>
          {VIEWS.map(([key, label, icon]) => (
            <button key={key} type="button" aria-pressed={view === key} onClick={() => chooseView(key)} style={{ ...(view === key ? btn.primary : btn.ghost), ...smallBtn }}>
              <Icon name={icon} size={14} /> {label}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => openEditor(null)} style={{ ...btn.primary, ...withIcon }}><Icon name="plus" /> Add stop</button>
      </div>
      <StopImport stops={stops} onChanged={fetchData} />

      {view === "list" && <Table columns={columns} rows={filteredStops} emptyMessage={emptyMessage} />}
      {view === "map" && stopsMap}
      {view === "split" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 16, alignItems: "start" }}>
          <div style={{ maxHeight: 560, overflowY: "auto" }}>
            <Table columns={splitColumns} rows={filteredStops} emptyMessage={emptyMessage} onRowHover={(row) => setHoveredId(row?.id ?? null)} />
          </div>
          {stopsMap}
        </div>
      )}
    </PageShell>
  );
}

export default StopsPage;
