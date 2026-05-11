from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
    'PAGE_SIZE': 50,
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
# All values must come from environment — no hardcoded fallbacks.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME':     os.environ['DATABASE_NAME'],
        'USER':     os.environ['DATABASE_USER'],
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST':     os.environ.get('DATABASE_HOST', 'localhost'),
        'PORT':     os.environ.get('DATABASE_PORT', '5432'),
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
DEFAULT_FROM_EMAIL = 'FAST Transport <thundermarks.agency@gmail.com>'

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