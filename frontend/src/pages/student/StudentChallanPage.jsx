// Route: /student/challan ("View Challan" in the sidebar).
// Opens the current registration's challan directly instead of a details page
// with a second "View Challan" button.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner } from "../../components/ui";
import { btn, colors, fonts } from "../../theme";
import { getRegistration } from "../../services/transportService";
import { ChallanView } from "./ChallanPage";

// Same rule as the Register page: the live registration is the one that is not cancelled.
function pickRegistration(payload) {
  const list = payload?.results ?? payload;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list.find((r) => r.status !== "Cancelled") || list[list.length - 1];
}

function EmptyState({ title, text, action, onAction }) {
  return (
    <ContentCard style={{ maxWidth: 640 }}>
      <h3 style={{ margin: 0, fontSize: 19, fontWeight: 700, fontFamily: fonts.heading, color: colors.textPrimary }}>{title}</h3>
      <p style={{ margin: "8px 0 18px", fontSize: 14, lineHeight: 1.6, color: colors.textSecondary }}>{text}</p>
      {action && <button onClick={onAction} style={btn.primary}>{action}</button>}
    </ContentCard>
  );
}

function StudentChallanPage() {
  const navigate = useNavigate();
  const [registration, setRegistration] = useState(undefined); // undefined while loading
  const [error, setError] = useState("");

  useEffect(() => {
    getRegistration()
      .then((res) => setRegistration(pickRegistration(res.data)))
      .catch(() => { setError("Could not load your registration. Refresh the page to try again."); setRegistration(null); });
  }, []);

  const status = registration?.status?.toLowerCase();

  let body;
  if (registration === undefined) body = <Spinner />;
  else if (error) body = <Banner variant="danger">{error}</Banner>;
  else if (!registration || status === "cancelled") {
    body = (
      <EmptyState
        title="No challan yet"
        text="A challan is issued once you register for transport and a seat is held for you."
        action="Register for transport"
        onAction={() => navigate("/student/transport-registrations")}
      />
    );
  } else if (status === "waitlisted") {
    // Not fetching the challan here: the challan endpoint creates one on first read,
    // and a waitlisted passenger must not be billed.
    body = (
      <EmptyState
        title="You're on the waiting list"
        text="Nothing is due yet. A challan is issued only when a seat is confirmed for you, and you'll be notified the moment one opens up."
        action="See my position"
        onAction={() => navigate("/student/transport")}
      />
    );
  } else {
    body = <ChallanView id={registration.id} />;
  }

  return (
    <PageShell role="student" title="My Challan">
      <PageTitle sub="Your transport fee for this semester and how to pay it.">Challan</PageTitle>
      {body}
    </PageShell>
  );
}

export default StudentChallanPage;
