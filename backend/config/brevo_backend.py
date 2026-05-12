"""
Brevo HTTP API email backend.

Uses Brevo's REST API (https://api.brevo.com) over HTTPS port 443
instead of SMTP port 587, which is blocked on Render's free tier.

Requires env var: BREVO_API_KEY (your Brevo API key, NOT the SMTP key).
"""

import requests as req_lib
import logging
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoAPIEmailBackend(BaseEmailBackend):
    """
    Send emails via Brevo's HTTP API instead of SMTP.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "BREVO_API_KEY", "")

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for msg in email_messages:
            try:
                payload = {
                    "sender": self._parse_email(msg.from_email),
                    "to": [self._parse_email(addr) for addr in msg.to],
                    "subject": msg.subject,
                    "textContent": msg.body,
                }

                if msg.alternatives:
                    for content, mimetype in msg.alternatives:
                        if mimetype == "text/html":
                            payload["htmlContent"] = content

                resp = req_lib.post(
                    BREVO_API_URL,
                    json=payload,
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
                    logger.error(
                        "Brevo API error %s: %s", resp.status_code, resp.text
                    )
                    if not self.fail_silently:
                        raise Exception(
                            f"Brevo API error {resp.status_code}: {resp.text}"
                        )

            except Exception as e:
                logger.error("Brevo API send failed: %s", e)
                if not self.fail_silently:
                    raise

        return sent

    @staticmethod
    def _parse_email(email_str):
        """Parse 'Name <email>' format into {name, email} dict."""
        if "<" in email_str and ">" in email_str:
            name = email_str.split("<")[0].strip()
            email = email_str.split("<")[1].rstrip(">").strip()
            return {"name": name, "email": email}
        return {"email": email_str.strip()}
