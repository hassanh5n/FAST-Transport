// Route plans: stored sets of routes + stops + ETAs. One is active and is what everyone sees;
// activating another rewrites the live routes. The route builder always edits the active plan.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import PageShell, { PageTitle } from "../../components/PageShell";
import Table from "../../components/Table";
import { Banner, ConfirmModal, FormModal, Field, SectionBlock, StatusBadge } from "../../components/ui";
import Icon from "../../components/Icon";
import { inputStyle, selectStyle } from "../../styles/formStyles";
import { btn, colors, fonts } from "../../theme";
import { cachedThumbnail, planThumbnail, pruneThumbnails } from "../../components/maps/planThumbnail";
import { downloadFile } from "../../utils/transferFiles";
import { AddressProgress, fillAddresses, hasNoAddress } from "../../components/StopImport";
import RoadLineBuilder from "../../components/RoadLineBuilder";
import {
  getRoutePlans, getRoutePlan, updateRoutePlan, deleteRoutePlan, duplicateRoutePlan, importRoutePlan,
  exportRoutePlan, previewRoutePlan, activateRoutePlan, getRoutePlanAttention,
} from "../../services/transportService";

// Any spreadsheet with these headings works; extra columns (e.g. "Map link") are ignored.
// Without Stop order or times, each route runs from the stop farthest from campus inwards.
const SAMPLE_CSV =
  "route_name,route_description,route_status,stop_order,name,latitude,longitude,address,morning_eta,evening_eta\n" +
  "Gulshan Route,Via University Road,published,1,Gulshan Chowrangi,24.921500,67.084700,,07:05,16:40\n";

const errorList = (err) => {
  const data = err.response?.data;
  return data && typeof data === "object" ? Object.values(data).flat().map(String) : [err.message];
};
const fileSlug = (name) => String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "plan";
const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

const inline = { display: "inline-flex", alignItems: "center", gap: 6 };
const smallBtn = { ...btn.ghost, ...inline, padding: "7px 12px", fontSize: 12, background: "#fff" };
const group = { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: colors.tableHeaderBg };
const groupLabel = { ...inline, fontSize: 13, fontWeight: 700, color: colors.textPrimary };
const mutedText = { fontSize: 12, color: colors.textSecondary };
const fullRow = { display: "grid", gap: 14, width: "100%", textAlign: "left" };

function NoteList({ title, items, tone = colors.textPrimary }) {
  if (!items.length) return null;
  return (
    <div>
      <strong style={{ fontSize: 13, color: tone }}>{title} ({items.length})</strong>
      <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 150, overflowY: "auto", fontSize: 12.5, color: colors.textSecondary }}>
        {items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
      </ul>
    </div>
  );
}

// Every control in a card row shares one height, so cards line up whatever actions they have.
const ROW = 36;
const rowBtn = { ...inline, justifyContent: "center", height: ROW, padding: "0 12px", fontSize: 13 };
const toolBtn = { ...btn.ghost, ...inline, justifyContent: "center", height: 32, padding: "0 6px", fontSize: 12, background: "#fff", minWidth: 0 };
const mapFrame = { position: "relative", display: "block", width: "100%", aspectRatio: "16 / 9", padding: 0, border: 0, borderBottom: `1px solid ${colors.borderLight}`, background: colors.neutralBg, cursor: "pointer", overflow: "hidden" };
const clamp2 = { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" };

function PlanCard({ plan, busy, onActivate, onView, onExport, onCopy, onRename, onDelete }) {
  // Keyed by fingerprint in the grid, so this state starts fresh whenever the plan's routes change.
  const [image, setImage] = useState(() => cachedThumbnail(plan));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (image || failed || plan.route_count === 0) return undefined;
    let live = true;
    planThumbnail(plan, () => getRoutePlan(plan.id).then((res) => res.data.routes))
      .then((url) => { if (live) setImage(url); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [plan, image, failed]);

  const lastUsed = plan.is_active ? "In use now" : plan.activated_at ? `Last active ${new Date(plan.activated_at).toLocaleDateString()}` : "Never activated";
  const placeholder = plan.route_count === 0 ? "No routes in this plan" : failed ? "Map preview unavailable" : "Drawing map…";

  // Border, shadow, hover lift and glow live in index.css (.plan-card) so they can animate.
  return (
    <article
      aria-label={`Route plan ${plan.name}`}
      className={`plan-card${plan.is_active ? " plan-card--active" : ""}`}
      style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}
    >
      <button type="button" onClick={onView} className="plan-card__map" style={mapFrame} aria-label={`View the routes in ${plan.name}`}>
        {image
          ? <img src={image} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          : <span style={{ ...mutedText, position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><Icon name="map" /> {placeholder}</span>}
        <span style={{ position: "absolute", top: 10, left: 10, boxShadow: "0 1px 4px rgba(11,45,66,0.25)", borderRadius: 999, display: "flex" }}>
          <StatusBadge active={plan.is_active} trueLabel="Active" falseLabel="Stored" />
        </span>
        {image && <span style={{ position: "absolute", right: 0, bottom: 0, padding: "1px 6px", fontSize: 10, color: colors.textSecondary, background: "rgba(255,255,255,0.8)", borderTopLeftRadius: 6 }}>© OpenStreetMap</span>}
      </button>

      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ ...clamp2, margin: 0, fontSize: 16, lineHeight: 1.3, fontWeight: 700, fontFamily: fonts.heading, color: colors.textPrimary, overflowWrap: "anywhere" }}>{plan.name}</h3>
            <p style={{ ...mutedText, margin: "4px 0 0" }}>
              <strong style={{ color: colors.textPrimary }}>{plan.route_count}</strong> {plan.route_count === 1 ? "route" : "routes"} · <strong style={{ color: colors.textPrimary }}>{plan.stop_count}</strong> {plan.stop_count === 1 ? "stop" : "stops"} · {lastUsed}
            </p>
          </div>
          {!plan.is_active && (
            <button type="button" disabled={busy} onClick={onDelete} title="Delete plan" aria-label={`Delete ${plan.name}`} style={{ ...btn.danger, ...inline, justifyContent: "center", flex: "0 0 auto", width: 32, height: 32, padding: 0 }}>
              <Icon name="trash" size={14} />
            </button>
          )}
        </div>
        {plan.description && <p style={{ ...mutedText, ...clamp2, margin: 0, overflowWrap: "anywhere" }}>{plan.description}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
          {plan.is_active
            ? <span style={{ ...rowBtn, flex: 1, gap: 8, fontWeight: 600, borderRadius: btn.primary.borderRadius, background: colors.successBg, color: colors.successText }}>
                <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: colors.successDot }} /> Live for everyone
              </span>
            : <button type="button" disabled={busy} onClick={onActivate} style={{ ...btn.primary, ...rowBtn, flex: 1 }}>Activate</button>}
          <button type="button" onClick={onView} style={{ ...btn.ghost, ...rowBtn, background: "#fff" }}><Icon name="list" size={13} /> View</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 6, paddingTop: 12, borderTop: `1px solid ${colors.borderLight}` }}>
          <button type="button" onClick={() => onExport("csv")} style={toolBtn}><Icon name="download" size={13} /> CSV</button>
          <button type="button" onClick={() => onExport("json")} style={toolBtn}><Icon name="download" size={13} /> JSON</button>
          <button type="button" onClick={onCopy} style={toolBtn}><Icon name="plus" size={13} /> Copy</button>
          <button type="button" onClick={onRename} style={toolBtn}><Icon name="edit" size={13} /> Rename</button>
        </div>
      </div>
    </article>
  );
}

function RoutePlansPage() {
  const fileInput = useRef(null);
  const fillCancelled = useRef(false);
  const previewSeq = useRef(0); // only the newest preview request may update the dialog
  const [previewing, setPreviewing] = useState(false);
  const [activations, setActivations] = useState(0); // remounts the road line builder after each activation
  const [imported, setImported] = useState(null); // { name, routes, created, reused, done, total, blocked? }
  const [plans, setPlans] = useState([]);
  const [attention, setAttention] = useState([]);
  const [notice, setNotice] = useState(null); // { variant, text, items? }
  const [busy, setBusy] = useState(false);
  const [activating, setActivating] = useState(null); // { plan, report }
  const [naming, setNaming] = useState(null); // { plan, mode: "rename" | "duplicate", name, description }
  const [viewing, setViewing] = useState(null); // plan detail incl. routes
  const [deleting, setDeleting] = useState(null);

  const fetchData = () =>
    Promise.all([getRoutePlans(), getRoutePlanAttention()])
      .then(([plansRes, attentionRes]) => { setPlans(plansRes.data); setAttention(attentionRes.data); pruneThumbnails(plansRes.data); })
      .catch(() => setNotice({ variant: "danger", text: "Failed to load route plans." }));

  useEffect(() => { fetchData(); }, []);
  useEffect(() => () => { fillCancelled.current = true; }, []); // leaving the page stops the address fill

  const fail = (text) => (err) => setNotice({ variant: "danger", text, items: errorList(err) });

  // Runs one request with the page locked, then reloads the list.
  const run = async (action, successText, failureText) => {
    setBusy(true);
    try {
      await action();
      await fetchData(); // list first, so the success message never sits above stale rows
      if (successText) setNotice({ variant: "success", text: successText });
      return true;
    } catch (err) {
      fail(failureText)(err);
      return false;
    } finally {
      setBusy(false);
    }
  };

  // Import creates the plan (inactive) and its new stops at once; addresses are then
  // looked up one stop per second while the popup shows progress.
  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNotice(null);
    setBusy(true);
    let res;
    try {
      res = await importRoutePlan(file);
      await fetchData();
    } catch (err) {
      fail(`"${file.name}" was not imported. Fix these and try again:`)(err);
      return;
    } finally {
      setBusy(false);
    }
    const created = res.data.stops?.created || [];
    const targets = created.filter(hasNoAddress);
    setImported({ name: res.data.name, routes: res.data.route_count, created: created.length, reused: res.data.stops?.reused ?? 0, done: 0, total: targets.length });
    fillCancelled.current = false;
    const started = await fillAddresses(targets, (done) => setImported((current) => current && { ...current, done }), () => fillCancelled.current);
    if (!started) setImported((current) => current && { ...current, total: 0, blocked: true });
  };

  const closeImported = () => {
    fillCancelled.current = true; // stops not reached keep "N/A"; "Fill from map" on the Stops page finishes them
    setImported(null);
  };

  const exportAs = (plan, format) =>
    exportRoutePlan(plan.id, format)
      .then((res) => downloadFile(`route_plan_${fileSlug(plan.name)}_${new Date().toISOString().slice(0, 10)}.${format}`, res.data))
      .catch(fail(`Could not export "${plan.name}".`));

  const openView = (plan) => getRoutePlan(plan.id).then((res) => setViewing(res.data)).catch(fail(`Could not open "${plan.name}".`));

  // The preview is the real switch-over run and rolled back, so it is redone whenever a bus pick changes.
  // While one runs the dialog is locked; if it fails, the previous picks and report stay and the admin is told,
  // so what Activate sends is always exactly what the dialog shows.
  const loadPreview = (plan, picks, previous = null) => {
    const seq = ++previewSeq.current;
    setPreviewing(true);
    if (!previous) setNotice({ variant: "info", text: `Preparing the activation preview for "${plan.name}"…` });
    const keepPrevious = (problem) => setActivating({ ...previous, problem });
    return previewRoutePlan(plan.id, picks)
      .then((res) => {
        if (seq !== previewSeq.current) return;
        if (!previous) setNotice(null);
        if (res.data.busy && previous) keepPrevious(res.data.errors[0]);
        else setActivating({ plan, picks, report: res.data });
      })
      .catch((err) => {
        if (seq !== previewSeq.current) return;
        if (previous) keepPrevious("The preview could not be updated, so that choice was not applied. Please pick it again.");
        else fail(`Could not preview "${plan.name}".`)(err);
      })
      .finally(() => { if (seq === previewSeq.current) setPreviewing(false); });
  };

  const openActivate = (plan) => loadPreview(plan, {});

  const pickBusRoute = (assignmentId, routeName) => {
    const picks = { ...activating.picks, [assignmentId]: routeName };
    if (!routeName) delete picks[assignmentId];
    loadPreview(activating.plan, picks, activating);
  };

  const confirmActivate = async (e) => {
    e.preventDefault();
    if (previewing) return; // Activate always sends the picks the finished preview showed
    const { plan, report, picks } = activating;
    if (report.errors.length) { setActivating(null); return; }
    const moved = report.moved_students.length;
    const done = await run(
      () => activateRoutePlan(plan.id, picks),
      `"${plan.name}" is now the active plan.${moved ? ` ${plural(moved, "student")} ${moved === 1 ? "was" : "were"} moved to the nearest new stop and notified.` : ""}`,
      `Could not activate "${plan.name}".`,
    );
    if (done) {
      setActivating(null);
      setActivations((n) => n + 1); // new routes have no road lines yet: build them now
    }
  };

  const submitName = async (e) => {
    e.preventDefault();
    const { plan, mode } = naming;
    const name = naming.name.trim();
    if (!name) return;
    const done = mode === "rename"
      ? await run(() => updateRoutePlan(plan.id, { name, description: naming.description }), `Plan "${name}" saved.`, "Could not save the plan.")
      : await run(() => duplicateRoutePlan(plan.id, name), `Saved "${name}" as a new plan.`, "Could not copy the plan.");
    if (done) setNaming(null);
  };

  const confirmDelete = () => {
    const plan = deleting;
    setDeleting(null);
    run(() => deleteRoutePlan(plan.id), `Plan "${plan.name}" deleted.`, `Could not delete "${plan.name}".`);
  };

  const activePlan = plans.find((plan) => plan.is_active);

  const attentionColumns = [
    { key: "roll_number", label: "Roll no." },
    { key: "name", label: "Student" },
    { key: "route", label: "Route", render: (row) => row.route || "Not assigned" },
    { key: "stop", label: "Stop" },
    { key: "reason", label: "Problem" },
  ];

  // A preview that fails returns only { errors }; fill the rest so the dialog can render.
  const report = activating && {
    routes: { created: [], updated: [], unchanged: 0, removed: [], archived: [] },
    stops: { created: [], reactivated: [], removed: 0, deactivated: 0 },
    buses: [], plan_routes: [], moved_students: [], affected_students: [], errors: [],
    ...activating.report,
  };

  return (
    <PageShell role="staff" title="Admin — Route Plans">
      <PageTitle sub="A route plan is a full set of routes, stops and ETAs. One plan is active for everyone; activate another to switch. To change the active plan, edit its routes on the Routes page.">
        Route Plans
      </PageTitle>

      {activations > 0 && <RoadLineBuilder key={activations} autoStart />}

      {notice && (
        <Banner variant={notice.variant}>
          {notice.text}
          {notice.items?.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 220, overflowY: "auto" }}>
              {notice.items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
            </ul>
          )}
        </Banner>
      )}

      {imported && (
        <FormModal
          title="Plan imported"
          sub={`"${imported.name}" is saved as an inactive plan. The live routes change only when you activate it.`}
          submitLabel="Done"
          onSubmit={(e) => { e.preventDefault(); closeImported(); }}
          onClose={closeImported}
          width="560px"
        >
          <div style={{ ...fullRow, gap: 14 }}>
            <p style={{ margin: 0, fontSize: 14 }}>
              <strong>{imported.routes}</strong> routes · <strong>{imported.created}</strong> new stops · <strong>{imported.reused}</strong> existing stops reused
            </p>
            <AddressProgress done={imported.done} total={imported.total} blocked={imported.blocked} />
          </div>
        </FormModal>
      )}

      {deleting && (
        <ConfirmModal
          title="Delete Plan?"
          message={`"${deleting.name}" will be removed from the stored plans. The live routes are not affected. Export it first if you may need it again.`}
          confirmLabel="Yes, Delete"
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        />
      )}

      {naming && (
        <FormModal
          title={naming.mode === "rename" ? "Rename Plan" : `Copy "${naming.plan.name}"`}
          sub={naming.mode === "rename" ? "Change the plan's name or description." : naming.plan.is_active ? "Saves the routes as they are right now as a new stored plan." : "Creates a second stored copy of this plan."}
          submitLabel={naming.mode === "rename" ? "Save" : "Save as New Plan"}
          loading={busy}
          onSubmit={submitName}
          onClose={() => setNaming(null)}
        >
          <Field label="Plan Name" required flex="1 1 100%">
            <input value={naming.name} maxLength={100} onChange={(e) => setNaming({ ...naming, name: e.target.value })} style={inputStyle} autoFocus />
          </Field>
          {naming.mode === "rename" && (
            <Field label="Description" flex="1 1 100%">
              <input value={naming.description} onChange={(e) => setNaming({ ...naming, description: e.target.value })} style={inputStyle} />
            </Field>
          )}
        </FormModal>
      )}

      {viewing && (
        <FormModal
          title={viewing.name}
          sub={`${plural(viewing.routes.length, "route")}${viewing.is_active ? " · active plan" : " · stored plan"}`}
          submitLabel="Close"
          onSubmit={(e) => { e.preventDefault(); setViewing(null); }}
          onClose={() => setViewing(null)}
          width="680px"
        >
          <div style={{ ...fullRow, gap: 8, maxHeight: 420, overflowY: "auto" }}>
            {viewing.routes.length === 0 && <span style={mutedText}>This plan has no routes.</span>}
            {viewing.routes.map((route) => (
              <details key={route.name} style={{ border: `1px solid ${colors.borderLight}`, borderRadius: 8, padding: "8px 12px" }}>
                <summary style={{ cursor: "pointer", fontSize: 13.5 }}>
                  <strong>{route.name}</strong> <span style={mutedText}>· {plural(route.stops.length, "stop")} · {route.status}</span>
                </summary>
                <ol style={{ margin: "8px 0 0", paddingLeft: 22, fontSize: 12.5, color: colors.textSecondary }}>
                  {route.stops.map((stop) => (
                    <li key={stop.name}>{stop.name} <span style={{ color: colors.textMuted }}>· AM {stop.morning_eta || "—"} · PM {stop.evening_eta || "—"}</span></li>
                  ))}
                </ol>
              </details>
            ))}
          </div>
        </FormModal>
      )}

      {activating && (
        <FormModal
          title={`Activate "${activating.plan.name}"?`}
          sub={`This replaces the routes everyone sees${activePlan ? `. The current plan "${activePlan.name}" is saved as it is now and can be activated again later` : ""}.`}
          submitLabel={report.errors.length ? "Close" : previewing ? "Updating preview…" : "Activate Plan"}
          loading={busy}
          onSubmit={confirmActivate}
          onClose={() => { if (!busy) setActivating(null); }}
          width="640px"
        >
          <div style={fullRow}>
            {activating.problem && <Banner variant="warning">{activating.problem}</Banner>}
            {report.errors.length > 0 && (
              <Banner variant="danger">
                This plan cannot be activated yet:
                <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{report.errors.map((item) => <li key={item}>{item}</li>)}</ul>
              </Banner>
            )}
            <p style={{ margin: 0, fontSize: 14 }}>
              Routes: <strong>{report.routes.created.length}</strong> new · <strong>{report.routes.updated.length}</strong> changed · <strong>{report.routes.unchanged}</strong> unchanged · <strong>{report.routes.removed.length}</strong> removed
              {report.stops.removed > 0 && <> · Stops: <strong>{report.stops.removed}</strong> no longer used are removed</>}
            </p>
            {report.buses.length > 0 && (
              <div>
                <strong style={{ fontSize: 13 }}>Buses on routes being removed ({report.buses.length})</strong>
                <p style={{ ...mutedText, margin: "4px 0 8px" }}>
                  Pick the new route for each bus. Its seated students move with it to the nearest stop on that route and keep their seats.
                  A bus left unassigned can be assigned later on the Assignments page; its students are queued for a seat on their nearest new route.
                </p>
                <div style={{ display: "grid", gap: 8 }}>
                  {report.buses.map((bus) => (
                    <label key={bus.assignment_id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
                      <span style={{ minWidth: 220 }}><strong>{bus.bus}</strong> · {bus.driver} <span style={mutedText}>(was on {bus.from_route})</span></span>
                      <select
                        value={activating.picks[bus.assignment_id] || ""}
                        disabled={busy || previewing}
                        onChange={(e) => pickBusRoute(bus.assignment_id, e.target.value)}
                        style={{ ...selectStyle, width: "auto", minWidth: 200, flex: "1 1 200px" }}
                      >
                        <option value="">Leave unassigned</option>
                        {report.plan_routes
                          .filter((route) => !bus.contractor || !route.contractor || route.contractor === bus.contractor)
                          .map((route) => <option key={route.name} value={route.name}>{route.name}</option>)}
                      </select>
                    </label>
                  ))}
                </div>
              </div>
            )}
            {report.moved_students.some((s) => s.far) && (
              <Banner variant="warning">
                Some students would be moved more than 1 km. Check them below; after activation they can be moved on Route Change Requests or Student Bus Assignments.
              </Banner>
            )}
            <NoteList
              title="Students moved to the nearest new stop (each is notified)"
              items={report.moved_students.map((s) =>
                `${s.far ? "⚠ " : ""}${s.roll_number} · ${s.name}: ${s.from_stop} → ${s.to_stop} on ${s.to_route} (${s.distance_m} m)` +
                (s.seat === "kept" ? " · keeps seat" : s.seat === "queued" ? " · queued for a seat" : ""))}
            />
            {report.affected_students.length > 0 && (
              <Banner variant="warning">
                {plural(report.affected_students.length, "registered student")} could not be given a stop on the new routes and will be listed under "Needs attention".
              </Banner>
            )}
            <NoteList title="Students without a stop" tone={colors.warningText} items={report.affected_students.map((s) => `${s.roll_number} · ${s.name}: ${s.reason}`)} />
            <NoteList title="New routes" items={report.routes.created} />
            <NoteList title="Changed routes" items={report.routes.updated} />
            <NoteList title="Routes removed" items={report.routes.removed} />
            <NoteList title="Routes kept as archived (older semesters' registrations still use them)" items={report.routes.archived} />
            <NoteList title="New stops to create" items={report.stops.created} />
            <NoteList title="Inactive stops to reactivate" items={report.stops.reactivated} />
          </div>
        </FormModal>
      )}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "12px 0", alignItems: "stretch" }}>
        <div style={group}>
          <span style={groupLabel}><Icon name="upload" /> Import plan</span>
          <button type="button" style={smallBtn} onClick={() => fileInput.current?.click()} disabled={busy}>
            <Icon name="file" size={14} /> {busy ? "Working…" : "Choose Excel, CSV or JSON file"}
          </button>
          <a href={`data:text/csv;charset=utf-8,${encodeURIComponent(SAMPLE_CSV)}`} download="route_plan_sample.csv" style={{ ...inline, ...mutedText }}>
            <Icon name="download" size={13} /> Sample CSV
          </a>
          <input ref={fileInput} type="file" accept=".xlsx,.csv,.json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json" hidden onChange={handleFile} />
        </div>
        {activePlan && (
          <div style={group}>
            <span style={groupLabel}><Icon name="plus" /> Current routes</span>
            <button type="button" style={smallBtn} disabled={busy} onClick={() => setNaming({ plan: activePlan, mode: "duplicate", name: `${activePlan.name} copy`, description: activePlan.description })}>
              Save as a new plan
            </button>
          </div>
        )}
      </div>

      {plans.length === 0 && <p style={mutedText}>No route plans yet.</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))", gap: 16, alignItems: "stretch" }}>
        {plans.map((plan) => (
          <PlanCard
            key={`${plan.id}-${plan.fingerprint}`}
            plan={plan}
            busy={busy}
            onActivate={() => openActivate(plan)}
            onView={() => openView(plan)}
            onExport={(format) => exportAs(plan, format)}
            onCopy={() => setNaming({ plan, mode: "duplicate", name: `${plan.name} copy`, description: plan.description })}
            onRename={() => setNaming({ plan, mode: "rename", name: plan.name, description: plan.description })}
            onDelete={() => setDeleting(plan)}
          />
        ))}
      </div>

      {attention.length > 0 && (
        <SectionBlock
          title={`Needs attention (${attention.length})`}
          sub="These students are registered on a route or stop that is not being served. Move them from Route Change Requests or Student Bus Assignments."
          style={{ marginTop: 28 }}
        >
          <Table columns={attentionColumns} rows={attention.map((row) => ({ ...row, id: row.registration_id }))} />
          <p style={{ ...mutedText, marginTop: 8 }}>
            <Link to="/admin/routechangerequests" style={{ color: colors.accent }}>Open Route Change Requests</Link>
            {" · "}
            <Link to="/admin/student-bus-assignments" style={{ color: colors.accent }}>Open Student Bus Assignments</Link>
          </p>
        </SectionBlock>
      )}
    </PageShell>
  );
}

export default RoutePlansPage;
