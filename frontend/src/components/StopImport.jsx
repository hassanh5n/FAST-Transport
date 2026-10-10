// Bulk stop import (CSV/JSON) + address filling, shared by the Stops page and Route Builder.
// The server creates the stops instantly; addresses are then looked up from the map one per
// second (the free geocoder's limit) and saved onto each stop.
import { useEffect, useRef, useState } from "react";
import { FormModal, Banner } from "./ui";
import { btn, colors } from "../theme";
import { importStops, resolveMapLocation, updateStop } from "../services/transportService";

const SAMPLE_CSV = "name,latitude,longitude,address\nGulshan Chowrangi,24.921500,67.084700,\n";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const hasNoAddress = (stop) => !stop.address || stop.address.trim() === "" || stop.address === "N/A";

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
  const smallBtn = { ...btn.ghost, fontSize: 13, flex: "1 1 auto" };

  return (
    <>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <button type="button" style={smallBtn} onClick={() => fileInput.current?.click()} disabled={uploading}>
          {uploading ? "Importing…" : "Import CSV/JSON"}
        </button>
        {missing.length > 0 && !filling && (
          <button type="button" style={smallBtn} onClick={() => { setOpen(true); setReport(null); setError(""); runFill(missing); }}>
            Fill {missing.length} missing address{missing.length === 1 ? "" : "es"}
          </button>
        )}
        <a href={sampleHref} download="stops_sample.csv" style={{ fontSize: 12, color: colors.textSecondary }}>
          Download sample CSV
        </a>
        <input ref={fileInput} type="file" accept=".csv,.json,text/csv,application/json" hidden onChange={handleFile} />
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
