"""
One-time codes for signup, password reset and fee payment.

Two rules every caller gets for free:
  * codes come from `secrets`, not `random` (which is predictable);
  * a code allows MAX_ATTEMPTS wrong guesses, then it is dead and a new one
    must be requested. A 6-digit code with unlimited guesses can be brute
    forced inside its 10-minute window.
"""
import secrets

from django.db.models import F
from django.utils import timezone

from .models import OTPVerification

MAX_ATTEMPTS = 5


def generate_otp():
    return f"{secrets.randbelow(10**6):06d}"


def check_otp(record, code):
    """
    Return None if `code` is right for `record`, otherwise a user-facing error.

    An attempt is reserved with a conditional UPDATE before comparing, so
    parallel requests cannot squeeze in more than MAX_ATTEMPTS guesses.
    """
    if record is None:
        return "Invalid or expired code. Request a new one."
    if record.is_used or timezone.now() > record.expires_at:
        return "This code has expired. Request a new one."

    reserved = OTPVerification.objects.filter(
        pk=record.pk, failed_attempts__lt=MAX_ATTEMPTS
    ).update(failed_attempts=F("failed_attempts") + 1)
    if not reserved:
        return "Too many wrong attempts. Request a new code."

    if not secrets.compare_digest(str(record.otp), str(code)):
        return "Incorrect code. Check the email and try again."

    # Right code: the reserved attempt does not count against the user.
    OTPVerification.objects.filter(pk=record.pk).update(failed_attempts=F("failed_attempts") - 1)
    return None
