## Project overview

FleetCentric.ai: a transport management system for FAST NUCES Karachi shuttles. Students register each semester, get a seat on a route, pay a fee challan and track their bus; admins run the fleet; drivers run trips. Django REST backend + React (Vite) frontend, one Postgres database.

### Layout
- `backend/` - Django 6 + DRF. Settings in `config/settings/{base,dev,prod}.py`; run with `--settings=config.settings.dev`. All app code is one app: `backend/apps/transport/`.
- `frontend/` - React 19 + Vite PWA, React Router, TanStack Query, MapLibre GL, Recharts.
- `docs/` - `api_spec.md`, `database_schema.md`, `PERF.md`, and `fleetcentric_ai_routing_optimization_context.md` (the research optimizer plan).
- `nginx/`, `docker-compose*.yml` - containerised db/backend/frontend. Ignore `backend/venv/`, `backend/staticfiles/`, `backups/` and `*.dump`.

### Backend (`backend/apps/transport/`)
- `models/` - one module per area, all re-exported from `models/__init__.py`:
  - `core.py`: StudentProfile, Semester, Contractor, Route, Stop, RouteStop (stop order + morning/evening ETAs), Bus, Driver, RouteAssignment (bus + driver on a route per semester), MaintenanceSchedule
  - `registration.py`: SemesterRegistration, TransportRegistration, SeatAllocation, Waitlist, RouteChangeRequest
  - `fees.py`: FeeVerification, Challan · `support.py`: Complaint, Notification, OTPVerification, Incident
  - `tracking.py`: BusLocationPing · `crime.py`: crime-risk zones · `plans.py`: RoutePlan · `admin_rbac.py`: AdminRole, AdminProfile, AdminActivityLog
- `views/` (one module per area) and `serializers/` mirror the models. `urls.py` registers DRF viewsets plus function views; everything is mounted under `/api/` by `config/urls.py`. JWT via SimpleJWT (`/api/token/`, `/api/token/refresh/`).
- Domain logic lives in top-level modules, not in views: `auto_assign.py` + `seatallocation.py` (route/seat assignment, waitlist), `route_plans.py` (import/export/activate hand-made route plans), `route_order.py`, `corridor.py`, `road_lines.py` (OSRM road geometry), `traffic.py`, `crime_risk.py`, `geofencing.py`, `transport_card.py` (PDF card), `fleet_import.py` / `stop_import.py` (Excel imports), `emails.py` + `otp.py` (Brevo SMTP).
- Access control: `permissions.py` (student/driver/staff), `rbac.py` (per-module admin roles, superadmin), `audit.py` (activity log). `authentication.py` does one shared user lookup per request.
- Management commands in `management/commands/` (crime-risk refresh, seat-offer expiry, stop-order repair).
- Tests are `test_*.py` beside the code: `python manage.py test apps.transport --settings=config.settings.dev`.

### Frontend (`frontend/src/`)
- `App.jsx` holds all routes, split by role guard: `StudentRoute` (`/student/*`), `DriverRoute` (`/driver/*`), `StaffRoute module="..."` (`/admin/*`, gated per RBAC module; `superOnly` for admin management).
- `pages/{student,admin,driver,auth}/` are screens; `components/` shared UI (`PageShell.jsx`, `ui.jsx`, `Table.jsx`) and `components/maps/` (MapLibre maps, traffic, incidents).
- `services/api.js` is the axios client: base URL `VITE_API_BASE_URL`, bearer token from `localStorage.access`, auto-refresh, and it unwraps DRF pagination so callers always get arrays. `services/transportService.js` has one function per backend endpoint (`getBuses` -> `GET /api/buses/`), so it is the bridge between a page and a view: page -> transportService function -> `/api/<path>` -> `urls.py` -> view in `views/`.
- `utils/permissions.js` mirrors backend RBAC modules for showing/hiding UI.

### Things to know
- Local dev points at the shared hosted Postgres; do not write test data without asking.
- The research optimizer (School Bus Routing Problem solver) is not built yet; `route_plans.py` is where proposals would plug in.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- Use the graph where it pays off: broad questions ("how does seat allocation work"), "what calls X / what does X call", and tracing a page through to the backend. There, start with `graphify query "<question>"`, `graphify explain "<concept>"` or `graphify path "<A>" "<B>"`; they return a scoped subgraph that is usually much smaller than grep output. When you already know the symbol, file or string, grep or read it directly. Mention the graph in subagent prompts that explore code broadly.
- A `graphify path` result is the shortest route through the graph, not necessarily the real call chain. Confirm it in the code before relying on it.
- Short names are often ambiguous (`Route` exists in models, tests and docs). Use `path::symbol`, e.g. `graphify explain "backend/apps/transport/models/core.py::Route"`.
- Frontend API calls are linked to the Django view or `@action` they hit by `calls_api` edges (e.g. `getRouteMapDetail()` -> `RouteViewSet.map_detail()`), so `graphify path` from a page to backend code works. graphify does not make these itself: `python scripts/graphify_api_links.py` adds them, and rebuilds keep them. Rerun it after adding or renaming an endpoint or a service function.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing. The git hooks do not refresh it; run `graphify export wiki` after a large change.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- graphify-out/ is gitignored, so each clone builds its own graph. If it is missing, run `graphify update .` (AST-only, no API cost). Git hooks installed with `graphify hook install` rebuild it after each commit, checkout and merge; still run `graphify update .` after uncommitted code changes you want queries to see.
