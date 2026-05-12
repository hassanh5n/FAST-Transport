from .base import *
import dj_database_url

DEBUG = False

# Render sets RENDER_EXTERNAL_HOSTNAME automatically
ALLOWED_HOSTS = [
    os.environ.get('RENDER_EXTERNAL_HOSTNAME', ''),
    os.environ.get('DJANGO_ALLOWED_HOST', ''),
]
# Remove empty strings
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]

# Frontend URL for CORS (Vercel domain)
CORS_ALLOWED_ORIGINS = [
    os.environ.get('FRONTEND_URL', 'http://localhost:5173'),
]

# ── Database (Neon / Render Postgres via DATABASE_URL) ────────────────────────
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config(
        default=os.environ['DATABASE_URL'],
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )

# ── Static files (WhiteNoise serves them without Nginx) ──────────────────────
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── HTTPS / security headers ─────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER       = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT           = False  # Render handles SSL termination
SESSION_COOKIE_SECURE         = True
CSRF_COOKIE_SECURE            = True
SECURE_HSTS_SECONDS           = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF   = True
X_FRAME_OPTIONS               = 'DENY'