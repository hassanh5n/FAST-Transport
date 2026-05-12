"""
Auto-create a superuser from environment variables during deployment.
Skips silently if the user already exists or env vars are missing.

Required env vars on Render:
  DJANGO_SUPERUSER_USERNAME
  DJANGO_SUPERUSER_EMAIL
  DJANGO_SUPERUSER_PASSWORD
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Create a superuser from env vars (idempotent, safe for build scripts)"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not all([username, email, password]):
            self.stdout.write(self.style.WARNING(
                "Skipping superuser creation — set DJANGO_SUPERUSER_USERNAME, "
                "DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD env vars."
            ))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.SUCCESS(
                f"Superuser '{username}' already exists — skipping."
            ))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Superuser '{username}' created successfully."
        ))
