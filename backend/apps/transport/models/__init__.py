"""Database models, one module per area. Import from `apps.transport.models` as before."""
from django.contrib.auth.models import User  # noqa: F401  (signals.py imports User from here)

from .core import *  # noqa: F401,F403
from .registration import *  # noqa: F401,F403
from .fees import *  # noqa: F401,F403
from .support import *  # noqa: F401,F403
from .tracking import *  # noqa: F401,F403
from .crime import *  # noqa: F401,F403
from .admin_rbac import *  # noqa: F401,F403
