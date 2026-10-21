// CSV import/export bar shared by the Buses and Drivers pages.
// The server creates the valid rows and reports duplicates and invalid rows by row number.
import { useRef, useState } from "react";
import { FormModal, Banner } from "./ui";
import Icon from "./Icon";
import { btn, colors } from "../theme";
import { downloadFile, toCsv } from "../utils/transferFiles";

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

/**
 * kind:        "bus" / "driver" (singular, used in labels and file names)
 * records:     rows currently shown on the page (what Export downloads)
 * columns:     CSV header, identical for import and export so an export imports back as-is
 * toRow:       record -> {column: value} for export
 * sampleCsv:   small example file offered as a download
 * importFile:  (File) => axios promise returning the import report
 * duplicateNote: one line shown in the report modal explaining the duplicate rule
 */
export default function FleetImport({ kind, records, columns, toRow, sampleCsv, importFile, duplicateNote, onChanged }) {
  const fileInput = useRef(null);
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);
  const plural = kind === "bus" ? "buses" : `${kind}s`;

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setOpen(true);
    setError("");
    setReport(null);
    setUploading(true);
    try {
      const res = await importFile(file);
      setReport(res.data);
      onChanged?.();
    } catch (err) {
      setError(err.response?.data?.file || err.response?.data?.detail || "Import failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const exportCsv = () =>
    downloadFile(`${plural}_${new Date().toISOString().slice(0, 10)}.csv`, toCsv(columns, records.map(toRow)));

  const sampleHref = `data:text/csv;charset=utf-8,${encodeURIComponent(sampleCsv)}`;
  const inline = { display: "inline-flex", alignItems: "center", gap: 6 };
  const smallBtn = { ...btn.ghost, ...inline, padding: "7px 12px", fontSize: 13, background: "#fff" };
  const group = { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "8px 12px", border: `1px solid ${colors.borderLight}`, borderRadius: 10, background: colors.tableHeaderBg };
  const groupLabel = { ...inline, fontSize: 13, fontWeight: 700, color: colors.textPrimary };

  return (
    <>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12, alignItems: "stretch" }}>
        <div style={group}>
          <span style={groupLabel}><Icon name="upload" /> Import {plural}</span>
          <button type="button" style={smallBtn} onClick={() => fileInput.current?.click()} disabled={uploading}>
            <Icon name="file" size={14} /> {uploading ? "Importing…" : "Choose CSV file"}
          </button>
          <a href={sampleHref} download={`${plural}_sample.csv`} style={{ ...inline, fontSize: 12, color: colors.textSecondary }}>
            <Icon name="download" size={13} /> Sample CSV
          </a>
          <input ref={fileInput} type="file" accept=".csv,text/csv" hidden onChange={handleFile} />
        </div>
        <div style={group}>
          <span style={groupLabel}><Icon name="download" /> Export {records.length} {records.length === 1 ? kind : plural}</span>
          <button type="button" style={smallBtn} onClick={exportCsv} disabled={records.length === 0}>CSV</button>
        </div>
      </div>

      {open && (
        <FormModal
          title={`Import ${plural}`}
          sub={duplicateNote}
          submitLabel="Done"
          onSubmit={(e) => { e.preventDefault(); setOpen(false); }}
          onClose={() => setOpen(false)}
          width="620px"
        >
          <div style={{ display: "grid", gap: 14, width: "100%", textAlign: "left" }}>
            {uploading && <p style={{ margin: 0, fontSize: 13 }}>Reading file and creating {plural}…</p>}
            {error && <Banner variant="warning">{String(error)}</Banner>}
            {report && (
              <>
                <p style={{ margin: 0, fontSize: 14 }}>
                  <strong>{report.created.length}</strong> created · <strong>{report.skipped.length}</strong> duplicates skipped · <strong>{report.invalid.length}</strong> invalid
                </p>
                {report.ignored_columns.length > 0 && (
                  <p style={{ margin: 0, fontSize: 12.5, color: colors.textSecondary }}>
                    Ignored columns: {report.ignored_columns.join(", ")}
                  </p>
                )}
                <ReportList title="Duplicates skipped" items={report.skipped} tone={colors.textPrimary} />
                <ReportList title="Invalid" items={report.invalid} tone={colors.dangerText} />
              </>
            )}
          </div>
        </FormModal>
      )}
    </>
  );
}
