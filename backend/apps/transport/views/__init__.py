"""API views, one module per area. Import from `apps.transport.views` as before."""
import requests as req_lib  # noqa: F401  (tests patch apps.transport.views.req_lib.get)

from .maps import *  # noqa: F401,F403
from .maps import _valid_karachi_coordinate, _map_cache_key, _is_line_string, _is_straight_fallback, _road_geometry, _display_route_geometry  # noqa: F401
from .auth import *  # noqa: F401,F403
from .students import *  # noqa: F401,F403
from .routes import *  # noqa: F401,F403
from .fleet import *  # noqa: F401,F403
from .registration import *  # noqa: F401,F403
from .fees import *  # noqa: F401,F403
from .fees import _mark_seat_confirmed  # noqa: F401
from .complaints import *  # noqa: F401,F403
from .notifications import *  # noqa: F401,F403
from .dashboard import *  # noqa: F401,F403
from .tracking import *  # noqa: F401,F403
from .tracking import _parse_tracker_timestamp, _location_status, _fetch_tracker_location, _serialize_fleet_bus  # noqa: F401
from .incidents import *  # noqa: F401,F403
from .driver import *  # noqa: F401,F403
from .driver import _driver_for, _driver_assignment, _haversine_m, _route_legs, _stop_etas  # noqa: F401
