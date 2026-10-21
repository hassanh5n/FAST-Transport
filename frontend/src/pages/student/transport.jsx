import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Pill, Banner, DetailRow, ConfirmModal } from "../../components/ui";
import { btn, colors, fonts } from "../../theme";
import {
  getDashboard,
  getWaitlistStatus,
  cancelRegistration,
} from "../../services/transportService";

// Time left on a seat-offer deadline. A held seat is not open-ended, so the
// student needs to see the clock, not just a status word. Kept as a pure
// function so it can be called after the loading guards below without
// breaking hook ordering.
function formatCountdown(deadline, now) {
  if (!deadline) return null;
  const remaining = new Date(deadline).getTime() - now;
  if (remaining <= 0) return { expired: true, label: "expired" };
  const hours = Math.floor(remaining / 3600000);
  const minutes = Math.floor((remaining % 3600000) / 60000);
  return {
    expired: false,
    label: hours >= 1 ? `${hours}h ${minutes}m` : `${minutes}m`,
  };
}

function StudentTransport() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [queue, setQueue] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const pendingMsg = "Fees paid; Admin will assign seats shortly.";
  const unpaidMsg  = "Registration submitted. Please pay transport fee to proceed.";

  const load = () => {
    getDashboard()
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load transport data."));
    getWaitlistStatus()
      .then((res) => setQueue(res.data))
      .catch(() => setQueue(null));
  };

  useEffect(() => { load(); }, []);

  // Keep the offer countdown moving without re-fetching.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelRegistration(queue.registration_id ?? data?.active_registration?.id);
      setConfirmCancel(false);
      load();
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not cancel your registration."
      );
      setConfirmCancel(false);
    } finally {
      setCancelling(false);
    }
  };

  if (error) return <PageShell role="student" title="My Transport"><Banner variant="danger">{error}</Banner></PageShell>;
  if (!data)  return <PageShell role="student" title="My Transport"><Spinner /></PageShell>;

  const { profile, active_registration, seat, waitlist_position, waitlist, fee_summary } = data;
  const queueInfo = queue?.waitlist || waitlist;
  const countdown = formatCountdown(queue?.payment_due_at, now);
  const isWaitlisted = Boolean(queueInfo) && !seat;
  const isSeatHeld = queue?.status === "Seat Held" && queue?.challan_status !== "paid";
  const canCancel =
    queue?.challan_status !== "paid" &&
    ["Waitlisted", "Seat Held", "Pending"].includes(queue?.status || "");
  // queue.status comes from TransportRegistration and is the authoritative
  // value ("Seat Held" / "Waitlisted" / "Approved"); the dashboard's
  // active_registration is only a fallback for older data.
  const effectiveStatus = queue?.status || active_registration?.status || "";
  const normStatus = effectiveStatus.toLowerCase();
  const hasSubmittedFee = Boolean(active_registration?.fee_submitted);
  const shouldShowPending = !seat && hasSubmittedFee && ["pending", "approved", "payment_submitted"].includes(normStatus);
  const displayStatus = shouldShowPending ? pendingMsg : effectiveStatus;
  const hasFullAssignment = Boolean(profile && seat && active_registration?.route && active_registration?.bus);

  return (
    <PageShell role="student" title="My Transport">
      {confirmCancel && (
        <ConfirmModal
          title="Cancel registration?"
          message={
            seat
              ? "Your seat will be released immediately and given to the next student in the queue. You will have to register again to get another seat."
              : "You will be removed from the waiting list and lose your place in the queue."
          }
          confirmLabel={cancelling ? "Cancelling…" : "Yes, cancel"}
          onConfirm={handleCancel}
          onCancel={() => setConfirmCancel(false)}
        />
      )}

      <PageTitle sub="Your current semester transport details.">My Transport</PageTitle>

      {/* A held seat expires. Show the clock prominently. */}
      {isSeatHeld && countdown && !countdown.expired && (
        <Banner variant="warning">
          <strong>A seat is being held for you — pay within {countdown.label}.</strong>
          <div style={{ marginTop: 4 }}>
            If the fee is not paid by{" "}
            {new Date(queue.payment_due_at).toLocaleString()}, the seat is
            released to the next student on the waiting list.
          </div>
        </Banner>
      )}

      {isWaitlisted && (
        <Banner variant="info">
          <strong>
            You are number {queueInfo.position} of {queueInfo.total} on the
            waiting list for this route.
          </strong>
          <div style={{ marginTop: 4 }}>
            You have not been charged. A challan is issued only when a seat is
            confirmed for you, and you will be notified the moment one opens up.
          </div>
        </Banner>
      )}

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
                variant={
                  ["approved", "confirmed"].includes(normStatus)
                    ? "success"
                    : ["rejected", "cancelled"].includes(normStatus)
                      ? "danger"
                      : "warning"
                }
              />
            } />
            {!seat && !waitlist_position && !hasSubmittedFee && (
              <Banner variant="warning" style={{ marginTop: "12px" }}>{unpaidMsg}</Banner>
            )}
            {seat && <DetailRow label="Seat Number" value={`#${seat.seat_number}`} />}
            {queueInfo && (
              <DetailRow
                label="Waiting List"
                value={`Position ${queueInfo.position} of ${queueInfo.total}`}
              />
            )}
            {!queueInfo && waitlist_position && (
              <DetailRow label="Waitlist Position" value={`#${waitlist_position}`} />
            )}
            {isSeatHeld && countdown && (
              <DetailRow
                label="Pay Before"
                value={
                  countdown.expired
                    ? "Deadline passed"
                    : `${new Date(queue.payment_due_at).toLocaleString()} (${countdown.label} left)`
                }
              />
            )}

            {canCancel && (
              <div style={{ marginTop: 16 }}>
                <button
                  onClick={() => setConfirmCancel(true)}
                  style={{ ...btn.danger, padding: "8px 16px", fontSize: 13 }}
                >
                  {seat ? "Cancel registration" : "Leave waiting list"}
                </button>
                <p style={{ margin: "6px 0 0", fontSize: 11.5, color: colors.textMuted }}>
                  {seat
                    ? "Releases your seat to the next student in the queue."
                    : "Frees your place for the students behind you."}
                </p>
              </div>
            )}
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
          <>
            <p style={{ margin: "0 0 12px", color: colors.textSecondary, fontSize: "13.5px" }}>
              You are not registered for transport this semester.
            </p>
            <button
              onClick={() => navigate("/student/transport-registrations")}
              style={{ ...btn.primary, padding: "8px 16px", fontSize: 13 }}
            >
              Register for transport
            </button>
          </>
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