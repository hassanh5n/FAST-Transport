from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Allow the React dev server
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]

# In dev, use the console email backend so you don't need SMTP running
# Comment this out when you want to test real email delivery locally.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'