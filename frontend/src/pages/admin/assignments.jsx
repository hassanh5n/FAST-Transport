// Route Assignments: every published route needs a bus and a driver for the active
// semester. The page is a coverage board: routes without a bus come first and are
// assigned inline; one-click auto-assign proposes the rest for the admin to review.
import { useEffect, useMemo, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Banner, ConfirmModal, Field, FormModal, ModalLayer, Spinner } from "../../components/ui";
import Icon from "../../components/Icon";
import { selectStyle, inputStyle } from "../../styles/formStyles";
import { btn, colors, fonts, radius, shadow } from "../../theme";
import {
  getAssignments, createAssignment, updateAssignment, deleteAssignment,
  getRoutes, getBuses, getDrivers, getSemesters, getAutoAssignPlan, applyAutoAssign,
} from "../../services/transportService";
import { useContractor, ContractorSwitch } from "../../components/ContractorSwitch";
import "./assignments.css";

const FILTERS = [
  ["all", "All routes"],
  ["open", "Needs a bus"],
  ["over", "Over capacity"],
  ["ok", "Covered"],
];

// A bus or driver fits a route when either side has no contractor yet, or both match.
const fitsOwner = (owner) => (item) => owner == null || item.contractor == null || item.contractor === owner;
const errorText = (err) => {
  const data = err.response?.data;
  if (!data) return err.message || "Something went wrong.";
  if (typeof data === "string") return data;
  if (data.detail && !data.rows) return data.detail;
  if (data.rows) return data.rows.map((r) => `Row ${r.row}: ${Object.values(r.errors).flat().join(" ")}`).join(" ");
  return Object.values(data).flat().join(" ");
};
const plural = (n, word) => `${n} ${n === 1 ? word : word === "bus" ? "buses" : `${word}s`}`;

function AssignmentsPage() {
  const contractor = useContractor();
  const [assignments, setAssignments] = useState(null);
  const [routes, setRoutes] = useState([]);
  const [buses, setBuses] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [plan, setPlan] = useState(null);           // auto-assign preview; also carries students per route
  const [planError, setPlanError] = useState("");
  const [notice, setNotice] = useState(null);       // { variant, text }
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [drafts, setDrafts] = useState({});         // routeId -> { bus_id, driver_id } for inline assigning
  const [adding, setAdding] = useState(null);       // covered route whose "add a bus" row is open
  const [busyRoute, setBusyRoute] = useState(null);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({ route_id: "", bus_id: "", driver_id: "" });
  const [savingEdit, setSavingEdit] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [preview, setPreview] = useState(null);     // { proposals, keep:Set }
  const [applying, setApplying] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  const loadPlan = () =>
    getAutoAssignPlan()
      .then((res) => { setPlan(res.data); setPlanError(""); })
      .catch((err) => { setPlan(null); setPlanError(errorText(err)); });

  const loadAssignments = () =>
    getAssignments()
      .then((res) => setAssignments(res.data))
      .catch(() => { setAssignments([]); setNotice({ variant: "danger", text: "Assignments could not be loaded. Refresh the page to try again." }); });

  const reload = () => Promise.all([loadAssignments(), loadPlan()]);

  useEffect(() => {
    reload();
    Promise.all([getRoutes(), getBuses(), getDrivers(), getSemesters()])
      .then(([r, b, d, s]) => { setRoutes(r.data); setBuses(b.data); setDrivers(d.data); setSemesters(s.data); })
      .catch(() => setNotice({ variant: "danger", text: "Routes, buses or drivers could not be loaded. Refresh the page to try again." }));
  }, []);

  const semester = semesters.find((s) => s.is_active) || null;

  // ── Who is running what this semester ────────────────────────────────────
  const board = useMemo(() => {
    const current = (assignments || []).filter((a) => a.is_active && a.semester?.id === semester?.id);
    const byRoute = new Map();
    current.forEach((a) => byRoute.set(a.route?.id, [...(byRoute.get(a.route?.id) || []), a]));
    const busyBuses = new Set(current.map((a) => a.bus?.id));
    const busyDrivers = new Set(current.map((a) => a.driver?.id));

    const rows = routes
      .filter((r) => r.is_active && r.status === "published" && contractor.matches(r.contractor))
      .map((route) => {
        const running = byRoute.get(route.id) || [];
        const seats = running.reduce((sum, a) => sum + (a.bus?.capacity || 0), 0);
        const students = plan?.students?.[route.id] ?? null;
        const state = !running.length ? "open" : students != null && students > seats ? "over" : "ok";
        return { route, running, seats, students, state };
      });

    return {
      rows,
      freeBuses: buses.filter((b) => b.is_active && !busyBuses.has(b.id) && contractor.matches(b.contractor)),
      freeDrivers: drivers.filter((d) => d.is_available && !busyDrivers.has(d.id) && contractor.matches(d.contractor)),
      inactive: (assignments || []).filter((a) => !current.includes(a) && contractor.matches(a.route?.contractor)),
      counts: {
        all: rows.length,
        open: rows.filter((r) => r.state === "open").length,
        over: rows.filter((r) => r.state === "over").length,
        ok: rows.filter((r) => r.state === "ok").length,
      },
    };
  }, [assignments, routes, buses, drivers, plan, semester, contractor]);

  const order = { open: 0, over: 1, ok: 2 };
  const visibleRows = board.rows
    .filter((r) => filter === "all" || r.state === filter)
    .filter((r) => !search.trim() || [r.route.name, ...r.running.flatMap((a) => [a.bus?.bus_number, a.driver?.name])]
      .some((text) => text?.toLowerCase().includes(search.trim().toLowerCase())))
    .sort((a, b) => order[a.state] - order[b.state] || a.route.name.localeCompare(b.route.name));

  const proposals = (plan?.proposals || []).filter((p) => contractor.matches(p.contractor));

  // ── Actions ──────────────────────────────────────────────────────────────
  const draftFor = (routeId) => drafts[routeId] || { bus_id: "", driver_id: "" };
  const setDraft = (routeId, patch) => setDrafts((all) => ({ ...all, [routeId]: { ...draftFor(routeId), ...patch } }));

  const assign = async (route) => {
    const draft = draftFor(route.id);
    if (!draft.bus_id || !draft.driver_id) {
      setNotice({ variant: "warning", text: `Choose a bus and a driver for ${route.name}.` });
      return;
    }
    setBusyRoute(route.id);
    try {
      await createAssignment({ route_id: route.id, bus_id: draft.bus_id, driver_id: draft.driver_id, semester_id: semester.id });
      setDrafts((all) => { const next = { ...all }; delete next[route.id]; return next; });
      setAdding(null);
      setNotice({ variant: "success", text: `${route.name} is now covered.` });
      await reload();
    } catch (err) {
      setNotice({ variant: "danger", text: `${route.name}: ${errorText(err)}` });
    } finally {
      setBusyRoute(null);
    }
  };

  const openEdit = (a) => {
    setEditing(a);
    setEditForm({ route_id: a.route?.id ?? "", bus_id: a.bus?.id ?? "", driver_id: a.driver?.id ?? "" });
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    setSavingEdit(true);
    try {
      await updateAssignment(editing.id, editForm);
      setEditing(null);
      setNotice({ variant: "success", text: "Assignment updated." });
      await reload();
    } catch (err) {
      setNotice({ variant: "danger", text: errorText(err) });
    } finally {
      setSavingEdit(false);
    }
  };

  const setActive = async (a, isActive) => {
    try {
      await updateAssignment(a.id, { is_active: isActive });
      setNotice({ variant: "success", text: `${a.bus?.bus_number} on ${a.route?.name} ${isActive ? "reactivated" : "paused"}.` });
      await reload();
    } catch (err) {
      setNotice({ variant: "danger", text: errorText(err) });
    }
  };

  const confirmDelete = async () => {
    const a = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteAssignment(a.id);
      setNotice({ variant: "success", text: `${a.bus?.bus_number} removed from ${a.route?.name}.` });
      await reload();
    } catch (err) {
      setNotice({ variant: "danger", text: errorText(err) });
    }
  };

  const openPreview = async () => {
    await loadPlan();
    setPreview("open");
  };

  const kept = preview === "open" ? proposals.filter((p) => !p.dropped) : [];
  const toggleProposal = (index) =>
    setPlan((current) => ({
      ...current,
      proposals: current.proposals.map((p, i) => (i === index ? { ...p, dropped: !p.dropped } : p)),
    }));

  const applyPreview = async () => {
    setApplying(true);
    try {
      const res = await applyAutoAssign(kept.map(({ route_id, bus_id, driver_id }) => ({ route_id, bus_id, driver_id })));
      setPreview(null);
      setNotice({ variant: "success", text: `${plural(res.data.length, "bus")} assigned. Students on these routes can now be seated.` });
      await reload();
    } catch (err) {
      setNotice({ variant: "danger", text: `Nothing was saved. ${errorText(err)}` });
      await loadPlan();
    } finally {
      setApplying(false);
    }
  };

  // ── Edit modal options ───────────────────────────────────────────────────
  const editOwner = routes.find((r) => String(r.id) === String(editForm.route_id))?.contractor ?? null;
  const editBuses = editing ? [editing.bus, ...board.freeBuses].filter(Boolean).filter(fitsOwner(editOwner)) : [];
  const editDrivers = editing ? [editing.driver, ...board.freeDrivers].filter(Boolean).filter(fitsOwner(editOwner)) : [];

  const loading = assignments === null;
  const covered = board.counts.all - board.counts.open;
  const coverage = board.counts.all ? covered / board.counts.all : 0;

  return (
    <PageShell role="staff" title="Admin — Assignments">
      <div className="asg-page">
        <div style={styles.head}>
          <PageTitle sub={semester ? `${semester.name} · each published route needs a bus and a driver.` : "No semester is active, so nothing can be assigned yet."}>
            Route Assignments
          </PageTitle>
          <div style={styles.headActions}>
            <ContractorSwitch value={contractor} />
            <button
              type="button"
              onClick={openPreview}
              disabled={!semester || !proposals.length}
              style={{ ...btn.primary, ...styles.autoBtn, ...(!semester || !proposals.length ? styles.disabled : null) }}
              title={proposals.length ? "Review the proposed buses and drivers before anything is saved" : "Every route that can be covered already is"}
            >
              <Icon name="zap" size={15} />
              {proposals.length ? `Auto-assign ${plural(proposals.length, "bus")}` : "Nothing left to auto-assign"}
            </button>
          </div>
        </div>

        {notice && (
          <div style={{ position: "relative" }}>
            <Banner variant={notice.variant}>
              <span style={{ paddingRight: 28, display: "block" }}>{notice.text}</span>
            </Banner>
            <button type="button" className="asg-icon-btn" onClick={() => setNotice(null)} aria-label="Dismiss message" style={styles.noticeClose}>
              <Icon name="x" size={14} />
            </button>
          </div>
        )}
        {planError && semester && <Banner variant="warning">Auto-assign is unavailable: {planError}</Banner>}

        {/* Coverage at a glance */}
        <section style={styles.summary} aria-label="Coverage this semester">
          <div style={{ flex: "1 1 260px", minWidth: 0 }}>
            <p style={styles.summaryLine}>
              <strong className="asg-num" style={styles.summaryBig}>{covered}</strong>
              <span> of {plural(board.counts.all, "route")} have a bus</span>
            </p>
            <div style={styles.track} role="img" aria-label={`${Math.round(coverage * 100)} percent of routes covered`}>
              <div style={{ ...styles.trackFill, transform: `scaleX(${coverage})` }} />
            </div>
          </div>
          <dl className="asg-facts" style={styles.facts}>
            <Fact label="Need a bus" value={board.counts.open} tone={board.counts.open ? "warning" : "muted"} />
            <Fact label="Over capacity" value={board.counts.over} tone={board.counts.over ? "danger" : "muted"} />
            <Fact label="Free buses" value={board.freeBuses.length} />
            <Fact label="Free drivers" value={board.freeDrivers.length} />
          </dl>
        </section>

        <div className="asg-layout">
          <section style={styles.boardCard} aria-label="Routes">
            <div style={styles.toolbar}>
              <div role="group" aria-label="Show routes" style={styles.filters}>
                {FILTERS.map(([key, label]) => (
                  <button key={key} type="button" className="asg-filter" aria-pressed={filter === key} onClick={() => setFilter(key)}>
                    {label} <span className="asg-filter-count">{board.counts[key]}</span>
                  </button>
                ))}
              </div>
              <label style={styles.searchWrap}>
                <Icon name="search" size={14} color={colors.textMuted} />
                <input
                  type="search" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Route, bus or driver" aria-label="Search routes, buses and drivers"
                  style={styles.search}
                />
              </label>
            </div>

            {loading ? <Spinner /> : !visibleRows.length ? (
              <p style={styles.empty}>
                {board.counts.all === 0
                  ? "There are no published routes yet. Publish a route on the Routes page and it will appear here."
                  : search ? `No route, bus or driver matches “${search}”.`
                  : filter === "open" ? "Every route has a bus." : filter === "over" ? "No route has more students than seats." : "No routes in this view."}
              </p>
            ) : (
              <div>
                {visibleRows.map((row) => (
                  <RouteRow
                    key={row.route.id}
                    row={row}
                    contractorName={contractor.nameOf(row.route.contractor)}
                    freeBuses={board.freeBuses.filter(fitsOwner(row.route.contractor))}
                    freeDrivers={board.freeDrivers}
                    draft={draftFor(row.route.id)}
                    onDraft={(patch) => setDraft(row.route.id, patch)}
                    adding={adding === row.route.id}
                    onAdd={() => setAdding(adding === row.route.id ? null : row.route.id)}
                    onAssign={() => assign(row.route)}
                    busy={busyRoute === row.route.id}
                    onEdit={openEdit}
                    onPause={(a) => setActive(a, false)}
                    onDelete={setPendingDelete}
                    canAssign={Boolean(semester)}
                  />
                ))}
              </div>
            )}
          </section>

          <aside style={styles.pool} aria-label="Free buses and drivers">
            <h3 style={styles.poolTitle}>Free this semester</h3>
            <div className="asg-pool-lists">
            <PoolList
              icon="bus"
              title="Buses"
              items={board.freeBuses}
              empty="Every active bus is on a route."
              render={(b) => (
                <>
                  <span style={styles.poolName}>{b.bus_number}</span>
                  <span className="asg-num" style={styles.poolMeta}>{b.capacity} seats{contractor.nameOf(b.contractor) ? ` · ${contractor.nameOf(b.contractor)}` : ""}</span>
                </>
              )}
            />
            <PoolList
              icon="user"
              title="Drivers"
              items={board.freeDrivers}
              empty="Every available driver is on a route."
              render={(d) => (
                <>
                  <span style={styles.poolName}>{d.name}</span>
                  <span style={styles.poolMeta}>{contractor.nameOf(d.contractor) || "No contractor"}</span>
                </>
              )}
            />
            </div>
          </aside>
        </div>

        {board.inactive.length > 0 && (
          <section style={{ ...styles.boardCard, marginTop: 20 }}>
            <button type="button" className="asg-link" onClick={() => setShowInactive((v) => !v)} aria-expanded={showInactive} style={{ padding: "14px 18px" }}>
              {showInactive ? "Hide" : "Show"} paused and past assignments ({board.inactive.length})
            </button>
            {showInactive && board.inactive.map((a) => (
              <div key={a.id} className="asg-route" style={{ opacity: 0.85 }}>
                <div>
                  <div style={styles.routeName}>{a.route?.name}</div>
                  <div style={styles.routeMeta}>{a.semester?.name}{a.is_active ? "" : " · paused"}</div>
                </div>
                <div style={styles.routeMeta}>{a.bus?.bus_number} · {a.driver?.name}</div>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
                  {!a.is_active && a.semester?.id === semester?.id && (
                    <button type="button" onClick={() => setActive(a, true)} style={styles.smallGhost}>Reactivate</button>
                  )}
                  <button type="button" onClick={() => setPendingDelete(a)} style={styles.smallDanger}>Delete</button>
                </div>
              </div>
            ))}
          </section>
        )}
      </div>

      {pendingDelete && (
        <ConfirmModal
          title="Remove this bus from the route?"
          message={`${pendingDelete.bus?.bus_number} will stop running ${pendingDelete.route?.name}. Seats allocated on this bus are released, and waiting students may be offered seats elsewhere. This cannot be undone.`}
          confirmLabel="Remove"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {editing && (
        <FormModal
          title={`Change ${editing.route?.name}`}
          sub="Swap the bus or driver, or move this pair to another route."
          submitLabel="Save changes"
          loading={savingEdit}
          onClose={() => setEditing(null)}
          onSubmit={saveEdit}
          width="640px"
        >
          <Field label="Route" required flex="1 1 170px">
            <select value={editForm.route_id} onChange={(e) => setEditForm({ ...editForm, route_id: e.target.value })} style={selectStyle}>
              {routes.filter((r) => r.is_active && r.status === "published").map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
          <Field label="Bus" required flex="1 1 140px">
            <select value={editForm.bus_id} onChange={(e) => setEditForm({ ...editForm, bus_id: e.target.value })} style={selectStyle}>
              {editBuses.map((b) => <option key={b.id} value={b.id}>{b.bus_number} · {b.capacity} seats</option>)}
            </select>
          </Field>
          <Field label="Driver" required flex="1 1 140px">
            <select value={editForm.driver_id} onChange={(e) => setEditForm({ ...editForm, driver_id: e.target.value })} style={selectStyle}>
              {editDrivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
        </FormModal>
      )}

      {preview === "open" && plan && (
        <AutoAssignDialog
          plan={plan}
          proposals={proposals}
          keptCount={kept.length}
          contractor={contractor}
          onToggle={(p) => toggleProposal(plan.proposals.indexOf(p))}
          onClose={() => setPreview(null)}
          onApply={applyPreview}
          applying={applying}
        />
      )}
    </PageShell>
  );
}

function Fact({ label, value, tone = "default" }) {
  const color = { warning: colors.warningText, danger: colors.dangerText, muted: colors.textMuted, default: colors.textPrimary }[tone];
  return (
    <div style={styles.fact}>
      <dt style={styles.factLabel}>{label}</dt>
      <dd className="asg-num" style={{ ...styles.factValue, color }}>{value}</dd>
    </div>
  );
}

function SeatMeter({ students, seats }) {
  if (students == null) return <span style={styles.routeMeta}>{seats ? `${seats} seats` : "No seats yet"}</span>;
  const over = seats > 0 && students > seats; // a route with no bus yet reads as "needs a bus", not overcrowded
  const fill = seats ? Math.min(students / seats, 1) : students ? 1 : 0;
  return (
    <div>
      <div className="asg-num" style={{ fontSize: 13, color: over ? colors.dangerText : colors.textPrimary, fontWeight: 600 }}>
        {students} <span style={{ color: colors.textSecondary, fontWeight: 400 }}>{students === 1 ? "student" : "students"} · {seats} seats</span>
      </div>
      <div style={{ ...styles.meter }} aria-hidden="true">
        <div style={{ ...styles.meterFill, width: `${fill * 100}%`, background: over ? colors.dangerDot : seats ? colors.accent : colors.warningDot }} />
      </div>
    </div>
  );
}

function RouteRow({ row, contractorName, freeBuses, freeDrivers, draft, onDraft, adding, onAdd, onAssign, busy, onEdit, onPause, onDelete, canAssign }) {
  const { route, running, seats, students, state } = row;
  const owner = route.contractor ?? freeBuses.find((b) => String(b.id) === String(draft.bus_id))?.contractor ?? null;
  const drivers = freeDrivers.filter(fitsOwner(owner));
  const showPicker = canAssign && (state === "open" || adding);

  return (
    <div className={`asg-route${state === "open" ? " asg-route--open" : ""}`}>
      <div style={{ minWidth: 0 }}>
        <div style={styles.routeName}>{route.name}</div>
        <div style={styles.routeMeta}>
          {contractorName || "No contractor"}
          {state === "open" && <span style={styles.needTag}>Needs a bus</span>}
          {state === "over" && <span style={styles.overTag}>Over capacity</span>}
        </div>
      </div>

      <SeatMeter students={students} seats={seats} />

      <div style={{ display: "grid", gap: 8, minWidth: 0 }}>
        {running.map((a) => (
          <div key={a.id} className="asg-chip" title={`${a.bus?.bus_number}: ${a.bus?.capacity} seats, driven by ${a.driver?.name}`}>
            <Icon name="bus" size={15} color={colors.accent} />
            {/* the route's total seats are in the meter beside this; each bus's own count is in the tooltip */}
            <span style={{ fontWeight: 600, color: colors.textPrimary, whiteSpace: "nowrap" }}>{a.bus?.bus_number}</span>
            <span style={styles.chipDivider} aria-hidden="true" />
            <Icon name="user" size={14} color={colors.textSecondary} />
            <span style={styles.chipDriver}>{a.driver?.name}</span>
            <span className="asg-chip-actions">
              <button type="button" className="asg-icon-btn" onClick={() => onEdit(a)} aria-label={`Change ${a.bus?.bus_number} on ${route.name}`} title="Change bus, driver or route">
                <Icon name="edit" size={14} />
              </button>
              <button type="button" className="asg-icon-btn" onClick={() => onPause(a)} aria-label={`Pause ${a.bus?.bus_number} on ${route.name}`} title="Pause (keeps the record)">
                <Icon name="clock" size={14} />
              </button>
              <button type="button" className="asg-icon-btn asg-icon-btn--danger" onClick={() => onDelete(a)} aria-label={`Remove ${a.bus?.bus_number} from ${route.name}`} title="Remove">
                <Icon name="trash" size={14} />
              </button>
            </span>
          </div>
        ))}

        {showPicker ? (
          <div style={styles.picker}>
            <select aria-label={`Bus for ${route.name}`} value={draft.bus_id} onChange={(e) => onDraft({ bus_id: e.target.value })} style={{ ...selectStyle, ...styles.pickerSelect }}>
              <option value="">{freeBuses.length ? "Choose a bus" : "No free bus fits"}</option>
              {freeBuses.map((b) => <option key={b.id} value={b.id}>{b.bus_number} · {b.capacity} seats</option>)}
            </select>
            <select aria-label={`Driver for ${route.name}`} value={draft.driver_id} onChange={(e) => onDraft({ driver_id: e.target.value })} style={{ ...selectStyle, ...styles.pickerSelect }}>
              <option value="">{drivers.length ? "Choose a driver" : "No free driver fits"}</option>
              {drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <button type="button" onClick={onAssign} disabled={busy} style={{ ...btn.primary, ...styles.pickerBtn, ...(busy ? styles.disabled : null) }}>
              {busy ? "Assigning…" : "Assign"}
            </button>
            {adding && state !== "open" && (
              <button type="button" className="asg-icon-btn" onClick={onAdd} aria-label="Cancel adding a bus"><Icon name="x" size={14} /></button>
            )}
          </div>
        ) : canAssign && (
          <button type="button" className="asg-link" onClick={onAdd}>
            <Icon name="plus" size={13} /> Add another bus
          </button>
        )}
      </div>
    </div>
  );
}

function PoolList({ icon, title, items, empty, render }) {
  return (
    <div style={{ marginTop: 16 }}>
      <div style={styles.poolHead}>
        <Icon name={icon} size={14} color={colors.textSecondary} />
        <span>{title}</span>
        <span className="asg-num" style={styles.poolCount}>{items.length}</span>
      </div>
      {items.length ? (
        <ul style={styles.poolUl}>
          {items.map((item) => <li key={item.id} style={styles.poolLi}>{render(item)}</li>)}
        </ul>
      ) : <p style={styles.poolEmpty}>{empty}</p>}
    </div>
  );
}

function AutoAssignDialog({ plan, proposals, keptCount, contractor, onToggle, onClose, onApply, applying }) {
  const groups = [
    ["Routes with no bus", proposals.filter((p) => p.reason === "No bus yet")],
    ["Extra buses where students outnumber seats", proposals.filter((p) => p.reason !== "No bus yet")],
  ].filter(([, items]) => items.length);
  const unplaced = plan.unplaced;

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !applying) onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [applying, onClose]);

  return (
    <ModalLayer>
      <div style={styles.overlay} onMouseDown={() => !applying && onClose()}>
        <div className="asg-dialog" role="dialog" aria-modal="true" aria-labelledby="asg-dialog-title" style={styles.dialog} onMouseDown={(e) => e.stopPropagation()}>
          <div style={styles.dialogHead}>
            <div>
              <h3 id="asg-dialog-title" style={styles.dialogTitle}>Auto-assign for {plan.semester.name}</h3>
              <p style={styles.dialogSub}>
                Nothing is saved until you confirm. Each bus goes to a route of its own contractor, the biggest buses to the busiest routes.
                Untick anything you want to assign yourself.
              </p>
            </div>
            <button type="button" className="asg-icon-btn" onClick={onClose} disabled={applying} aria-label="Close"><Icon name="x" size={16} /></button>
          </div>

          <div style={styles.dialogBody}>
            {groups.map(([title, items]) => (
              <div key={title} style={{ marginBottom: 16 }}>
                <h4 style={styles.groupTitle}>{title} <span className="asg-num" style={{ color: colors.textMuted }}>{items.length}</span></h4>
                <div style={styles.proposalBox}>
                  {items.map((p) => (
                    <label key={`${p.route_id}-${p.bus_id}`} className={`asg-proposal${p.dropped ? " asg-proposal--off" : ""}`}>
                      <input type="checkbox" checked={!p.dropped} onChange={() => onToggle(p)} disabled={applying} />
                      <span style={{ minWidth: 0 }}>
                        <span style={styles.proposalRoute}>{p.route}</span>
                        <span style={styles.proposalPair}>
                          {p.bus} <span className="asg-num" style={{ color: colors.textMuted }}>({p.capacity} seats)</span> · {p.driver}
                          {contractor.nameOf(p.contractor) ? <span style={{ color: colors.textMuted }}> · {contractor.nameOf(p.contractor)}</span> : null}
                        </span>
                      </span>
                      <span className="asg-num" style={styles.proposalReason}>
                        {p.reason === "No bus yet" ? `${p.students} students · ${p.seats_after} seats` : p.reason}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}

            {unplaced.length > 0 && (
              <Banner variant="warning">
                <strong>{plural(unplaced.length, "route")} still {unplaced.length === 1 ? "needs" : "need"} a bus after this.</strong>{" "}
                {unplaced.map((u) => `${u.route}: ${u.reason.replace(/\.$/, "")}`).join("; ")}. Add buses or drivers for that contractor, or assign them by hand.
              </Banner>
            )}
            {(plan.spare_buses.length > 0 || plan.spare_drivers.length > 0) && (
              <p style={styles.spare}>
                Left free afterwards: {plural(plan.spare_buses.length, "bus")} and {plural(plan.spare_drivers.length, "driver")}
                {plan.spare_buses.length ? ` (${plan.spare_buses.map((b) => b.bus_number).join(", ")})` : ""}. None of them fits a route that still needs seats.
              </p>
            )}
          </div>

          <div style={styles.dialogFoot}>
            <span className="asg-num" style={{ fontSize: 13, color: colors.textSecondary }}>{keptCount} of {proposals.length} selected</span>
            <div style={{ display: "flex", gap: 10 }}>
              <button type="button" onClick={onClose} disabled={applying} style={btn.ghost}>Cancel</button>
              <button type="button" onClick={onApply} disabled={applying || !keptCount} style={{ ...btn.primary, ...(applying || !keptCount ? styles.disabled : null) }}>
                {applying ? "Assigning…" : `Assign ${plural(keptCount, "bus")}`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </ModalLayer>
  );
}

const styles = {
  head: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" },
  headActions: { display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" },
  autoBtn: { display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 16, padding: "10px 18px" },
  disabled: { opacity: 0.55, cursor: "not-allowed" },
  noticeClose: { position: "absolute", top: 7, right: 8 },

  summary: {
    display: "flex", gap: 28, alignItems: "center", flexWrap: "wrap",
    background: colors.cardBg, border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg,
    boxShadow: shadow.card, padding: "18px 22px", marginBottom: 20,
  },
  summaryLine: { margin: "0 0 10px", fontSize: 14, color: colors.textSecondary },
  summaryBig: { fontFamily: fonts.heading, fontSize: 26, color: colors.textPrimary, marginRight: 4, letterSpacing: "-0.02em" },
  track: { height: 8, borderRadius: radius.pill, background: colors.neutralBg, overflow: "hidden" },
  trackFill: { height: "100%", background: colors.accent, transformOrigin: "left", transition: "transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)" },
  facts: { display: "flex", gap: 26, margin: 0, flexWrap: "wrap" },
  fact: { margin: 0 },
  factLabel: { fontSize: 11.5, fontWeight: 600, color: colors.textSecondary, marginBottom: 2 },
  factValue: { margin: 0, fontFamily: fonts.heading, fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em" },

  boardCard: { background: colors.cardBg, border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, boxShadow: shadow.card, overflow: "hidden", minWidth: 0 },
  toolbar: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "12px 14px", borderBottom: `1px solid ${colors.borderLight}`, background: colors.tableHeaderBg },
  filters: { display: "flex", gap: 4, flexWrap: "wrap" },
  searchWrap: { display: "flex", alignItems: "center", gap: 8, ...inputStyle, padding: "7px 12px", flex: "0 1 240px", cursor: "text" },
  search: { border: "none", outline: "none", background: "transparent", fontSize: 13, width: "100%", color: colors.textPrimary, fontFamily: fonts.body },
  empty: { margin: 0, padding: "40px 24px", textAlign: "center", color: colors.textSecondary, fontSize: 13.5 },

  routeName: { fontFamily: fonts.heading, fontWeight: 600, fontSize: 15, color: colors.textPrimary, overflowWrap: "anywhere" },
  routeMeta: { fontSize: 12.5, color: colors.textSecondary, marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  needTag: { fontSize: 11, fontWeight: 600, color: colors.warningText, background: colors.warningBg, borderRadius: radius.pill, padding: "2px 8px" },
  overTag: { fontSize: 11, fontWeight: 600, color: colors.dangerText, background: colors.dangerBg, borderRadius: radius.pill, padding: "2px 8px" },
  meter: { height: 5, borderRadius: radius.pill, background: colors.neutralBg, overflow: "hidden", marginTop: 7, maxWidth: 180 },
  meterFill: { height: "100%", borderRadius: radius.pill },
  chipDivider: { width: 1, height: 16, background: colors.borderLight, margin: "0 2px" },
  chipDriver: { color: colors.textSecondary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 },
  picker: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" },
  pickerSelect: { flex: "1 1 150px", width: "auto", padding: "8px 30px 8px 11px", background: "#fff" },
  pickerBtn: { padding: "8px 16px" },
  smallGhost: { ...btn.ghost, padding: "6px 12px", fontSize: 12 },
  smallDanger: { ...btn.danger, padding: "6px 12px", fontSize: 12 },

  pool: { background: colors.cardBg, border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, boxShadow: shadow.card, padding: "18px 22px 20px" },
  poolTitle: { margin: 0, fontFamily: fonts.heading, fontSize: 15, fontWeight: 600, color: colors.textPrimary },
  poolHead: { display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 700, color: colors.textSecondary, marginBottom: 8 },
  poolCount: { marginLeft: "auto", fontWeight: 600, color: colors.textMuted },
  poolUl: { listStyle: "none", margin: 0, padding: 0, maxHeight: 260, overflowY: "auto", display: "grid", gap: 2 },
  poolLi: { display: "flex", justifyContent: "space-between", gap: 10, padding: "6px 8px", borderRadius: radius.sm, background: colors.tableRowAlt, fontSize: 13 },
  poolName: { color: colors.textPrimary, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  poolMeta: { color: colors.textMuted, fontSize: 12, whiteSpace: "nowrap" },
  poolEmpty: { margin: 0, fontSize: 12.5, color: colors.textMuted },

  overlay: { position: "fixed", inset: 0, background: "rgba(11,45,66,0.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16 },
  dialog: { background: "#fff", borderRadius: radius.xl, boxShadow: shadow.modal, width: "100%", maxWidth: 720, maxHeight: "90vh", display: "flex", flexDirection: "column" },
  dialogHead: { display: "flex", justifyContent: "space-between", gap: 16, padding: "22px 24px 14px" },
  dialogTitle: { margin: "0 0 6px", fontFamily: fonts.heading, fontSize: 18, color: colors.textPrimary },
  dialogSub: { margin: 0, fontSize: 13, color: colors.textSecondary, lineHeight: 1.6, maxWidth: "62ch" },
  dialogBody: { padding: "4px 24px 8px", overflowY: "auto" },
  groupTitle: { margin: "8px 0 8px", fontSize: 12.5, fontWeight: 700, color: colors.textSecondary },
  proposalBox: { border: `1px solid ${colors.borderLight}`, borderRadius: radius.md, overflow: "hidden" },
  proposalRoute: { display: "block", fontWeight: 600, fontSize: 13.5, color: colors.textPrimary },
  proposalPair: { display: "block", fontSize: 12.5, color: colors.textSecondary, marginTop: 2 },
  proposalReason: { fontSize: 12, color: colors.textSecondary, whiteSpace: "nowrap" },
  spare: { fontSize: 12.5, color: colors.textSecondary, margin: "4px 0 8px", lineHeight: 1.6 },
  dialogFoot: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "14px 24px 20px", borderTop: `1px solid ${colors.borderLight}` },
};

export default AssignmentsPage;
