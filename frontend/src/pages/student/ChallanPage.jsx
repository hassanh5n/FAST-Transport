import { useCallback, useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, Banner, Pill, ValidatedInput } from "../../components/ui";
import { BrandMark, BrandWordmark } from "../../components/Brand";
import { btn, colors, fonts, radius } from "../../theme";
import {
  getChallan, createPaymentIntent, confirmStripePayment, verifyPaymentOtp,
} from "../../services/transportService";
import { formatPKR, formatDate } from "./transportHelpers";

const sectionH = { margin: 0, fontSize: 15, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading };
const labelSt = { fontSize: 12.5, fontWeight: 600, color: colors.textSecondary, display: "block", marginBottom: 5 };
const inputSt = { width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${colors.borderMid}`, fontSize: 15, color: colors.textPrimary, background: "#fff", outline: "none", boxSizing: "border-box" };

// ── Payment steps (card, then emailed OTP) ───────────────────────────────────
function StepIndicator({ current }) {
  const steps = ["Card details", "Verify by email", "Done"];
  return (
    <ol className="pay-steps">
      {steps.map((label, i) => {
        const done = i < current, active = i === current;
        return (
          <li key={label} className={`pay-steps__item${done ? " is-done" : ""}${active ? " is-active" : ""}`}>
            <span className="pay-steps__dot" aria-hidden="true">{done ? "✓" : i + 1}</span>
            <span className="pay-steps__label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ── Simulated Stripe card form ────────────────────────────────────────────────
function StripeCardForm({ amount, onSuccess, onCancel }) {
  const [card, setCard] = useState("4242 4242 4242 4242");
  const [expiry, setExpiry] = useState("12/29");
  const [cvc, setCvc] = useState("123");
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");

  const handlePay = async () => {
    setError("");
    if (card.replace(/\s/g, "").length !== 16) { setError("Enter a 16-digit card number."); return; }
    if (!expiry.match(/^\d{2}\/\d{2}$/)) { setError("Enter the expiry as MM/YY."); return; }
    if (cvc.length < 3) { setError("Enter the 3 or 4 digit CVC."); return; }
    setProcessing(true);
    try { await onSuccess(); }
    catch (err) { setError(err.response?.data?.detail || "The payment could not be confirmed. Try again."); }
    finally { setProcessing(false); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {error && <Banner variant="danger">{error}</Banner>}
      <div>
        <label style={labelSt}>Card number</label>
        <ValidatedInput value={card} onChange={(e) => setCard(e.target.value)} placeholder="4242 4242 4242 4242" maxLength={19} style={inputSt}
          validators={[{ check: "required", message: "Card number required" }, { check: "minLength", arg: 16, message: "Enter a valid card number" }]} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label style={labelSt}>Expiry</label>
          <ValidatedInput value={expiry} onChange={(e) => setExpiry(e.target.value)} placeholder="MM/YY" maxLength={5} style={inputSt} validators={[{ check: "required", message: "Expiry required" }]} />
        </div>
        <div>
          <label style={labelSt}>CVC</label>
          <ValidatedInput value={cvc} onChange={(e) => setCvc(e.target.value)} placeholder="123" maxLength={4} type="password" style={inputSt}
            validators={[{ check: "required", message: "CVC required" }, { check: "minLength", arg: 3, message: "Enter a valid CVC" }]} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
        <button onClick={onCancel} disabled={processing} style={{ ...btn.ghost, flex: "0 0 auto" }}>Back</button>
        <button onClick={handlePay} disabled={processing} style={{ ...btn.primary, flex: 1, padding: "11px 18px", opacity: processing ? 0.7 : 1 }}>
          {processing ? "Processing…" : `Pay ${formatPKR(amount)}`}
        </button>
      </div>
      <p style={{ fontSize: 12, color: colors.textMuted, margin: 0, textAlign: "center" }}>
        Test mode. Use card 4242 4242 4242 4242.
      </p>
    </div>
  );
}

// ── Emailed OTP ───────────────────────────────────────────────────────────────
function OTPInput({ emailHint, onVerify, onResend }) {
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refs = useRef([]);

  const handleChange = (i, val) => {
    if (!/^\d*$/.test(val)) return;
    const next = [...otp]; next[i] = val.slice(-1); setOtp(next);
    if (val && i < 5) refs.current[i + 1]?.focus();
  };

  // Pasting the whole code from the email fills every box.
  const handlePaste = (e) => {
    const digits = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!digits) return;
    e.preventDefault();
    setOtp([...digits.padEnd(6, " ")].map((d) => d.trim()));
    refs.current[Math.min(digits.length, 5)]?.focus();
  };

  const handleKeyDown = (i, e) => {
    if (e.key === "Backspace" && !otp[i] && i > 0) refs.current[i - 1]?.focus();
    if (e.key === "Enter") handleSubmit();
  };

  const handleSubmit = async () => {
    const code = otp.join("");
    if (code.length !== 6) { setError("Enter all 6 digits."); return; }
    setError(""); setNotice(""); setVerifying(true);
    try { await onVerify(code); }
    catch (err) { setError(err.response?.data?.detail || "Verification failed. Check the code and try again."); setVerifying(false); }
  };

  const handleResend = async () => {
    setError(""); setNotice("");
    try { await onResend(); setNotice("A new code is on its way."); }
    catch { setError("Could not resend the code. Try again in a minute."); }
  };

  return (
    <div>
      <p style={{ margin: "0 0 16px", fontSize: 13.5, lineHeight: 1.6, color: colors.textSecondary }}>
        Enter the 6-digit code sent to <strong style={{ color: colors.textPrimary }}>{emailHint || "your email"}</strong>.
      </p>
      {error && <Banner variant="danger">{error}</Banner>}
      {notice && <Banner variant="success">{notice}</Banner>}
      <div style={{ display: "flex", gap: 8, justifyContent: "space-between", marginBottom: 16 }}>
        {otp.map((digit, i) => (
          <input key={i} ref={(el) => (refs.current[i] = el)} value={digit} aria-label={`Digit ${i + 1}`}
            onChange={(e) => handleChange(i, e.target.value)} onKeyDown={(e) => handleKeyDown(i, e)} onPaste={handlePaste}
            className="otp-box" maxLength={1} inputMode="numeric" autoComplete={i === 0 ? "one-time-code" : "off"} />
        ))}
      </div>
      <button onClick={handleSubmit} disabled={verifying} style={{ ...btn.primary, width: "100%", padding: 12, opacity: verifying ? 0.7 : 1 }}>
        {verifying ? "Verifying…" : "Verify and pay"}
      </button>
      <p style={{ fontSize: 12.5, color: colors.textMuted, textAlign: "center", margin: "14px 0 0" }}>
        Didn't get it?{" "}
        <button type="button" onClick={handleResend} style={{ background: "none", border: "none", padding: 0, color: colors.accent, cursor: "pointer", fontWeight: 600, fontSize: 12.5 }}>
          Resend code
        </button>
      </p>
    </div>
  );
}

// ── Success overlay ───────────────────────────────────────────────────────────
function SuccessCard({ amount, onClose }) {
  return createPortal(
    <div role="dialog" aria-modal="true" aria-labelledby="pay-success-title" style={{ position: "fixed", inset: 0,
      background: "rgba(11,45,66,0.55)", backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
    }}>
      <div className="pay-success" style={{ background: "#fff", borderRadius: radius.xl, padding: "2.25rem 2rem",
        maxWidth: 360, width: "90%", textAlign: "center", boxShadow: "0 32px 80px rgba(11,45,66,0.3)" }}>
        <svg viewBox="0 0 80 80" width="72" height="72" style={{ margin: "0 auto 1.25rem", display: "block" }} aria-hidden="true">
          <circle cx="40" cy="40" r="38" fill={colors.successBg} stroke={colors.successText} strokeWidth="1.5" />
          <polyline points="22,40 35,53 58,28" fill="none" stroke={colors.successText} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <p id="pay-success-title" style={{ fontSize: 19, fontWeight: 700, fontFamily: fonts.heading, margin: "0 0 8px", color: colors.textPrimary }}>Payment received</p>
        <p style={{ fontSize: 13.5, lineHeight: 1.6, color: colors.textSecondary, margin: "0 0 1.25rem" }}>
          {formatPKR(amount)} has been paid. The transport office will verify it and confirm your seat.
        </p>
        <button onClick={onClose} style={{ ...btn.primary, width: "100%", padding: 11 }}>Done</button>
      </div>
      <style>{`.pay-success { animation: popIn 0.45s cubic-bezier(.34,1.56,.64,1) both; }
        @keyframes popIn { 0%{transform:scale(0.6);opacity:0} 100%{transform:scale(1);opacity:1} }
        @media (prefers-reduced-motion: reduce) { .pay-success { animation: none; } }`}</style>
    </div>,
    document.body
  );
}

// ── The challan itself, plus the payment panel ───────────────────────────────
export function ChallanView({ id }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [emailHint, setEmailHint] = useState("");
  const [showSuccess, setShowSuccess] = useState(false);
  const [startError, setStartError] = useState("");
  const [starting, setStarting] = useState(false);
  const pollRef = useRef(null);

  const fetchChallan = useCallback(
    () => getChallan(id).then((res) => setData(res.data)).catch(() => {}),
    [id]
  );

  useEffect(() => {
    getChallan(id).then((res) => { setData(res.data); setLoading(false); }).catch(() => setLoading(false));
  }, [id]);

  // Paid but not yet verified: check back every 10s so approval shows up on its own.
  useEffect(() => {
    const isPaidNotApproved = data?.status === "paid" && (data?.registration_status || "").toLowerCase() !== "approved";
    if (isPaidNotApproved) pollRef.current = setInterval(fetchChallan, 10000);
    else clearInterval(pollRef.current);
    return () => clearInterval(pollRef.current);
  }, [data?.status, data?.registration_status, fetchChallan]);

  const handleStartPayment = async () => {
    setStartError(""); setStarting(true);
    try { await createPaymentIntent(id); setStep(1); }
    catch (err) { setStartError(err.response?.data?.detail || "Could not start the payment. Try again."); }
    finally { setStarting(false); }
  };

  const handleCardSuccess = async () => {
    const res = await confirmStripePayment(id);
    setEmailHint(res.data?.email_hint || "");
    setStep(2);
  };

  const handleOTPVerify = async (otp) => {
    await verifyPaymentOtp(id, otp);
    setShowSuccess(true);
  };

  if (loading) return <Spinner />;
  if (!data) return <Banner variant="danger">This challan could not be found. Open it again from My Transport.</Banner>;

  const isPaid = data.status === "paid";
  const isApproved = (data.registration_status || "").toLowerCase() === "approved";
  const dueAt = data.payment_due_at ? new Date(data.payment_due_at) : null;
  const overdue = !isPaid && dueAt && dueAt.getTime() < Date.now();
  const challanNo = String(data.id ?? id).padStart(6, "0");
  const statusPill = isPaid
    ? <Pill label={isApproved ? "Verified" : "Paid"} variant="success" />
    : <Pill label={overdue ? "Overdue" : "Unpaid"} variant={overdue ? "danger" : "warning"} />;

  return (
    <div className="tp-layout">
      {/* ── The challan document ── */}
      <ContentCard style={{ marginBottom: 0, padding: 0, overflow: "hidden" }}>
        <div className="challan-head">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={34} />
            <div>
              <BrandWordmark height={12} style={{ marginBottom: 4 }} />
              <div style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.75)" }}>Transport fee challan</div>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>Challan no.</div>
            <div style={{ fontFamily: fonts.heading, fontSize: 18, fontWeight: 700, color: "#fff", letterSpacing: "0.04em" }}>{challanNo}</div>
          </div>
        </div>

        <div style={{ padding: "24px 28px 28px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 12.5, color: colors.textMuted }}>Billed to</div>
              <div style={{ fontFamily: fonts.heading, fontSize: 18, fontWeight: 700, color: colors.textPrimary, marginTop: 2 }}>{data.student_name || "—"}</div>
            </div>
            {statusPill}
          </div>

          <dl className="tp-facts">
            <div className="tp-fact"><dt>Semester</dt><dd>{data.semester_name || "—"}</dd></div>
            <div className="tp-fact"><dt>Route</dt><dd>{data.route_name || "—"}</dd></div>
            <div className="tp-fact"><dt>Pickup stop</dt><dd>{data.stop_name || "—"}</dd></div>
            <div className="tp-fact"><dt>Issued on</dt><dd>{formatDate(data.created_at) || "—"}</dd></div>
            {!isPaid && dueAt && (
              <div className="tp-fact tp-fact--wide"><dt>Pay by</dt><dd style={overdue ? { color: colors.dangerText } : undefined}>{formatDate(dueAt, true)}</dd></div>
            )}
          </dl>

          <table className="challan-lines">
            <thead>
              <tr><th>Description</th><th>Amount</th></tr>
            </thead>
            <tbody>
              <tr><td>Transport fee, {data.semester_name || "this semester"}</td><td>{formatPKR(data.amount)}</td></tr>
            </tbody>
            <tfoot>
              <tr><td>Total {isPaid ? "paid" : "due"}</td><td>{formatPKR(data.amount)}</td></tr>
            </tfoot>
          </table>
        </div>
      </ContentCard>

      {/* ── Payment panel ── */}
      <aside className="tp-side challan-side">
        <ContentCard style={{ marginBottom: 0 }}>
          {isPaid ? (
            <>
              <h3 style={{ ...sectionH, fontSize: 17 }}>{isApproved ? "Paid and verified" : "Payment received"}</h3>
              <p style={{ margin: "8px 0 16px", fontSize: 13.5, lineHeight: 1.6, color: colors.textSecondary }}>
                {isApproved
                  ? "Your fee is verified and your registration is active for this semester."
                  : "The transport office is verifying your payment. This page updates on its own once they do."}
              </p>
              <button onClick={() => navigate("/student/transport")} style={isApproved ? btn.primary : { ...btn.ghost }}>
                Go to My Transport
              </button>
            </>
          ) : step === 0 ? (
            <>
              <div style={{ fontSize: 12.5, color: colors.textSecondary }}>Amount due</div>
              <div style={{ fontFamily: fonts.heading, fontSize: 30, fontWeight: 800, color: colors.textPrimary, letterSpacing: "-0.02em", margin: "2px 0 6px" }}>
                {formatPKR(data.amount)}
              </div>
              {dueAt && (
                <p style={{ margin: "0 0 18px", fontSize: 13, color: overdue ? colors.dangerText : colors.textSecondary }}>
                  {overdue
                    ? "The payment deadline has passed. Your held seat may have been released."
                    : `Pay by ${formatDate(dueAt, true)} to keep your seat.`}
                </p>
              )}
              {!dueAt && <div style={{ height: 12 }} />}
              {startError && <Banner variant="danger">{startError}</Banner>}
              <button onClick={handleStartPayment} disabled={starting} style={{ ...btn.primary, width: "100%", padding: 12, fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: starting ? 0.7 : 1 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><rect x="1" y="4" width="22" height="16" rx="2" /><line x1="1" y1="10" x2="23" y2="10" /></svg>
                {starting ? "Starting…" : "Pay online"}
              </button>
              <p style={{ margin: "12px 0 0", fontSize: 12, lineHeight: 1.55, color: colors.textMuted, textAlign: "center" }}>
                Card payment, confirmed with a code sent to your email.
              </p>
            </>
          ) : (
            <>
              <StepIndicator current={step - 1} />
              {step === 1 && <StripeCardForm amount={data.amount} onSuccess={handleCardSuccess} onCancel={() => setStep(0)} />}
              {step === 2 && <OTPInput emailHint={emailHint} onVerify={handleOTPVerify} onResend={() => createPaymentIntent(id)} />}
            </>
          )}
        </ContentCard>

        <ContentCard style={{ marginBottom: 0 }}>
          <h3 style={sectionH}>Need help?</h3>
          <p style={{ margin: "6px 0 12px", fontSize: 13, lineHeight: 1.6, color: colors.textSecondary }}>
            {isPaid ? "Questions about this payment go to the transport office." : "If the amount or details look wrong, raise it with the transport office before paying."}
          </p>
          <button onClick={() => navigate("/student/complaints")} style={{ ...btn.ghost, padding: "8px 14px" }}>Contact the office</button>
        </ContentCard>
      </aside>

      {showSuccess && <SuccessCard amount={data.amount} onClose={() => { setShowSuccess(false); setStep(0); fetchChallan(); }} />}
    </div>
  );
}

// Route: /student/challan/:id
function ChallanPage() {
  const { id } = useParams();
  return (
    <PageShell role="student" title="My Challan">
      <PageTitle sub="Your transport fee for this semester and how to pay it.">Challan</PageTitle>
      <ChallanView id={id} />
    </PageShell>
  );
}

export default ChallanPage;
