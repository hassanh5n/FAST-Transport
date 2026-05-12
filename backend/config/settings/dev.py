from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Allow the React dev server
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' (for console only)

EMAIL_BACKEND = 'config.email_backends.DualEmailBackend' # (for both console and real email)