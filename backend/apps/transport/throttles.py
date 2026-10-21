"""Rate limits for login, signup and one-time-code endpoints. Rates live in settings."""
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class AuthRateThrottle(SimpleRateThrottle):
    """Per client IP, signed in or not: login, signup, OTP verify/resend, password reset."""
    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class OtpRateThrottle(UserRateThrottle):
    """Per signed-in user: fee payment OTP start and verify."""
    scope = "otp"
