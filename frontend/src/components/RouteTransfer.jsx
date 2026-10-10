// Route import/export (CSV/JSON): a route's ID and details plus its ordered stops and their ETAs.
// Export is always available. Import shows only when `onImport` is given (the route builder):
// it matches the file's stops to existing ones, creates any that are new, and hands the ordered
// list to the builder, which saves nothing until the admin publishes.
import { useRef, useState } from "react";
import { FormModal, Banner } from "./ui";
import Icon from "./Icon";
import { btn, colors } from "../theme";
import { createStop, getStops } from "../services/transportService";
import { downloadFile, parseRouteFile, planRouteImport, routeExport } from "../utils/transferFiles";

const fileSlug = (name) => String(name || "route").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "route";

function NoteList({ title, items, tone }) {
  if (!items.length) return null;
  return (
    <div style={{ width: "100%", textAlign: "left" }}>
      <strong style={{ fontSize: 13, color: tone }}>{title} ({items.length})</strong>
      <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 140, overflowY: "auto", fontSize: 12.5, color: colors.textSecondary }}>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

export default function RouteTransfer({ route, stops, onImport }) {
  const fileInput = useRef(null);
  const [plan, setPlan] = useState(null); // result of planRouteImport, shown for confirmation
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [applying, setApplying] = useState(false);

  const exportAs = (format) => downloadFile(`route_${route.id ?? "new"}_${fileSlug(route.name)}_${new Date().toISOString().slice(0, 10)}.${format}`, routeExport(route, stops, format));

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    setPlan(null);
    setReading(true);
    try {
      const { rows, firstRow, source } = parseRouteFile(file.name, await file.text());
      const existing = await getStops();
      setPlan({ ...planRouteImport(rows, firstRow, existing.data?.results || existing.data || []), source });
    } catch (err) {
      setError(err.response ? "Could not load the existing stops. Please try again." : err.message);
    } finally {
      setReading(false);
    }
  };

  const close = () => { if (!applying) { setPlan(null); setError(""); } };

  const apply = async (e) => {
    e.preventDefault();
    if (!plan?.stops.length) { close(); return; }
    setApplying(true);
    setError("");
    const imported = [];
    try {
      for (const item of plan.stops) {
        // Created one at a time so a failure names the stop it stopped at.
        const stop = item.existing || (await createStop(item.create)).data;
        imported.push({ ...stop, morning_eta: item.morning_eta, evening_eta: item.evening_eta });
      }
      onImport(imported);
      setPlan(null);
    } catch (err) {
      const failed = plan.stops[imported.length]?.name;
      const detail = err.response?.data && typeof err.response.data === "object" ? Object.values(err.response.data).flat().join(" ") : err.message;
      setError(`Could not create the stop "${failed}": ${detail} The route was not changed. Stops created before it were kept; choosing the file again will reuse them.`);
    } finally {
      setApplying(false);
    }
  };

  const inline = { display: "inline-flex", alignItems: "center", gap: 6 };
  const smallBtn = { ...btn.ghost, ...inline, padding: "7px 12px", fontSize: 13, background: "#fff" };
  const group = { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: colors.tableHeaderBg };
  const groupLabel = { ...inline, fontSize: 13, fontWeight: 700, color: colors.textPrimary };

  const toCreate = plan ? plan.stops.filter((item) => item.create) : [];
  const fromOtherRoute = plan && plan.source.id != null && route.id != null && String(plan.source.id) !== String(route.id);

  return (
    <>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16, alignItems: "stretch" }}>
        {onImport && (
          <div style={group}>
            <span style={groupLabel}><Icon name="upload" /> Import route</span>
            <button type="button" style={smallBtn} onClick={() => fileInput.current?.click()} disabled={reading}>
              <Icon name="file" size={14} /> {reading ? "Reading file…" : "Choose CSV or JSON file"}
            </button>
            <input ref={fileInput} type="file" accept=".csv,.json,text/csv,application/json" hidden onChange={handleFile} />
          </div>
        )}
        <div style={group}>
          <span style={groupLabel}><Icon name="download" /> Export route ID {route.id} ({stops.length} stop{stops.length === 1 ? "" : "s"})</span>
          <button type="button" style={smallBtn} onClick={() => exportAs("csv")}>CSV</button>
          <button type="button" style={smallBtn} onClick={() => exportAs("json")}>JSON</button>
        </div>
      </div>
      {error && !plan && <Banner variant="danger">{error}</Banner>}

      {plan && (
        <FormModal
          title="Import route stops"
          sub="This replaces the stop list and ETAs shown on this page with the file's. The route itself is not saved until you click Save & Publish Route."
          submitLabel={plan.stops.length ? `Load ${plan.stops.length} stop${plan.stops.length === 1 ? "" : "s"}` : "Close"}
          loading={applying}
          onSubmit={apply}
          onClose={close}
          width="620px"
        >
          <div style={{ display: "grid", gap: 14, width: "100%", textAlign: "left" }}>
            {error && <Banner variant="danger">{error}</Banner>}
            {fromOtherRoute && (
              <Banner variant="warning">
                This file was exported from a different route: ID {plan.source.id}{plan.source.name ? ` (${plan.source.name})` : ""}. You are importing into route ID {route.id} ({route.name}).
              </Banner>
            )}
            {plan.stops.length === 0 && <Banner variant="warning">No usable stops were found in this file.</Banner>}
            <p style={{ margin: 0, fontSize: 14 }}>
              <strong>{plan.stops.length - toCreate.length}</strong> existing · <strong>{toCreate.length}</strong> new · <strong>{plan.skipped.length}</strong> skipped
            </p>
            {toCreate.length > 0 && (
              <Banner variant="info">
                The new stops below do not exist yet. They are created as soon as you click Load, and stay even if you never publish this route.
              </Banner>
            )}
            <NoteList title="New stops to create" items={toCreate.map((item) => `${item.name} (${item.create.latitude}, ${item.create.longitude})`)} tone={colors.textPrimary} />
            <NoteList title="Skipped rows" items={plan.skipped.map((item) => `Row ${item.row}${item.name ? ` · ${item.name}` : ""}: ${item.reason}`)} tone={colors.dangerText} />
            <NoteList title="ETAs left blank" items={plan.warnings} tone={colors.warningText} />
          </div>
        </FormModal>
      )}
    </>
  );
}
