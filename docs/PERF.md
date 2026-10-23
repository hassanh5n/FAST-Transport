# Performance log

Every speed change tried, kept or not, with the numbers that decided it. Read this
before proposing a performance change, so an idea that already failed is not tried again.

## How it was measured

- The database is hosted on Supabase. From a development PC one query takes about
  **170 ms** there and back, and data comes back at about **60 KB/s**. So the number of
  queries per request, and the bytes they pull, decide almost every timing below.
- Backend: Django test client against the real database, read-only GETs, cache cleared
  first. Query counts come from `CaptureQueriesContext`; they do not vary between runs,
  timings do (±300 ms is normal), so query counts were the deciding number.
- Write paths: the test suite run with every request's queries counted, on the throwaway
  test database, never on live data.
- Frontend: production build, served locally; the service worker was checked in headless Edge.

## Kept

| Change | Before → after | Where |
|---|---|---|
| Route stops: route, stop and active assignment loaded with the rows | `/api/routestops/` 2,858 queries, **9 min 23 s** → 3 queries, 2.3 s | `RouteStopViewSet`, `RouteStopSerializer` |
| Road lines (`Route.geometry`, ~4 KB a route) no longer loaded or returned where unused | `eligible-route-stops` 25 s → 3.3 s; `/api/routes/` 202 KB → 2 KB; assignments 260 KB → 7 KB | `.defer("route__geometry")` on route joins; `RouteSerializer` geometry write-only |
| Waitlist overview: assignments and seat counts in one query | 107 queries, 24 s → 3 queries, 1.1 s | `WaitlistViewSet.overview` |
| Admin dashboard: 8 counts in one query | 8 → 1 query | `views/dashboard.py _counts` |
| Student dashboard: fewer lookups | 15 → 11 queries, 2.6 s → 1.7 s | `DashboardView` |
| Routes map cached under a fingerprint of its rows, ETag + 304 | ~610 ms, 45 KB → ~200 ms; 304 with an empty body | `RouteViewSet.map` |
| Live fleet: semester filtered in the prefetch | 4 → 3 queries per 8 s poll, ~865 → ~745 ms | `admin_live_fleet` |
| One JWT user lookup per request, profiles joined | `/api/user/` 4 queries → 1 (~650 → ~165 ms); 1–3 fewer on every other request | `authentication.SharedJWTAuthentication` |
| Lists skip `COUNT(*)` when they fit on one page | one fewer query on every list; responses byte-identical | `pagination.OnePageNumberPagination` |
| Complaints, drivers, admin roles: related rows joined, not fetched per row | 6 → 2, 4 → 2, 8 → 2 queries | their viewsets |
| Route change requests: seat counts once per list | 7 → 3 queries | `RouteChangeRequestViewSet` |
| Seat checks count every bus in one query | registration 38 → 34, fee verify 30 → 29 (grows with buses per route) | `seatallocation._buses_emptiest_first` |
| Login response carries the user | one request fewer at sign-in | `LoggedTokenObtainPairView`, login/OTP pages |
| Saved copies (IndexedDB) shown first, refreshed after | dashboard on screen at 1.5 s with a 4 s-per-request network | `api.getSWR`, `queryClient.js` |
| Service worker: app shell + OpenFreeMap tiles | map tile 309 ms → 4 ms on repeat; app opens offline | `vite.config.js` |
| Dashboard maps lazy-loaded; traffic map no longer pulls MapLibre | ~285 KB gzipped off the dashboard's first load | `dashboard.jsx`, `campusLocation.js` |
| Google Fonts linked from `index.html` instead of a CSS `@import` | removes a three-step download chain before text shows | `index.html` |
| Index on location pings `(bus, -recorded_at)` | latest-ping lookup stops scanning every ping (table empty today) | migration `0031`, **not yet applied to Supabase** |

## Considered and not done

| Idea | Why not |
|---|---|
| Prefetch registration's eligible stops before the semester list arrives | Saves ~0.5 s for unregistered students but makes every registered student run a 3 s query they never use. |
| Cache the user lookup across requests | Saves one query, but a deactivated account would keep access until the cache expired. |
| Leave road lines out of `/api/route-plans/` | Its fingerprint (which keys the plan thumbnails) is built from them. |
| Rewrite plan preview/activation (54–57 queries) | Already set-based; the count does not grow with data, and admins run it rarely. |
| Merge the remaining checks in registration and fee verification | Each is a separate business rule; merging risks behaviour changes for ~0.5 s. |
| Cache Google's traffic tiles | Google's terms forbid it, and live traffic must be fresh. |

## Outside the code

- Host the production backend in the **same region as the Supabase project**. Most of
  the time above is the distance between the server and the database.
- Development uses no persistent database connections (Supabase's pooler allows 15), so
  each dev request also pays for a new connection. Production (`prod.py`) keeps them.
