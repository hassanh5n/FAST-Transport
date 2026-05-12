"""
email_backends.py — custom email backend.

DualEmailBackend: sends via SMTP (Brevo) AND prints to console.
If SMTP fails, the exception is printed clearly and re-raised so
the error surfaces in the view rather than being silently swallowed.
"""

from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend
import logging

logger = logging.getLogger(__name__)


class DualEmailBackend(SMTPBackend):
    """
    Send via SMTP and also print to the console.

    SMTP failures are logged and re-raised — this makes misconfiguration
    immediately visible rather than silently dropped.
    """

    def send_messages(self, email_messages):
        # Always print to console so the OTP is visible during development
        # even when SMTP is broken.
        console_backend = ConsoleBackend()
        console_backend.send_messages(email_messages)

        # Now actually send via SMTP.
        try:
            result = super().send_messages(email_messages)
            logger.info("DualEmailBackend: sent %d message(s) via SMTP", result)
            return result
        except Exception as exc:
            # Print a clear diagnostic — the old version swallowed this silently.
            logger.error(
                "\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "  SMTP SEND FAILED\n"
                "  %s\n"
                "  Check:\n"
                "    1. EMAIL_HOST_PASSWORD is set in your .env\n"
                "    2. Brevo SMTP key is valid (Brevo → SMTP & API)\n"
                "    3. Port 587 isn't blocked by your firewall/Docker\n"
                "    4. Run: python test_email.py you@example.com\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                exc,
            )
            raise  # surface the error to the caller / view