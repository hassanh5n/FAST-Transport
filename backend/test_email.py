"""
SMTP Diagnostic Script
Run with: python test_email.py your@email.com
Place this file in the backend/ directory.
"""

import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Load .env manually (no Django needed) ────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── Settings ──────────────────────────────────────────────────────────────────
HOST      = "smtp-relay.brevo.com"
PORT      = 587
USER      = "a8d609001@smtp-brevo.com"
PASSWORD  = os.environ.get("EMAIL_HOST_PASSWORD", "")
FROM_ADDR = "thundermarks.agency@gmail.com"
TO_ADDR   = sys.argv[1] if len(sys.argv) > 1 else None

print("\n── FAST Transport SMTP Diagnostics ──")
print(f"  Host     : {HOST}:{PORT}")
print(f"  User     : {USER}")
print(f"  Password : {'(set, length=' + str(len(PASSWORD)) + ')' if PASSWORD else '(NOT SET — check .env)'}")
print(f"  From     : {FROM_ADDR}")
print(f"  To       : {TO_ADDR or '(none — pass email as argument)'}")
print()

if not PASSWORD:
    print("❌  EMAIL_HOST_PASSWORD is empty.")
    print("    Add it to your .env file:")
    print("    EMAIL_HOST_PASSWORD=your_brevo_smtp_key")
    print("    You can find it in Brevo → SMTP & API → SMTP tab.")
    sys.exit(1)

if not TO_ADDR:
    print("❌  No recipient. Usage:  python test_email.py you@example.com")
    sys.exit(1)

# ── Step 1: TCP connectivity ──────────────────────────────────────────────────
import socket
print("Step 1 — TCP connectivity...")
try:
    sock = socket.create_connection((HOST, PORT), timeout=10)
    sock.close()
    print(f"  ✓  Connected to {HOST}:{PORT}")
except Exception as e:
    print(f"  ❌  Cannot reach {HOST}:{PORT} → {e}")
    print("      Likely cause: firewall or Docker network blocking port 587.")
    print("      Try: nc -zv smtp-relay.brevo.com 587")
    sys.exit(1)

# ── Step 2: STARTTLS handshake ────────────────────────────────────────────────
print("\nStep 2 — STARTTLS...")
try:
    server = smtplib.SMTP(HOST, PORT, timeout=15)
    server.set_debuglevel(0)
    server.ehlo()
    server.starttls(context=ssl.create_default_context())
    server.ehlo()
    print("  ✓  STARTTLS handshake succeeded")
except Exception as e:
    print(f"  ❌  STARTTLS failed → {e}")
    sys.exit(1)

# ── Step 3: Authentication ────────────────────────────────────────────────────
print("\nStep 3 — Authentication...")
try:
    server.login(USER, PASSWORD)
    print("  ✓  Authenticated as", USER)
except smtplib.SMTPAuthenticationError as e:
    print(f"  ❌  Auth failed → {e}")
    print("      Your Brevo SMTP password is wrong.")
    print("      Go to Brevo → SMTP & API → Generate a new SMTP key.")
    server.quit()
    sys.exit(1)
except Exception as e:
    print(f"  ❌  Unexpected auth error → {e}")
    server.quit()
    sys.exit(1)

# ── Step 4: Send test email ───────────────────────────────────────────────────
print(f"\nStep 4 — Sending test email to {TO_ADDR}...")
msg = MIMEMultipart("alternative")
msg["Subject"] = "FAST Transport — SMTP Test"
msg["From"]    = f"FAST Transport <{FROM_ADDR}>"
msg["To"]      = TO_ADDR

html = """\
<html><body>
<h2 style="color:#0b2d42">SMTP Test Successful ✓</h2>
<p>If you're reading this, your Brevo SMTP relay is configured correctly.</p>
<p style="color:#888;font-size:12px">Sent from FAST Transport diagnostic script</p>
</body></html>
"""
msg.attach(MIMEText("SMTP Test Successful. Your Brevo relay is working.", "plain"))
msg.attach(MIMEText(html, "html"))

try:
    server.sendmail(FROM_ADDR, [TO_ADDR], msg.as_string())
    server.quit()
    print(f"  ✓  Email sent to {TO_ADDR}")
    print("\n✅  All checks passed.")
    print("    If the email doesn't arrive within 2 minutes, check spam.")
    print("    If it's in spam, verify your sender domain in Brevo:")
    print("    Brevo → Senders & Domains → Add 'thundermarks.agency' domain → add DNS records.")
except Exception as e:
    server.quit()
    print(f"  ❌  Send failed → {e}")
    sys.exit(1)