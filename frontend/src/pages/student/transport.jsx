import { useEffect, useState } from "react";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Pill, Banner, DetailRow } from "../../components/ui";
import { colors, fonts } from "../../theme";
import { getDashboard } from "../../services/transportService";

function StudentTransport() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const pendingMsg = "Fees paid; Admin will assign seats shortly.";
  const unpaidMsg  = "Registration submitted. Please pay transport fee to proceed.";

  useEffect(() => {
    getDashboard()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load transport data."));
  }, []);

  if (error) return <PageShell role="student" title="My Transport"><Banner variant="danger">{error}</Banner></PageShell>;
  if (!data)  return <PageShell role="student" title="My Transport"><Spinner /></PageShell>;

  const { profile, active_registration, seat, waitlist_position, fee_summary } = data;
  const normStatus = (active_registration?.status || "").toLowerCase();
  const hasSubmittedFee = Boolean(active_registration?.fee_submitted);
  const shouldShowPending = !seat && hasSubmittedFee && ["pending", "approved", "payment_submitted"].includes(normStatus);
  const displayStatus = shouldShowPending ? pendingMsg : active_registration?.status;
  const hasFullAssignment = Boolean(profile && seat && active_registration?.route && active_registration?.bus);

  return (
    <PageShell role="student" title="My Transport">
      <PageTitle sub="Your current semester transport details.">My Transport</PageTitle>

      {/* Registration */}
      <ContentCard>
        <h3 style={sectionH}>Current Semester Registration</h3>
        {active_registration ? (
          <>
            <DetailRow label="Semester" value={active_registration.semester} />
            <DetailRow label="Bus"      value={active_registration.bus || "Pending assignment"} />
            <DetailRow label="Route"    value={active_registration.route} />
            <DetailRow label="Stop"     value={active_registration.stop} />
            <DetailRow label="Status"   value={
              <Pill
                label={displayStatus}
                variant={normStatus === "approved" ? "success" : normStatus === "rejected" ? "danger" : "warning"}
              />
            } />
            {!seat && !waitlist_position && !hasSubmittedFee && (
              <Banner variant="warning" style={{ marginTop: "12px" }}>{unpaidMsg}</Banner>
            )}
            {seat && <DetailRow label="Seat Number" value={`#${seat.seat_number}`} />}
            {waitlist_position && <DetailRow label="Waitlist Position" value={`#${waitlist_position}`} />}
            {hasFullAssignment && (
              <>
                <div style={{ borderTop: `1px solid ${colors.borderLight}`, margin: "14px 0" }} />
                <h4 style={{ ...sectionH, fontSize: "13px", marginBottom: "8px" }}>Student Details</h4>
                <DetailRow label="Full Name" value={(() => {
                  const name = `${profile.first_name || ""} ${profile.last_name || ""}`.trim();
                  return name || "—";
                })()} />
                <DetailRow label="Roll No"    value={profile.roll_number} />
                <DetailRow label="Department" value={profile.department} />
                <DetailRow label="Batch"      value={profile.batch} />
              </>
            )}
          </>
        ) : (
          <p style={{ margin: 0, color: colors.textSecondary, fontSize: "13.5px" }}>{unpaidMsg}</p>
        )}
      </ContentCard>

      {/* Fee Summary */}
      <ContentCard>
        <h3 style={sectionH}>Fee Summary</h3>
        {fee_summary?.length > 0 ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13.5px" }}>
              <thead>
                <tr style={{ background: colors.tableHeaderBg }}>
                  {["Semester", "Amount", "Challan #", "Verified"].map(h => (
                    <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontWeight: "700", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.06em", color: colors.textSecondary, borderBottom: `1px solid ${colors.borderLight}` }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fee_summary.map((f, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${colors.tableRowBorder}` }}>
                    <td style={{ padding: "10px 14px" }}>{f.semester}</td>
                    <td style={{ padding: "10px 14px" }}>Rs. {f.amount}</td>
                    <td style={{ padding: "10px 14px" }}>{f.challan_number}</td>
                    <td style={{ padding: "10px 14px" }}>
                      <Pill label={f.is_verified ? "Verified" : "Pending"} variant={f.is_verified ? "success" : "warning"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ margin: 0, color: colors.textMuted, fontSize: "13.5px" }}>No fee records found.</p>
        )}
      </ContentCard>
    </PageShell>
  );
}

const sectionH = { margin: "0 0 12px", fontSize: "15px", fontWeight: "700", color: colors.textPrimary, fontFamily: fonts.heading };

export default StudentTransport;