// Bulk stop import/export (CSV/JSON) + address filling, used by the Stops page.
// The server creates the stops instantly; addresses are then looked up from the map one per
// second (the free geocoder's limit) and saved onto each stop.
import { useEffect, useRef, useState } from "react";
import { FormModal, Banner } from "./ui";
import Icon from "./Icon";
import { btn, colors } from "../theme";
import { importStops, resolveMapLocation, updateStop } from "../services/transportService";
import { downloadFile, toCsv } from "../utils/transferFiles";

const SAMPLE_CSV = "name,latitude,longitude,address\nGulshan Chowrangi,24.921500,67.084700,\n";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const hasNoAddress = (stop) => !stop.address || stop.address.trim() === "" || stop.address === "N/A";

// Same columns the import accepts, so an exported file can be imported back as-is.
const EXPORT_COLUMNS = ["name", "latitude", "longitude", "address", "is_active", "location_accuracy_m", "provider_place_id"];
function exportStops(stops, format) {
  const rows = stops.map((stop) => Object.fromEntries(EXPORT_COLUMNS.map((column) => [
    column,
    column === "address" && hasNoAddress(stop) ? "" : stop[column] ?? (column === "is_active" ? true : null),
  ])));
  downloadFile(`stops_${new Date().toISOString().slice(0, 10)}.${format}`, format === "json" ? JSON.stringify(rows, null, 2) : toCsv(EXPORT_COLUMNS, rows));
}

async function fillAddresses(stops, onProgress, isCancelled) {
  for (let i = 0; i < stops.length; i += 1) {
    if (isCancelled()) return;
    const stop = stops[i];
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const res = await resolveMapLocation({ action: "reverse", latitude: Number(stop.latitude), longitude: Number(stop.longitude) });
        const label = res.data.results?.[0]?.label;
        if (label) await updateStop(stop.id, { address: label });
        if (!res.data.cached) await sleep(1100);
        break;
      } catch (err) {
        if (err.response?.status !== 429) break; // outside Karachi / service down: keep "N/A"
        await sleep(1100);
      }
    }
    onProgress(i + 1);
  }
}

function ReportList({ title, items, tone }) {
  if (!items.length) return null;
  return (
    <div style={{ width: "100%", textAlign: "left" }}>
      <strong style={{ fontSize: 13, color: tone }}>{title} ({items.length})</strong>
      <ul style={{ margin: "6px 0 0", paddingLeft: 18, maxHeight: 160, overflowY: "auto", fontSize: 12.5, color: colors.textSecondary }}>
        {items.map((item) => (
          <li key={`${title}-${item.row}`}>Row {item.row}{item.name ? ` · ${item.name}` : ""}: {item.reason}</li>
        ))}
      </ul>
    </div>
  );
}

export default function StopImport({ stops = [], onChanged }) {
  const fileInput = useRef(null);
  const cancelled = useRef(false);
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);
  const [progress, setProgress] = useState(null); // { done, total } while filling addresses

  useEffect(() => () => { cancelled.current = true; }, []);

  const missing = stops.filter(hasNoAddress);
  const filling = progress && progress.done < progress.total;

  const runFill = async (targets) => {
    if (!targets.length) return;
    cancelled.current = false;
    setProgress({ done: 0, total: targets.length });
    await fillAddresses(targets, (done) => setProgress({ done, total: targets.length }), () => cancelled.current);
    onChanged?.();
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setOpen(true);
    setError("");
    setReport(null);
    setProgress(null);
    setUploading(true);
    try {
      const res = await importStops(file);
      setReport(res.data);
      onChanged?.();
      runFill(res.data.created.filter(hasNoAddress));
    } catch (err) {
      setError(err.response?.data?.file || err.response?.data?.detail || "Import failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const close = () => {
    cancelled.current = true; // remaining stops keep "N/A"; "Fill missing addresses" resumes later
    setOpen(false);
  };

  const sampleHref = `data:text/csv;charset=utf-8,${encodeURIComponent(SAMPLE_CSV)}`;
  const inline = { display: "inline-flex", alignItems: "center", gap: 6 };
  const smallBtn = { ...btn.ghost, ...inline, padding: "7px 12px", fontSize: 13, background: "#fff" };
  const group = { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: colors.tableHeaderBg };
  const groupLabel = { ...inline, fontSize: 13, fontWeight: 700, color: colors.textPrimary };

  return (
    <>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12, alignItems: "stretch" }}>
        <div style={group}>
          <span style={groupLabel}><Icon name="upload" /> Import stops</span>
          <button type="button" style={smallBtn} onClick={() => fileInput.current?.click()} disabled={uploading}>
            <Icon name="file" size={14} /> {uploading ? "Importing…" : "Choose CSV or JSON file"}
          </button>
          <a href={sampleHref} download="stops_sample.csv" style={{ ...inline, fontSize: 12, color: colors.textSecondary }}>
            <Icon name="download" size={13} /> Sample CSV
          </a>
          <input ref={fileInput} type="file" accept=".csv,.json,text/csv,application/json" hidden onChange={handleFile} />
        </div>
        <div style={group}>
          <span style={groupLabel}><Icon name="download" /> Export {stops.length} stop{stops.length === 1 ? "" : "s"}</span>
          <button type="button" style={smallBtn} onClick={() => exportStops(stops, "csv")} disabled={stops.length === 0}>CSV</button>
          <button type="button" style={smallBtn} onClick={() => exportStops(stops, "json")} disabled={stops.length === 0}>JSON</button>
        </div>
        {missing.length > 0 && !filling && (
          <div style={{ ...group, background: colors.warningBg, borderColor: "rgba(245,158,11,0.25)" }}>
            <span style={{ ...groupLabel, color: colors.warningText }}><Icon name="pin" /> {missing.length} without an address</span>
            <button type="button" style={smallBtn} onClick={() => { setOpen(true); setReport(null); setError(""); runFill(missing); }}>
              Fill from map
            </button>
          </div>
        )}
      </div>

      {open && (
        <FormModal
          title="Import stops"
          sub="Stops that already exist (same name, or within 25 m) are skipped."
          submitLabel="Done"
          onSubmit={(e) => { e.preventDefault(); close(); }}
          onClose={close}
          width="620px"
        >
          <div style={{ display: "grid", gap: 14, width: "100%", textAlign: "left" }}>
            {uploading && <p style={{ margin: 0, fontSize: 13 }}>Reading file and creating stops…</p>}
            {error && <Banner variant="warning">{String(error)}</Banner>}
            {report && (
              <>
                <p style={{ margin: 0, fontSize: 14 }}>
                  <strong>{report.created.length}</strong> created · <strong>{report.skipped.length}</strong> skipped · <strong>{report.invalid.length}</strong> invalid
                </p>
                {report.ignored_columns.length > 0 && (
                  <p style={{ margin: 0, fontSize: 12.5, color: colors.textSecondary }}>
                    Ignored columns (not part of a stop): {report.ignored_columns.join(", ")}
                  </p>
                )}
                <ReportList title="Skipped" items={report.skipped} tone={colors.textPrimary} />
                <ReportList title="Invalid" items={report.invalid} tone={colors.dangerText} />
              </>
            )}
            {progress && (
              <div>
                <p style={{ margin: "0 0 6px", fontSize: 13 }}>
                  {filling
                    ? `Fetching addresses… ${progress.done} / ${progress.total}`
                    : `Addresses done (${progress.total}). Any the map couldn't find stay "N/A" and can be edited.`}
                </p>
                <div style={{ height: 6, borderRadius: 99, background: colors.borderLight, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${(progress.done / progress.total) * 100}%`, background: colors.accent, transition: "width 0.3s" }} />
                </div>
                {filling && (
                  <p style={{ margin: "6px 0 0", fontSize: 12, color: colors.textSecondary }}>
                    The stops are already saved. You can close this; use "Fill missing addresses" later to finish.
                  </p>
                )}
              </div>
            )}
          </div>
        </FormModal>
      )}
    </>
  );
}
