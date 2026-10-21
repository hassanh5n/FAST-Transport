"""
All outbound email for Fleetcentric.ai.

Every email (OTP codes and notification mirrors) is rendered by one template
in this module and always sent as multipart text + HTML. That keeps local
(Brevo SMTP via DualEmailBackend) and production (Brevo HTTP API) output
identical: both backends receive the same subject, sender, text and HTML.

Notification mirroring:
  Every Notification row is mirrored to the recipient's inbox by a single
  post_save receiver in signals.py, so new notification sites get email for
  free without touching this module.

Design notes (deliberate, given this project has no Celery/queue):

  * Notification email is sent on a short-lived background thread. A slow or
    failing Brevo call must never delay, or 500, a student's request.
    Those failures are swallowed and logged; the in-app notification is the
    source of truth.
  * OTP email is sent synchronously and raises on failure, because callers
    need to tell the user whether the code actually went out.
  * Staff recipients and "alert" notifications are skipped by default. The
    off-route geofence alert fires from the GPS ping signal and fans out to
    every admin, which would burn the Brevo free-tier daily quota (300/day)
    that signup OTPs also depend on.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)

BRAND_NAME = "Fleetcentric.ai"
NAVY = "#0b2d42"
BLUE = "#288dc4"
INK = "#0f1f2d"
MUTED = "#4a6178"
FAINT = "#8faabb"
FONT = "'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

ACCENTS = {
    "info": BLUE,
    "warning": "#f59e0b",
    "alert": "#ef4444",
}

# Notification.type values that should never generate an email.
SKIPPED_TYPES = {"alert"}

OTP_TTL_MINUTES = 10


def _portal_url():
    """Link for the "Open Fleetcentric.ai" button. Set EMAIL_PORTAL_URL to change it."""
    return getattr(settings, "EMAIL_PORTAL_URL", "") or ""


def display_name(user):
    """Full name for greetings ("Hassan Nafees"); username only if no name is set."""
    return (user.get_full_name() or "").strip() or user.username


# ── Rendering ────────────────────────────────────────────────────────────────

def render_email(
    *,
    heading,
    paragraphs,
    name=None,
    code=None,
    code_caption=None,
    details=None,
    button_label=None,
    button_url=None,
    accent=BLUE,
    preheader="",
    footnote=None,
):
    """
    Build the (text, html) pair for one email.

    paragraphs: list of plain strings (escaped here, newlines kept).
    details:    optional list of (label, value) rows shown in a small table.
    code:       optional one-time code shown in a large monospaced box.
    """
    greeting = f"Hi {name}," if name else "Hi there,"

    # Plain-text part
    text = [greeting, "", heading, ""]
    for p in paragraphs:
        text += [p, ""]
    if code:
        text += [f"{code_caption or 'Your code'}: {code}", ""]
    for label, value in details or []:
        text.append(f"{label}: {value}")
    if details:
        text.append("")
    if footnote:
        text += [footnote, ""]
    if button_url:
        text += [f"{button_label or 'Open'}: {button_url}", ""]
    text += [
        "--",
        f"{BRAND_NAME} Transport Portal",
        "This is an automated message. Please do not reply to this email.",
    ]
    text_body = "\n".join(text)

    # HTML part (table layout: email clients are not browsers)
    def para(p):
        return (
            f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{INK};">'
            f'{escape(p).replace(chr(10), "<br>")}</p>'
        )

    body_html = "".join(para(p) for p in paragraphs)

    code_html = ""
    if code:
        code_html = f"""
              <tr>
                <td style="padding:6px 36px 22px;">
                  <div style="font-size:12px;color:{MUTED};text-transform:uppercase;
                              letter-spacing:0.08em;margin-bottom:8px;">
                    {escape(code_caption or 'Your code')}
                  </div>
                  <div style="display:inline-block;background:#f0f6fb;border:1px solid #d6e6f2;
                              border-radius:10px;padding:14px 26px;
                              font-family:Consolas,'Courier New',monospace;font-size:30px;
                              font-weight:700;letter-spacing:8px;color:{NAVY};">
                    {escape(code)}
                  </div>
                </td>
              </tr>"""

    details_html = ""
    if details:
        rows = "".join(
            f"""<tr>
                  <td style="padding:8px 0;font-size:13px;color:{MUTED};width:40%;">{escape(str(l))}</td>
                  <td style="padding:8px 0;font-size:14px;color:{INK};font-weight:600;">{escape(str(v))}</td>
                </tr>"""
            for l, v in details
        )
        details_html = f"""
              <tr>
                <td style="padding:0 36px 18px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                         style="border-top:1px solid #edf2f7;border-bottom:1px solid #edf2f7;">
                    {rows}
                  </table>
                </td>
              </tr>"""

    footnote_html = ""
    if footnote:
        footnote_html = f"""
              <tr>
                <td style="padding:0 36px 18px;">
                  <p style="margin:0;font-size:13px;line-height:1.6;color:{MUTED};">
                    {escape(footnote)}
                  </p>
                </td>
              </tr>"""

    button_html = ""
    if button_url:
        button_html = f"""
              <tr>
                <td style="padding:4px 36px 30px;">
                  <a href="{escape(button_url)}"
                     style="display:inline-block;background:{BLUE};color:#ffffff;
                            text-decoration:none;font-weight:600;font-size:14px;
                            padding:12px 24px;border-radius:8px;">
                    {escape(button_label or 'Open')}
                  </a>
                </td>
              </tr>"""

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{escape(heading)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f0f4f8;font-family:{FONT};">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {escape(preheader or heading)}
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f0f4f8;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width:560px;background:#ffffff;border-radius:12px;
                        overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="background:{NAVY};padding:20px 36px;">
                <span style="color:#ffffff;font-size:18px;font-weight:700;
                             letter-spacing:0.01em;font-family:{FONT};">
                  {BRAND_NAME}
                </span>
                <span style="color:rgba(255,255,255,0.6);font-size:13px;
                             padding-left:8px;font-family:{FONT};">
                  Transport Portal
                </span>
              </td>
            </tr>
            <tr>
              <td style="height:4px;background:{accent};font-size:0;line-height:0;">&nbsp;</td>
            </tr>
            <tr>
              <td style="padding:30px 36px 6px;font-family:{FONT};">
                <p style="margin:0 0 18px;font-size:14px;color:{MUTED};">
                  {escape(greeting)}
                </p>
                <h1 style="margin:0 0 14px;font-size:20px;font-weight:700;
                           color:{INK};line-height:1.35;">
                  {escape(heading)}
                </h1>
                {body_html}
              </td>
            </tr>
            {code_html}
            {details_html}
            {footnote_html}
            {button_html}
            <tr>
              <td style="padding:18px 36px;border-top:1px solid #edf2f7;background:#f8fafc;">
                <p style="margin:0;font-size:12px;color:{FAINT};line-height:1.6;font-family:{FONT};">
                  {BRAND_NAME} Transport Portal<br>
                  This is an automated message. Please do not reply to this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    return text_body, html_body


# ── Sending ──────────────────────────────────────────────────────────────────

def send_email(subject, to_email, **content):
    """Render and send one branded email synchronously. Raises on failure."""
    text_body, html_body = render_email(**content)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")
    return msg.send(fail_silently=False)


def _send_quietly(subject, to_email, content):
    """Background-thread wrapper. Must never raise."""
    try:
        send_email(subject, to_email, **content)
    except Exception:
        logger.exception("Failed to email %s", to_email)


_OTP_COPY = {
    "verify": {
        "subject": f"Your {BRAND_NAME} verification code",
        "heading": "Verify your email address",
        "intro": "Use the code below to finish creating your Fleetcentric.ai account.",
        "ignore": "If you did not sign up, you can safely ignore this email.",
    },
    "reset": {
        "subject": f"Your {BRAND_NAME} password reset code",
        "heading": "Reset your password",
        "intro": "We received a request to reset your password. Use the code below to continue.",
        "ignore": "If you did not request a password reset, ignore this email. Your password will not change.",
    },
    "payment": {
        "subject": f"Your {BRAND_NAME} payment verification code",
        "heading": "Confirm your payment",
        "intro": "Use the code below to confirm your transport fee payment.",
        "ignore": "If you did not start this payment, ignore this email and contact the transport office.",
    },
}


def send_otp_email(to_email, code, purpose="verify", name=None, details=None):
    """
    Send a one-time code. Synchronous; raises on failure so the caller can
    tell the user the email did not go out.
    """
    copy = _OTP_COPY[purpose]
    return send_email(
        copy["subject"],
        to_email,
        heading=copy["heading"],
        paragraphs=[copy["intro"]],
        name=name,
        code=code,
        code_caption="Verification code",
        details=details,
        footnote=f"This code expires in {OTP_TTL_MINUTES} minutes. {copy['ignore']}",
        preheader=f"{code} is your {BRAND_NAME} code. It expires in {OTP_TTL_MINUTES} minutes.",
    )


def send_notification_email(notification):
    """
    Mirror a Notification to the recipient's inbox.

    Returns True if an email was dispatched, False if it was deliberately
    skipped. Never raises.
    """
    try:
        if not getattr(settings, "NOTIFICATION_EMAILS_ENABLED", False):
            return False

        if notification.type in SKIPPED_TYPES:
            return False

        user = notification.user
        if user is None or not user.email:
            return False

        if getattr(settings, "NOTIFICATION_EMAILS_SKIP_STAFF", True) and user.is_staff:
            return False

        portal = _portal_url()
        content = dict(
            heading=notification.title,
            paragraphs=[notification.message],
            name=display_name(user),
            accent=ACCENTS.get(notification.type, BLUE),
            button_label=f"Open {BRAND_NAME}" if portal else None,
            button_url=portal or None,
        )

        threading.Thread(
            target=_send_quietly,
            args=(f"{notification.title} | {BRAND_NAME}", user.email, content),
            daemon=True,
        ).start()
        return True
    except Exception:
        logger.exception("send_notification_email failed for notification %s",
                         getattr(notification, "pk", "?"))
        return False
