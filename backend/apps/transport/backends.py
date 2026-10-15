from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from .models import StudentProfile


class RollNumberBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Try matching roll_number first (students)
        try:
            profile = StudentProfile.objects.select_related("user").get(roll_number=username)
            user = profile.user
        except StudentProfile.DoesNotExist:
            # Fall back to actual username (keeps admin login working)
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None
        identifier = username.strip()
        if "@" in identifier:
            candidates = User.objects.filter(email__iexact=identifier)
        else:
            candidates = User.objects.filter(username=identifier)
        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None
