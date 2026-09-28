"""
Email delivery for in-app notifications.

Every Notification row created anywhere in the codebase is mirrored to the
recipient's inbox by a single post_save receiver in signals.py, so new
notification sites get email for free without touching this module.

Design notes (deliberate, given this project has no Celery/queue):

  * Sending happens on a short-lived background thread. A slow or failing
    Brevo call must never delay — or 500 — a student's registration request.
  * Failures are swallowed and logged. Email is best-effort; the in-app
    notification is the source of truth and is already committed by the time
    we get here.
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

# Notification.type values that should never generate an email.
SKIPPED_TYPES = {"alert"}


def _portal_url():
    return getattr(settings, "FRONTEND_URL", "") or ""


def _build_html(notification, recipient_name):
    """Branded HTML body. Table-based layout — email clients are not browsers."""
    title = escape(notification.title)
    message = escape(notification.message).replace("\n", "<br>")
    greeting = escape(recipient_name) if recipient_name else "there"
    portal = _portal_url()

    accent = {
        "info": "#288dc4",
        "warning": "#f59e0b",
        "alert": "#ef4444",
    }.get(notification.type, "#288dc4")

    button = ""
    if portal:
        button = f"""
          <tr>
            <td style="padding:8px 32px 32px;">
              <a href="{escape(portal)}"
                 style="display:inline-block;background:#288dc4;color:#ffffff;
                        text-decoration:none;font-weight:600;font-size:14px;
                        padding:11px 22px;border-radius:8px;">
                Open Fleetcentric.ai
              </a>
            </td>
          </tr>
        """

    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f0f4f8;
               font-family:'DM Sans',Segoe UI,system-ui,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f0f4f8;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width:560px;background:#ffffff;border-radius:12px;
                        overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="background:#0b2d42;padding:18px 32px;">
                <div style="color:rgba(255,255,255,0.55);font-size:11px;
                            letter-spacing:0.08em;text-transform:uppercase;">
                  Fleetcentric.ai
                </div>
                <div style="color:#ffffff;font-size:18px;font-weight:700;
                            margin-top:2px;">
                  Transport
                </div>
              </td>
            </tr>
            <tr>
              <td style="height:4px;background:{accent};font-size:0;">&nbsp;</td>
            </tr>
            <tr>
              <td style="padding:28px 32px 8px;">
                <p style="margin:0 0 16px;font-size:14px;color:#4a6178;">
                  Hi {greeting},
                </p>
                <h1 style="margin:0 0 12px;font-size:19px;font-weight:700;
                           color:#0f1f2d;line-height:1.35;">
                  {title}
                </h1>
                <p style="margin:0;font-size:14.5px;color:#0f1f2d;line-height:1.65;">
                  {message}
                </p>
              </td>
            </tr>
            {button}
            <tr>
              <td style="padding:18px 32px;border-top:1px solid #edf2f7;
                         background:#f8fafc;">
                <p style="margin:0;font-size:11.5px;color:#8faabb;line-height:1.6;">
                  This is an automated message from the Fleetcentric.ai portal.
                  Please do not reply to this email.
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


def _send(subject, text_body, html_body, to_email):
    """Runs on a background thread. Must never raise."""
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
    except Exception:
        # Best-effort: the in-app notification is already saved, so a failed
        # email is a degraded experience, not a lost one.
        logger.exception("Failed to email notification to %s", to_email)


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

        recipient_name = (user.first_name or "").strip() or user.username
        subject = f"[Fleetcentric.ai] {notification.title}"
        text_body = (
            f"Hi {recipient_name},\n\n"
            f"{notification.title}\n\n"
            f"{notification.message}\n"
        )
        portal = _portal_url()
        if portal:
            text_body += f"\nOpen the portal: {portal}\n"
        text_body += (
            "\n---\nThis is an automated message from the Fleetcentric.ai portal. "
            "Please do not reply.\n"
        )

        html_body = _build_html(notification, recipient_name)

        threading.Thread(
            target=_send,
            args=(subject, text_body, html_body, user.email),
            daemon=True,
        ).start()
        return True
    except Exception:
        logger.exception("send_notification_email failed for notification %s",
                         getattr(notification, "pk", "?"))
        return False
