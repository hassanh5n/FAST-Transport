import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useParams } from "react-router-dom";
import PageShell, { PageTitle, ContentCard } from "../../components/PageShell";
import { Spinner, DetailRow, Banner, ValidatedInput } from "../../components/ui";
import { btn, colors, radius } from "../../theme";
import {
  getChallan, createPaymentIntent, confirmStripePayment, verifyPaymentOtp,
} from "../../services/transportService";

// ── Step indicator ────────────────────────────────────────────────────────────
function StepIndicator({ current }) {
  const steps = ["Card Details", "OTP Verification", "Complete"];
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: "28px" }}>
      {steps.map((label, i) => {
        const done = i < current, active = i === current;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", flex: i < steps.length - 1 ? 1 : "none" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: "70px" }}>
              <div style={{
                width: "32px", height: "32px", borderRadius: "50%", display: "grid", placeItems: "center",
                fontSize: "13px", fontWeight: 600,
                background: done ? colors.successText : active ? colors.accent : colors.borderMid,
                color: (done || active) ? "#fff" : colors.textMuted, transition: "all 0.3s",
              }}>
                {done ? "✓" : i + 1}
              </div>
              <span style={{ fontSize: "11px", marginTop: "4px", color: active ? colors.accent : colors.textMuted, fontWeight: active ? 600 : 400 }}>
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ flex: 1, height: "2px", background: done ? colors.successText : colors.borderLight, margin: "0 6px", transition: "all 0.3s" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Simulated Stripe card form ────────────────────────────────────────────────
function StripeCardForm({ amount, onSuccess, onCancel }) {
  const [card, setCard] = useState("4242 4242 4242 4242");
  const [expiry, setExpiry] = useState("12/29");
  const [cvc, setCvc] = useState("123");
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");

  const handlePay = () => {
    setError("");
    if (card.replace(/\s/g, "").length !== 16) { setError("Invalid card number"); return; }
    if (!expiry.match(/^\d{2}\/\d{2}$/)) { setError("Invalid expiry (MM/YY)"); return; }
    if (cvc.length < 3) { setError("Invalid CVC"); return; }
    setProcessing(true);
    setTimeout(() => { setProcessing(false); onSuccess(); }, 1500);
  };

  return (
    <div style={{ border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, padding: "24px", background: colors.pageBg, marginBottom: "20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "18px" }}>
        <svg width="45" height="28" viewBox="0 0 45 28" fill="none">
          <rect width="45" height="28" rx="6" fill="#288dc4" />
          <text x="6" y="19" fill="white" fontSize="12" fontWeight="700" fontFamily="sans-serif">Stripe</text>
        </svg>
        <span style={{ fontSize: "14px", fontWeight: 600, color: colors.textPrimary }}>Stripe Test Payment</span>
        <span style={{ marginLeft: "auto", fontSize: "11px", padding: "2px 8px", borderRadius: "4px", background: colors.infoBg, color: colors.infoText, fontWeight: 500 }}>MASTERCARD/VISA</span>
      </div>
      <div style={{ fontSize: "22px", fontWeight: 700, color: colors.textPrimary, marginBottom: "20px" }}>PKR {amount}</div>
      {error && <Banner variant="danger" style={{ marginBottom: "12px" }}>{error}</Banner>}
      <div style={{ marginBottom: "14px" }}>
        <label style={stripeLabelSt}>Card Number</label>
        <ValidatedInput
          value={card}
          onChange={(e) => setCard(e.target.value)}
          placeholder="4242 4242 4242 4242"
          maxLength={19}
          style={{ ...stripeInputSt, width: "100%" }}
          validators={[{ check: "required", message: "Card number required" }, { check: "minLength", arg: 16, message: "Enter a valid card number" }]}
        />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "20px", minWidth: 0 }}>
        <div>
          <label style={stripeLabelSt}>Expiry</label>
          <ValidatedInput value={expiry} onChange={e => setExpiry(e.target.value)} placeholder="MM/YY" maxLength={5} style={stripeInputSt} validators={[{ check: "required", message: "Expiry required" }]} />
        </div>
        <div>
          <label style={stripeLabelSt}>CVC</label>
          <ValidatedInput value={cvc} onChange={e => setCvc(e.target.value)} placeholder="123" maxLength={4} type="password" style={stripeInputSt} validators={[{ check: "required", message: "CVC required" }, { check: "minLength", arg: 3, message: "Enter a valid CVC" }]} />
        </div>
      </div>
      <div style={{ display: "flex", gap: "10px" }}>
        <button onClick={onCancel} disabled={processing} style={{ ...btn.ghost, flex: "0 0 auto" }}>Cancel</button>
        <button onClick={handlePay} disabled={processing} style={{ ...btn.primary, background: "#288dc4", flex: 1 }}>
          {processing ? "Processing…" : `Pay PKR ${amount}`}
        </button>
      </div>
      <p style={{ fontSize: "11px", color: colors.textMuted, margin: "14px 0 0", textAlign: "center" }}>
        🔒 Test mode — use card 4242 4242 4242 4242
      </p>
    </div>
  );
}

// ── OTP input ─────────────────────────────────────────────────────────────────
function OTPInput({ emailHint, onVerify, onResend }) {
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const refs = useRef([]);

  const handleChange = (i, val) => {
    if (!/^\d*$/.test(val)) return;
    const next = [...otp]; next[i] = val.slice(-1); setOtp(next);
    if (val && i < 5) refs.current[i + 1]?.focus();
  };

  const handleKeyDown = (i, e) => {
    if (e.key === "Backspace" && !otp[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const handleSubmit = async () => {
    const code = otp.join("");
    if (code.length !== 6) { setError("Please enter all 6 digits."); return; }
    setError(""); setVerifying(true);
    try { await onVerify(code); }
    catch (err) { setError(err.response?.data?.detail || "Verification failed."); setVerifying(false); }
  };

  return (
    <div style={{ border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, padding: "28px 24px", background: colors.pageBg, marginBottom: "20px" }}>
      <div style={{ textAlign: "center", marginBottom: "20px" }}>
        <div style={{ width: "56px", height: "56px", borderRadius: "50%", background: colors.infoBg, display: "grid", placeItems: "center", margin: "0 auto 12px" }}>
          <span
            style={{
              display: "inline-flex",
              color: "#9ca3af",
              cursor: "pointer",
              transition: "0.2s"
            }}
            onMouseEnter={e => e.currentTarget.style.color = "#fff"}
            onMouseLeave={e => e.currentTarget.style.color = "#9ca3af"}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="M3 7l9 6 9-6" />
            </svg>
          </span>
        </div>
        <h3 style={{ margin: "0 0 6px", fontSize: "18px", color: colors.textPrimary }}>OTP Verification</h3>
        <p style={{ margin: 0, fontSize: "13px", color: colors.textSecondary }}>
          We've sent a 6-digit code to <strong>{emailHint || "your email"}</strong>
        </p>
      </div>
      {error && <Banner variant="danger" style={{ marginBottom: "12px", textAlign: "center" }}>{error}</Banner>}
      <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginBottom: "20px" }}>
        {otp.map((digit, i) => (
          <input key={i} ref={el => (refs.current[i] = el)} value={digit}
            onChange={e => handleChange(i, e.target.value)} onKeyDown={e => handleKeyDown(i, e)}
            style={{ width: "44px", height: "52px", textAlign: "center", fontSize: "22px", fontWeight: 700, borderRadius: "8px", border: `1px solid ${colors.borderMid}`, outline: "none", background: "#fff" }}
            maxLength={1} inputMode="numeric" />
        ))}
      </div>
      <button onClick={handleSubmit} disabled={verifying} style={{ ...btn.primary, background: "#288dc4", width: "100%", padding: "12px" }}>
        {verifying ? "Verifying…" : "Verify OTP"}
      </button>
      <p style={{ fontSize: "12px", color: colors.textMuted, textAlign: "center", margin: "14px 0 0" }}>
        Didn't receive the code?{" "}
        <span onClick={onResend} style={{ color: colors.accent, cursor: "pointer", fontWeight: 500 }}>Resend OTP</span>
      </p>
    </div>
  );
}

// ── Success overlay ───────────────────────────────────────────────────────────
function SuccessCard({ amount, onClose }) {
  return createPortal(
    <div style={{ position: "fixed", top: 0, right: 0, bottom: 0, left: 0,
      background: "rgba(11,45,66,0.55)",
      backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 9999,
    }}>
      <div style={{ background: "#fff", borderRadius: radius.xl, padding: "2.5rem 2rem",
        maxWidth: "340px", width: "90%", textAlign: "center",
        animation: "popIn 0.5s cubic-bezier(.34,1.56,.64,1) both",
        boxShadow: "0 32px 80px rgba(11,45,66,0.3)",
      }}>
        <div style={{ width: "80px", height: "80px", margin: "0 auto 1.5rem" }}>
          <svg viewBox="0 0 80 80" width="80" height="80">
            <circle cx="40" cy="40" r="38" fill={colors.successBg} stroke={colors.successText} strokeWidth="1.5" />
            <polyline points="22,40 35,53 58,28" fill="none" stroke={colors.successText} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <p style={{ fontSize: "18px", fontWeight: "500", margin: "0 0 8px", color: colors.textPrimary }}>Payment Verified</p>
        <p style={{ fontSize: "13px", color: colors.textSecondary, margin: "0 0 1.5rem" }}>
          Your fee payment has been verified via OTP.<br />Wait for admin to confirm registration.
        </p>
        <div style={{ background: colors.pageBg, borderRadius: radius.md, padding: "12px 16px", textAlign: "left", marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontSize: "13px", color: colors.textSecondary }}>Amount</span>
            <span style={{ fontSize: "13px", fontWeight: "500" }}>PKR {amount}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: "13px", color: colors.textSecondary }}>Status</span>
            <span style={{ fontSize: "12px", fontWeight: "600", background: colors.successBg, color: colors.successText, padding: "2px 10px", borderRadius: "20px" }}>
              Paid & Verified
            </span>
          </div>
        </div>
        <button onClick={onClose} style={{ ...btn.primary, background: colors.successText, width: "100%", padding: "10px" }}>Done</button>
      </div>
      <style>{`@keyframes popIn { 0%{transform:scale(0.4);opacity:0} 70%{transform:scale(1.08)} 100%{transform:scale(1);opacity:1} }`}</style>
    </div>,
    document.body                          
  );
}

// ── Main ChallanPage ──────────────────────────────────────────────────────────
function ChallanPage() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [emailHint, setEmailHint] = useState("");
  const [showSuccess, setShowSuccess] = useState(false);
  const pollRef = useRef(null);

  const fetchChallan = () => getChallan(id).then(res => setData(res.data)).catch(() => {});

  useEffect(() => {
    getChallan(id).then(res => { setData(res.data); setLoading(false); }).catch(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    const isPaidNotApproved = data?.status === "paid" && (data?.registration_status || "").toLowerCase() !== "approved";
    if (isPaidNotApproved) pollRef.current = setInterval(fetchChallan, 10000);
    else clearInterval(pollRef.current);
    return () => clearInterval(pollRef.current);
  }, [data?.status, data?.registration_status]);

  const handleStartPayment = async () => {
    try { await createPaymentIntent(id); setStep(1); }
    catch (err) { alert(err.response?.data?.detail || "Failed to start payment"); }
  };

  const handleCardSuccess = async () => {
    try {
      const res = await confirmStripePayment(id);
      setEmailHint(res.data?.email_hint || "");
      setStep(2);
    } catch (err) { alert(err.response?.data?.detail || "Failed to confirm payment"); }
  };

  const handleOTPVerify = async (otp) => {
    await verifyPaymentOtp(id, otp);
    setShowSuccess(true);
  };

  const handleResendOtp = async () => {
    try { await createPaymentIntent(id); alert("OTP resent."); }
    catch { alert("Failed to resend OTP."); }
  };

  if (loading) return <PageShell role="student" title="My Challan"><Spinner /></PageShell>;
  if (!data)   return <PageShell role="student" title="My Challan"><Banner variant="danger">Challan not found.</Banner></PageShell>;

  const isPaid       = data.status === "paid";
  const isApproved   = (data.registration_status || "").toLowerCase() === "approved";

  return (
    <PageShell role="student" title="My Challan" maxWidth="680px">
      <PageTitle sub={`Registration ID: ${id}`}>Challan Details</PageTitle>

      <div style={{ background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: radius.lg, padding: "24px", marginBottom: "20px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)" }}>
        <DetailRow label="Route"    value={data.route_name} />
        <DetailRow label="Stop"     value={data.stop_name} />
        <DetailRow label="Semester" value={data.semester_name} />
        <DetailRow label="Amount"   value={`PKR ${data.amount}`} />
        <DetailRow label="Status"   value={isPaid ? "Paid" : "Unpaid"} />
        {!isPaid && step === 0 && (
          <div style={{ marginTop: "16px" }}>
            <button onClick={handleStartPayment} style={{ ...btn.primary, background: "#288dc4", display: "flex", alignItems: "center", gap: "8px" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
              Pay PKR {data.amount}
            </button>
          </div>
        )}
        {/*
        <button
          onClick={() => setShowSuccess(true)}
          style={{ ...btn.ghost, marginTop: "12px", fontSize: "12px" }}
        >
          [DEV] Test Success Card
        </button>  */} 
      </div>

      {!isPaid && step >= 1 && step <= 2 && <StepIndicator current={step - 1} />}
      {!isPaid && step === 1 && <StripeCardForm amount={data.amount} onSuccess={handleCardSuccess} onCancel={() => setStep(0)} />}
      {!isPaid && step === 2 && <OTPInput emailHint={emailHint} onVerify={handleOTPVerify} onResend={handleResendOtp} />}
      {isPaid && !isApproved && !showSuccess && (
        <Banner variant="warning">
          <strong>Waiting for admin verification</strong> — Page refreshes automatically every 10 seconds.
        </Banner>
      )}
      {isPaid && isApproved && (
        <Banner variant="success">
          <strong>Fee Verified &amp; Registration Approved</strong> — Your transport registration is now active for this semester.
        </Banner>
      )}
      {showSuccess && <SuccessCard amount={data.amount} onClose={() => { setShowSuccess(false); fetchChallan(); }} />}
    </PageShell>
  );
}

const stripeLabelSt = { fontSize: "11px", fontWeight: "600", color: colors.textSecondary, display: "block", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.04em" };
const stripeInputSt = { width: "100%", padding: "10px 12px", borderRadius: "8px", border: `1px solid ${colors.borderMid}`, fontSize: "15px", color: colors.textPrimary, background: "#fff", outline: "none", boxSizing: "border-box" };

export default ChallanPage;