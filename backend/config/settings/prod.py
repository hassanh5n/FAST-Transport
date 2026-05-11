from .base import *

DEBUG = False

# Set DJANGO_ALLOWED_HOST to your actual domain, e.g. transport.nu.edu.pk
ALLOWED_HOSTS = [os.environ['DJANGO_ALLOWED_HOST']]

# Set FRONTEND_URL to your deployed frontend URL, e.g. https://transport.nu.edu.pk
CORS_ALLOWED_ORIGINS = [os.environ['FRONTEND_URL']]

# ── HTTPS / security headers ─────────────────────────────────────────────────
# Nginx terminates SSL, so Django sees HTTP internally.
# These settings tell Django the connection is actually HTTPS.
SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT           = True
SESSION_COOKIE_SECURE         = True
CSRF_COOKIE_SECURE            = True
SECURE_HSTS_SECONDS           = 31536000   # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF   = True
X_FRAME_OPTIONS               = 'DENY'