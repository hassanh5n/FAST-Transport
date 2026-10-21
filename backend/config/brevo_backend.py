"""
Brevo HTTP API email backend.

Uses Brevo's REST API (https://api.brevo.com) over HTTPS port 443
instead of SMTP port 587, which is blocked on Render's free tier.

Requires env var: BREVO_API_KEY (your Brevo API key, NOT the SMTP key).

Kept in parity with Django's SMTP backend so production mail looks the same
as local mail: same sender name, same text and HTML parts, reply-to/cc/bcc
passed through.
"""

import logging
from email.utils import getaddresses, parseaddr

import requests as req_lib
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _contact(addr):
    """'"Name" <a@b.c>' -> {"name": "Name", "email": "a@b.c"} (quotes stripped)."""
    name, email = parseaddr(addr)
    contact = {"email": email or addr.strip()}
    if name:
        contact["name"] = name
    return contact


def _contacts(addrs):
    return [{"email": e, **({"name": n} if n else {})} for n, e in getaddresses(addrs or [])]


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Send emails via Brevo's HTTP API instead of SMTP."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", "")

    def _payload(self, msg):
        payload = {
            "sender": _contact(msg.from_email or settings.DEFAULT_FROM_EMAIL),
            "to": _contacts(msg.to),
            "subject": msg.subject,
            "textContent": msg.body,
        }
        if msg.cc:
            payload["cc"] = _contacts(msg.cc)
        if msg.bcc:
            payload["bcc"] = _contacts(msg.bcc)
        if msg.reply_to:
            payload["replyTo"] = _contact(msg.reply_to[0])
        if msg.extra_headers:
            payload["headers"] = dict(msg.extra_headers)

        for content, mimetype in getattr(msg, "alternatives", None) or []:
            if mimetype == "text/html":
                payload["htmlContent"] = content
        if getattr(msg, "content_subtype", "plain") == "html":
            payload["htmlContent"] = msg.body
        return payload

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for msg in email_messages:
            try:
                resp = req_lib.post(
                    BREVO_API_URL,
                    json=self._payload(msg),
                    headers={
                        "api-key": self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    sent += 1
                    logger.info("Brevo API: sent email to %s", msg.to)
                else:
                    logger.error("Brevo API error %s: %s", resp.status_code, resp.text)
                    if not self.fail_silently:
                        raise Exception(f"Brevo API error {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error("Brevo API send failed: %s", e)
                if not self.fail_silently:
                    raise

        return sent
