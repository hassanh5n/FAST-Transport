// Common client-side validators used across student/auth pages
export const validators = {
  required: (v) => v !== undefined && v !== null && String(v).trim() !== "",
  email: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || "")),
  minLength: (v, n) => String(v || "").length >= n,
  maxLength: (v, n) => String(v || "").length <= n,
  numeric: (v) => /^\d+$/.test(String(v || "")),
  phone: (v) => /^\+?\d[\d\s-]{7,}$/.test(String(v || "")),
  roll: (v) => /^[A-Za-z0-9-]{3,20}$/.test(String(v || "")),
  otp6: (v) => /^\d{6}$/.test(String(v || "")),
  // Exact domain after the last "@"; the backend enforces the same rule (SIGNUP_EMAIL_DOMAINS).
  emailDomain: (v, domain) => String(v || "").trim().toLowerCase().split("@").pop() === domain,
};

// Students sign up with a university email (faculty are not restricted yet).
export const SIGNUP_EMAIL_DOMAIN = "nu.edu.pk";

export function validateField(value, rules) {
  // rules: array of { check: 'required'|'email'|..., arg?: any, message: '...' }
  for (const r of rules) {
    const fn = validators[r.check];
    if (!fn) continue;
    const ok = r.arg !== undefined ? fn(value, r.arg) : fn(value);
    if (!ok) return r.message || "Invalid value";
  }
  return null;
}
