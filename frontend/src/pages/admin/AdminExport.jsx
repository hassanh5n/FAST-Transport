import { useEffect, useState } from "react";
import PageShell, { PageTitle } from "../../components/PageShell";
import { Spinner, Banner } from "../../components/ui";
import { btn, colors, fonts, radius } from "../../theme";
import { getSemesters } from "../../services/transportService";
import api from "../../services/api";

// ── CSV helper ────────────────────────────────────────────────────────────────
function downloadCSV(filename, rows) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const escape  = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv     = [headers.join(","), ...rows.map(r => headers.map(h => escape(r[h])).join(","))].join("\n");
  const blob    = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url     = URL.createObjectURL(blob);
  const a       = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Export card ───────────────────────────────────────────────────────────────
function ExportCard({ title, description, icon, onExport, loading }) {
  return (
    <div style={{
      background: "#fff", border: `1px solid ${colors.borderLight}`,
      borderRadius: radius.lg, padding: "24px",
      boxShadow: "0 1px 3px rgba(11,45,66,0.06)",
    }}>
      <div style={{ display: "flex", gap: "16px", alignItems: "flex-start", marginBottom: "16px" }}>
        <div style={{
          width: "44px", height: "44px", borderRadius: "10px",
          background: colors.infoBg, border: `1px solid rgba(40,141,196,0.2)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: colors.accent, fontSize: "20px", flexShrink: 0,
        }}>
          {icon}
        </div>
        <div>
          <h3 style={{ margin: "0 0 4px", fontSize: "15px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading }}>{title}</h3>
          <p style={{ margin: 0, fontSize: "13px", color: colors.textSecondary, lineHeight: 1.5 }}>{description}</p>
        </div>
      </div>
      <button
        onClick={onExport}
        disabled={loading}
        style={{ ...btn.primary, display: "flex", alignItems: "center", gap: "8px", opacity: loading ? 0.6 : 1 }}
      >
        {loading ? "Preparing…" : (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download CSV
          </>
        )}
      </button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
function AdminExportPage() {
  const [semesters, setSemesters]           = useState([]);
  const [selectedSemester, setSelectedSemester] = useState("");
  const [loadingKey, setLoadingKey]         = useState(null);
  const [error, setError]                   = useState("");

  useEffect(() => {
    getSemesters()
      .then(r => {
        setSemesters(r.data);
        const active = r.data.find(s => s.is_active);
        if (active) setSelectedSemester(String(active.id));
      })
      .catch(() => setError("Failed to load semesters."));
  }, []);

  const withLoading = async (key, fn) => {
    setLoadingKey(key); setError("");
    try { await fn(); }
    catch { setError("Export failed. Please try again."); }
    finally { setLoadingKey(null); }
  };

  // ── Export: all students ──────────────────────────────────────────────────
  const exportAllStudents = () => withLoading("students", async () => {
    const res  = await api.get("/api/students/");
    const rows = res.data.map(s => ({
      "Roll Number":  s.roll_number,
      "Username":     s.user?.username,
      "Email":        s.user?.email,
      "Department":   s.department,
      "Batch":        s.batch,
      "Phone":        s.phone,
      "Address":      s.address,
      "Joined":       s.created_at?.slice(0, 10),
    }));
    downloadCSV("students_all.csv", rows);
  });

  // ── Export: semester registrations ────────────────────────────────────────
  const exportRegistrations = () => withLoading("registrations", async () => {
    if (!selectedSemester) { setError("Please select a semester first."); return; }
    const res  = await api.get(`/api/semester-registrations/?semester=${selectedSemester}`);
    const rows = (res.data.results ?? res.data).map(r => ({
      "Roll Number":  r.student?.roll_number,
      "Student":      r.student?.user?.username,
      "Email":        r.student?.user?.email,
      "Department":   r.student?.department,
      "Semester":     r.semester?.name,
      "Route":        r.route?.name,
      "Stop":         r.stop?.name,
      "Status":       r.status,
      "Registered At": r.registered_at?.slice(0, 10),
    }));
    const semName = semesters.find(s => String(s.id) === selectedSemester)?.name || selectedSemester;
    downloadCSV(`registrations_${semName.replace(/\s+/g, "_")}.csv`, rows);
  });

  // ── Export: fee verifications ─────────────────────────────────────────────
  const exportFees = () => withLoading("fees", async () => {
    if (!selectedSemester) { setError("Please select a semester first."); return; }
    const res  = await api.get("/api/fee-verifications/list/");
    const rows = res.data
      .filter(f => !selectedSemester || String(f.semester_id) === selectedSemester)
      .map(f => ({
        "Roll Number":    f.roll_number,
        "Student":        f.student_name,
        "Semester":       f.semester,
        "Challan Number": f.challan_number,
        "Amount (PKR)":   f.amount,
        "Verified":       f.is_verified ? "Yes" : "No",
      }));
    const semName = semesters.find(s => String(s.id) === selectedSemester)?.name || selectedSemester;
    downloadCSV(`fees_${semName.replace(/\s+/g, "_")}.csv`, rows);
  });

  // ── Export: seat allocations ──────────────────────────────────────────────
  const exportSeats = () => withLoading("seats", async () => {
    if (!selectedSemester) { setError("Please select a semester first."); return; }
    const res  = await api.get("/api/seat-allocations/current-allocations/");
    const rows = (res.data ?? [])
      .filter(r => !selectedSemester || String(r.semester_id) === selectedSemester)
      .map(r => ({
        "Roll Number":  r.roll_number,
        "Student":      r.student_name,
        "Semester":     r.semester,
        "Route":        r.route,
        "Stop":         r.stop,
        "Bus":          r.current_bus,
        "Seat Number":  r.current_seat_number,
      }));
    const semName = semesters.find(s => String(s.id) === selectedSemester)?.name || selectedSemester;
    downloadCSV(`seat_allocations_${semName.replace(/\s+/g, "_")}.csv`, rows);
  });

  // ── Export: complaints ────────────────────────────────────────────────────
  const exportComplaints = () => withLoading("complaints", async () => {
    const res  = await api.get("/api/complaints/");
    const rows = res.data.map(c => ({
      "Student":      c.submitted_by?.username,
      "Subject":      c.subject,
      "Category":     c.category,
      "Priority":     c.priority,
      "Status":       c.status,
      "Description":  c.description,
      "Admin Response": c.admin_response !== "N/A" ? c.admin_response : "",
      "Submitted":    c.created_at?.slice(0, 10),
      "Resolved":     c.resolved_at?.slice(0, 10) || "",
    }));
    downloadCSV("complaints_all.csv", rows);
  });

  const semesterExports = [
    { key: "registrations", title: "Semester Registrations",   description: "All student transport registrations for the selected semester with route, stop, and status.",          icon: "📋", fn: exportRegistrations },
    { key: "fees",          title: "Fee Verifications",         description: "Fee payment and challan records for the selected semester.",                                            icon: "💳", fn: exportFees          },
    { key: "seats",         title: "Seat Allocations",          description: "Final seat assignments per bus for the selected semester.",                                             icon: "🎫", fn: exportSeats         },
  ];

  const globalExports = [
    { key: "students",   title: "All Students",  description: "Complete student directory with contact details, department, and batch.", icon: "👥", fn: exportAllStudents },
    { key: "complaints", title: "All Complaints", description: "Full complaint history with admin responses and resolution status.",      icon: "💬", fn: exportComplaints  },
  ];

  return (
    <PageShell role="staff" title="Admin — Export Data">
      <PageTitle sub="Download records as CSV files for use in Excel or university ERP systems.">
        Export Data
      </PageTitle>

      {error && <Banner variant="danger" style={{ marginBottom: "20px" }}>{error}</Banner>}

      <div style={{ background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, padding: "20px 24px", marginBottom: "28px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)" }}>
        <p style={{ margin: "0 0 10px", fontSize: "13px", fontWeight: "600", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Semester for filtered exports
        </p>
        <select
          value={selectedSemester}
          onChange={e => setSelectedSemester(e.target.value)}
          style={{ padding: "9px 13px", borderRadius: radius.md, border: `1px solid ${colors.borderMid}`, fontSize: "14px", color: colors.textPrimary, background: "#fff", minWidth: "220px" }}
        >
          <option value="">All semesters</option>
          {semesters.map(s => (
            <option key={s.id} value={s.id}>{s.name} {s.is_active ? "(Active)" : ""}</option>
          ))}
        </select>
      </div>

      <h3 style={{ margin: "0 0 14px", fontSize: "14px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading }}>
        Semester Reports
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "14px", marginBottom: "28px" }}>
        {semesterExports.map(e => (
          <ExportCard key={e.key} title={e.title} description={e.description} icon={e.icon}
            onExport={e.fn} loading={loadingKey === e.key} />
        ))}
      </div>

      <h3 style={{ margin: "0 0 14px", fontSize: "14px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading }}>
        Full Records
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "14px" }}>
        {globalExports.map(e => (
          <ExportCard key={e.key} title={e.title} description={e.description} icon={e.icon}
            onExport={e.fn} loading={loadingKey === e.key} />
        ))}
      </div>
    </PageShell>
  );
}

export default AdminExportPage;