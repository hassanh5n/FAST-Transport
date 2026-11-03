# FleetCentric.ai — Product Demo Creative Brief

Pre-production analysis for the demo video. No Remotion code yet.
Evidence base: the `FAST-Transport` repo (backend `apps/transport`, frontend `src/pages`, `docs/`), the one-page abstract, the standee, the approved logo pack, and a live walkthrough of https://fleetcentric-ai.vercel.app as admin, student (route 6B) and driver (Rizwan, bus ABC-123) on 28 Sep 2026.

---

## A. Product understanding

FleetCentric.ai digitises the full operating cycle of an institution's fixed-route shuttle fleet. The pilot is the FAST-NUCES Karachi transport office (about 1,000 registered students and 30 buses).

It covers one semester's loop:

1. **Register.** A student picks their pickup stop on a map. The system chooses the route (`pick_route_for_stop`).
2. **Seat or queue.** If the bus has room, the student gets a seat. If it's full, they join that route's waitlist and **no fee is issued** (`seatallocation.py`).
3. **Pay.** A challan is issued only when a seat is actually held. The student pays through the Stripe test flow plus an email OTP, or the admin verifies payment. Either way the registration is approved and the seat confirmed.
4. **Auto-promote.** When a seat frees up (cancellation, admin deletion or an expired offer), the next student in the queue is promoted automatically. They get a challan, a payment deadline and an in-app notification that is also emailed (`signals.py` post_delete → `promote_next_from_waitlist`).
5. **Ride.** The driver's phone acts as the bus tracker. It sends GPS every 15 s, gets live ETAs for each stop, and ticks stops off automatically within 120 m (`DriverTrip.jsx`, `driver_location`).
6. **Watch.** Students see their bus on a live map, refreshed every 8 s. Admins see a Live Fleet map covering every bus, merging a hardware tracker feed (iTecknologi API), phone pings and stale/offline states. If a bus strays more than 1 km from its route's stops, the admins who handle fleet get an off-route alert.
7. **Govern.** Admins handle complaints, incident reports (students pin them on a map; they go public after admin approval), route-change requests and CSV exports. Access is split into 10 modules, each set to none, view or manage, and a field-level audit log records every admin change.

Three portals: **Student**, **Driver** (phone-first) and **Admin** (a super admin plus sub-admins with scoped access).

## B. Target audience

| Audience | What they need from the video |
|---|---|
| **Primary: FYP evaluators, supervisor, FAST faculty** | Proof that the system is real and complete, with non-trivial engineering and a credible research direction |
| **Secondary: institutional buyers** (university transport offices, school and corporate shuttle operators) | "This replaces our paper registers, spreadsheets and phone calls" |
| **Tertiary: startup audience** (competitions, incubators, LinkedIn) | A clear problem, a working product, a path to multi-tenant SaaS |

Recommendation: cut **one** master video for the buyer-plus-evaluator audience, then derive a short social cut from it.

## C. Core value proposition

**"One system for the whole semester of campus transport — from picking a stop to seeing your bus arrive."**

Supporting proof points, all from the code:

- Students pick a stop, not a route, and the system seats them.
- Nobody pays for a seat that doesn't exist. The waitlist fills itself.
- A driver's phone becomes a live tracker. No hardware is required, though hardware trackers are also supported.
- Admins see the whole fleet, and every admin action is on the record.

## D. Top features (ranked for demo value)

| # | Feature | Why it matters | Evidence |
|---|---|---|---|
| 1 | **Waitlist auto-promotion** | The strongest before/after moment. It's "intelligent", visible and unique. | `seatallocation.py` (`promote_next_from_waitlist`), `signals.py` (`promote_waitlist_on_seat_release`), `AdminWaitlist.jsx` |
| 2 | **Stop-first registration with auto route choice** | Picks the route with the most free seats, or the shortest queue if all are full | `pick_route_for_stop`, `registeration.jsx` ("Choose your route and stop on the map") |
| 3 | **Driver phone → live trip** | Very visual: live ETAs, auto-ticking stops, morning/evening direction | `DriverTrip.jsx`, `driver_location`, `_stop_etas` (OSRM legs, with a fallback estimate) |
| 4 | **Live Fleet map + fleet health** | The "control room" shot | `LiveFleetMap.jsx`, `admin_live_fleet`, `DashboardCharts.jsx` (Fleet health, Route capacity, Admin attention) |
| 5 | **Off-route geofence alert** | A dramatic beat that only reaches admins with the fleet module | `geofencing.py` (1 km), `check_bus_geofence` |
| 6 | **Route Builder** | Click stops, reorder them, set AM/PM ETAs, and see the road-following line appear | `RouteBuilder.jsx`, `preview_route_geometry` (OSRM, 7-day cache, straight-line fallback) |
| 7 | **Fee flow → digital transport card** | A satisfying payoff: an "Approved" state and a card with the seat number | `ChallanPage.jsx` (Stripe test + OTP), `verify_fee`, student dashboard card, `download_transport_card` (PDF) |
| 8 | **RBAC + activity log** | Enterprise credibility in a 3-second flash | `rbac.py`, `middleware.py`, `audit.py`, "Admins & Roles", "Activity Logs" |
| 9 | Incidents on the map | A good supporting beat for the student map | `StudentIncidents.jsx`, `approved_incidents` |
| 10 | Notifications mirrored to email | Mention it in narration only | `email_notification_to_user` signal (Brevo) |

## E. Best demo workflow

Follow **one fictional student through one semester**, with the driver and admin as the system around her. Every scene continues the same story, so there are no disconnected feature tours.

1. Student registers → picks a stop on the map → the route is chosen for her
2. Bus 5B is full → she's **#1 on the waiting list**, with no challan
3. Admin frees a seat → she is **auto-promoted**: the seat is held, a challan is issued, the clock starts, and a notification arrives
4. She pays (test mode) → Approved → a transport card with her seat number
5. Morning: driver taps **Start trip** → live ETAs, stops ticking off
6. Her Live Bus Map shows the bus approaching her stop
7. Admin Live Fleet: all buses live → one goes off route → alert
8. Control room close: charts, RBAC, activity log

The live data already fits this story: **route 5B's bus DEF-456 has capacity 2, with 2/2 taken and 1 waiting**. That's a ready-made "bus is full" scene.

## F. Visual story opportunities

| Moment | Treatment |
|---|---|
| **Opening "paper" problem** | Kinetic type of the standee's four pains: paper registration, seats counted by hand, fees checked by hand, no live bus location. Each gets a red ✕ that flips to a teal ✓ later in the video. |
| **Stop → route** | Map zoomed on Karachi. A pin drops on the stop, then the matching route polyline draws itself (real geometry from `/api/routes/map/`). |
| **Bus full → queue** | A seat-grid graphic (bus 5B, 2 of 2 seats filled). A student token slides into a queue slot marked "#1". |
| **Auto-promotion (hero beat)** | A seat token pops out, the queue token slides forward into it, and three UI chips cascade in: Seat Held → Challan issued → "A seat is now available for you" notification. Slow this beat down. It's the emotional peak. |
| **Card reveal** | The dashboard's navy transport card flips in with SEAT #N. |
| **Phone + laptop split** | Driver phone (Live Trip) on the left, student laptop map on the right. The same bus moves on both. |
| **Off-route** | The map desaturates, the bus drifts, a red 1 km ring pulses, and an alert toast drops into the admin's bell. |
| **Control room** | A slow push across the admin dashboard, then a quick montage of chart bars growing, the RBAC matrix and activity-log rows. |

## G. Technical story opportunities

Keep these to one fast "under the hood" beat (8–12 s) plus narration. Don't do a code tour.

- **Real maps on open infrastructure:** MapLibre GL + OpenFreeMap tiles + OSRM road routing. No paid map API.
- **Event-driven seat logic:** freeing a seat triggers promotion after the database commit. Promotion is suppressed during a reassignment so a student can't lose their seat mid-move.
- **Resilient live data:** positions come from a hardware tracker, then phone GPS, then stale/offline states. ETAs fall back to a distance estimate when OSRM is down, and the route line falls back to straight segments.
- **Central RBAC:** one middleware enforces 10 modules × none/view/manage on every endpoint, and every admin write is audited with a field-level diff.
- **Low-cost stack:** Django 6 + DRF, React 19 + Vite, PostgreSQL (Supabase), deployed on Vercel + Render free tiers with push-to-deploy. This ties directly to the research aim of optimisation that runs on low-cost hosting.
- **Tested:** 64 backend test cases (`tests.py`, `test_admin_rbac.py`, `test_crime_risk.py`).
- **Research roadmap, clearly labelled as future work:** route optimisation modelled as a School Bus / Vehicle Routing Problem, and ML forecasting of registration demand.

## H. Weak or unnecessary content to omit

**Omit, because it's repetitive or visually weak:**

- CRUD tables: Buses, Drivers, Stops, Semesters, Assignments, Bus Assignments, Students
- Login, signup, OTP and forgot-password screens (show the login card for about 1 s at most)
- Complaints pages (a plain list and form), Route Change Requests (same pattern as the waitlist), Export Data (a list of CSV buttons)
- Mobile hamburger layouts for admin and student (always record at laptop width)

**Omit, because it isn't real or ready yet:**

- **Crime-risk overlay.** Production has no feed ("Risk data is unavailable until an approved geocoded crime feed is configured"), and the README forbids presenting demo seed data as real.
- **Maintenance schedules.** Backend only, no UI.
- **Any "AI" or "optimised routes" claim about the current product.** Today the admin orders stops manually and OSRM only draws the road. "AI" belongs in the roadmap beat only, labelled "In research".
- **"PDF & CSV exports".** The export page is CSV only. The one PDF is the student transport card.
- **"@nu.edu.pk only" signup.** I only found a placeholder, not enforcement.
- **Real Stripe payments.** It's a sandbox. If the card form appears, show the "Stripe Test Payment" label, or cut straight to "Payment Verified".

**Fix before recording:**

- The semester is named **"Spring 2024"** and its registration deadline has passed. Rename it and reopen registration.
- **Real team emails, phone numbers and roll numbers** appear in the waitlist, route detail and complaints. Seed fictional students.
- Render cold-starts show "Loading (4 requests)…" toasts. Warm the backend before each take and trim any spinner.
- All 3 buses currently show "No tracker / Offline". A driver phone has to be running a trip during capture.
- Route 6B's builder preview drew straight segments in one view. Re-save routes so road geometry is cached.
- The Route Builder layout breaks below about 1000 px wide, so record at 1440 px or wider.

## I. Required assets

**Brand (have):**

- Approved logo files: `fleetcentric-logo-original.jpeg`, `-mark.png`, `-wordmark.png`. The pack's rule is **light grounds only, never recolour**. Put the logo on a white or cream plate in dark scenes (the standee does this). Note that the landing page uses `fleetcentric-primary-light.svg` on a dark hero, which conflicts with this rule.
- Palette: app navy `#0b2d42` / `#0f3a55`, accent `#288dc4` / `#62a1be`, page `#f0f4f8`, plus the logo's teal gradient and the standee's teal highlight. Status colours come from `theme.js`.
- Type: **Outfit** (headings) and **DM Sans** (body), matching the app.
- Standee copy for the problem beat, and the six feature tiles as an end-card grid.
- Existing diagrams: `Claude outputs/FleetCentric_architecture.png` and `FleetCentric_workflow.png` (for reference; restyle rather than paste).

**Screen recordings (to capture on a real laptop, 1920×1080 or 1440×900 @2x, clean browser profile, no bookmarks bar):**

1. Registration: stop picked on the map → submitted → "On the Waiting List" (fresh fictional student on 5B)
2. Admin Waiting List: 5B expanded → free a seat → queue empties
3. Student dashboard after promotion: notification + "Seat Held" + challan
4. Challan → "Payment Verified" → dashboard transport card
5. Driver Live Trip on a **phone**: portrait, 1080×2340 screen recording, while a trip is running (a real short drive, or Chrome DevTools location override replaying the 6B polyline)
6. Student Live Bus Map with the bus moving
7. Admin dashboard: Live Fleet with buses live, charts, then the off-route alert in the bell
8. Route Builder: add and reorder stops, with the line redrawing
9. Admins & Roles module matrix, and an Activity Logs row expanded to show the diff

**Data for motion graphics (pull from the API, don't invent):**

- Route geometries and stops: `/api/routes/map/`, used for animated polylines
- Fleet snapshot: `/api/admin/live-fleet/`, for bus chips
- Waitlist and capacity numbers: `/api/waitlist/`

**Audio and other:**

- Voice-over script (next step)
- Licence-clear music bed
- A UI click/tick SFX pack
- Team names, supervisor, FAST-NUCES Karachi credit, and the site URL for the end card

*Reference captures from this session* are in `reference-captures/`. They're low resolution because the browser pane was emulating a laptop. Use them for layout and blocking only, not in the final video.

## J. Recommended video length

- **Master cut: 90–105 s.** Long enough for the full student loop plus the control room and tech beats. Short enough for an evaluation panel, a pitch or a website hero.
- **Derived social cut: 30–40 s.** Hook → auto-promotion → live map → logo.
- **Optional 3–4 min walkthrough** for the FYP viva, using the same scenes with longer holds and narration. Build it later from the same Remotion components.

---

## Recommended narrative: "One seat, one bus, one morning"

The organising idea is **not a feature tour**. The video is one student's semester, told in 100 seconds. It ends with the admin's view that holds everything together.

| Time | Scene | On screen | Narration (draft intent) |
|---|---|---|---|
| 0–8 s | **Paper** | Kinetic type: "Transport still runs on paper." Four pains with red ✕ | "Every semester, campus transport runs on paper: registers, hand-counted seats, fees checked one by one, and no idea where the bus is." |
| 8–12 s | **Logo** | Mark builds on a light plate → "Fleetcentric.ai" | "FleetCentric.ai puts the whole cycle in one place." |
| 12–24 s | **Pick a stop** | Registration map, pin drop, route draws | "Students pick a stop, not a route. FleetCentric finds the bus that can seat them." |
| 24–40 s | **Full → queue → promoted** ★ | Seat-grid 2/2 → queue #1 → seat frees → cascade: Seat Held, Challan, Notification | "Bus full? She joins the queue, with no fee for a seat that doesn't exist. The moment a seat frees up, it's hers: challan issued, deadline set, and she's notified instantly." |
| 40–50 s | **Pay → card** | Payment Verified → transport card flips in, SEAT #N | "Pay, get verified, and your transport card is ready." |
| 50–62 s | **Driver starts the trip** | Phone mockup: Start trip → ETAs → stop ticks off | "The driver's phone becomes the tracker, with live arrival times for every stop." |
| 62–72 s | **Bus on her map** | Laptop and phone split, same bus moving | "And she watches it arrive." |
| 72–84 s | **Control room** | Admin Live Fleet → off-route ring → alert in the bell → charts | "Admins see the entire fleet live, and get alerted the moment a bus leaves its route." |
| 84–92 s | **Trust** | Flash: RBAC matrix → audit-log diff | "Scoped roles for every admin, and a record of every change." |
| 92–100 s | **Under the hood + next** | Stack strip; "In research: route optimisation · demand forecasting" | "Built on open maps and low-cost infrastructure, with optimised routing in research next." |
| 100–105 s | **End card** | Logo, URL, three portals, team, supervisor, FAST-NUCES Karachi | — |

★ The hero beat. Give it the most motion design and the slowest pacing.

**Creative rules for the build:**

- Show real UI captured at laptop size in a thin device frame. Use motion graphics only to *explain* what the UI does (seat grids, queue tokens, pulses), never to invent screens.
- Keep one accent colour per scene: teal for success, red for the problem, blue for UI.
- No claim goes on screen unless it's backed by code in the table in D. "AI" appears only in the roadmap beat.
