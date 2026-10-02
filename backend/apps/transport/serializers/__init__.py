"""DRF serializers, one module per area. Import from `apps.transport.serializers` as before."""
from .core import *  # noqa: F401,F403
from .routes import *  # noqa: F401,F403
from .fleet import *  # noqa: F401,F403
from .registration import *  # noqa: F401,F403
from .fees import *  # noqa: F401,F403
from .support import *  # noqa: F401,F403
