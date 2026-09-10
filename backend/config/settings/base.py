from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR.parent / ".env")

# ── Security ──────────────────────────────────────────────────────────────────
# No fallback — if this env var is missing, the app must not start.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False  # overridden per environment

ALLOWED_HOSTS = []  # overridden per environment

# ── Installed apps ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'apps.transport',
    'rest_framework',
    'rest_framework_simplejwt',
]

# ── REST Framework ────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Pagination — prevents timeout on large datasets
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 500,
}

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ]},
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
# Default config for local development.
# In production, prod.py overrides this entirely via DATABASE_URL.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     os.environ['DATABASE_NAME'],
        'USER':     os.environ['DATABASE_USER'],
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST':     os.environ.get('DATABASE_HOST', 'localhost'),
        'PORT':     os.environ.get('DATABASE_PORT', '5432'),
        'OPTIONS': {'sslmode': 'require'},
    }
}

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL  = '/static/'

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_BACKEND      = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST         = 'smtp-relay.brevo.com'
EMAIL_PORT         = 587
EMAIL_USE_TLS      = True
EMAIL_HOST_USER    = 'a8d609001@smtp-brevo.com'
EMAIL_HOST_PASSWORD = os.environ['EMAIL_HOST_PASSWORD']
DEFAULT_FROM_EMAIL = 'FAST-Transport <hassannafees.4017@gmail.com>'

# ── Notification emails ──────────────────────────────────────────────────────
# Every Notification row is mirrored to the recipient's inbox (see
# apps/transport/emails.py). Off by default so nothing sends until a settings
# module opts in — dev leaves it off so local testing does not consume the
# Brevo free-tier daily quota that signup OTPs also draw from.
NOTIFICATION_EMAILS_ENABLED = False

# Skip staff recipients. Admin-facing notifications (fee-payment fan-out, the
# off-route geofence alert fired on every GPS ping) are high volume and would
# exhaust the daily email quota.
NOTIFICATION_EMAILS_SKIP_STAFF = True

# Link target in the email body. Overridden per environment.
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')

# ── Maps providers ──────────────────────────────────────────────────────────
# Override these in deployment to use an institution-approved or self-hosted
# OSRM/Nominatim-compatible service. The browser never receives these URLs.
MAP_ROUTING_URL = os.environ.get('MAP_ROUTING_URL', 'https://router.project-osrm.org').rstrip('/')
MAP_GEOCODING_URL = os.environ.get('MAP_GEOCODING_URL', 'https://nominatim.openstreetmap.org').rstrip('/')
MAP_GEOCODING_USER_AGENT = os.environ.get('MAP_GEOCODING_USER_AGENT', 'FAST-Transport/1.0')

# ── Crime-risk map (separate from student Incident reports) ────────────────
# The feed must be an institution-approved/licensed GeoJSON or JSON endpoint;
# no public endpoint is assumed because CPLC/Sindh Police publish aggregate
# statistics rather than geocoded events.
CRIME_RISK_FEED_URL = os.environ.get('CRIME_RISK_FEED_URL', '').strip()
CRIME_RISK_FEED_TOKEN = os.environ.get('CRIME_RISK_FEED_TOKEN', '').strip()
CRIME_RISK_FEED_SOURCE_NAME = os.environ.get('CRIME_RISK_FEED_SOURCE_NAME', 'external-crime-feed')
CRIME_RISK_WINDOW_DAYS = int(os.environ.get('CRIME_RISK_WINDOW_DAYS', '90'))
CRIME_RISK_CELL_DEGREES = float(os.environ.get('CRIME_RISK_CELL_DEGREES', '0.005'))
# min_lat,min_lng,max_lat,max_lng; keep the extent limited to the Karachi
# service area so a misconfigured feed cannot create a world-sized grid.
CRIME_RISK_BBOX = os.environ.get('CRIME_RISK_BBOX', '24.60,66.70,25.35,67.50')

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set in dev.py / prod.py — never allow all in base.
CORS_ALLOW_ALL_ORIGINS = False

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps.transport': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# ── JWT ───────────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
