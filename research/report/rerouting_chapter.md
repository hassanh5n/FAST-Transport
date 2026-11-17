# Rerouting a Shuttle around a Blocked Road

Draft of 17 November 2026, written from `research/LOGBOOK.md` (entries of 10 November, the rules entry
L1 of 16 November, and the scaling-runs entry of 17 November), the work plan
`research/plans/2026-11-15-rerouting-plan.md` (version 2), the implementation plans in `research/plans/`,
the code in `research/reroute/` and the lead's implementation notes of 17 November.
No rerouting experiment has run on the Karachi map or on OSRM yet. Every number that needs such a run
is marked **[pending: entry Ln]**, where Ln is the logbook entry that will hold it (see the logbook
plan, `research/plans/2026-11-16-logbook-and-chapter.md`).

<!-- Lead: entries L2 to L6 and L8 to L11 do not exist yet (the scaling-runs entry of 17 November
takes the place of L7). When an entry is written, replace its [pending] marks and delete this
comment. Sections 8 to 11 are a frame only. -->

## 1. Introduction

The optimization chapter showed that a free-tier server can plan good routes for the semester, given
a few minutes per contractor. It also showed what such a server cannot do: re-run the same optimizer
within seconds when a road is blocked in the morning. A blocked road is not rare in Karachi. Protests
close trunk roads, and rain floods underpasses and main roads. When this happens today, the driver
finds a way around the block and the published stop order stays as it is.

This chapter studies what the transport system could do instead, for one bus at a time, on the morning
run to campus. The supervisor confirmed the question on 10 November 2026:

> When a road is blocked, which road and which stops (keep, skip, or let students walk to a nearby
> point) give the lowest student delay, within the same limits?

"The same limits" are those of the optimization chapter: a free-tier web service with 512 MB of memory,
no swap and one tenth of a CPU core. The question has three parts, each answered by a pass of one
experiment whose pass or fail rules were written down before any scenario existed:

1. **Quality.** With exact travel times and no time limit, how much do the methods gain over driving
   the published order around the block? Does letting students walk to a nearby stop help, once the
   gain that walking gives on a normal day is taken away? How close does a fast greedy method get to
   the best plan?
2. **Limits.** Under the free-tier limits, with travel times computed in memory from a road graph,
   how soon is a valid plan ready, and how close is it to the best plan after 30 seconds?
3. **Scaling.** How does the cost grow with more stops on a bus, a larger road graph, and more buses
   hit by the same closure?

The optimization work left three findings that shaped the design. A reroute needs a small problem (one
bus) and a method that always has an answer ready. After a block, travel times that cannot have
changed should be reused. And when a travel time must be guessed, it is safer to guess high.

The main results are **[pending: entries L8, L9, L10]**.

## 2. Background

The problem in this chapter is a covering path problem. The Shortest Covering Path Problem asks for the
shortest path between two fixed nodes such that every demand node lies within a given distance of some
node on the path [1]. The Covering Tour Problem gives the vocabulary used here: some nodes must be
visited, some may be visited, and some must be covered, that is, lie within a distance of a visited
node [2]. In this chapter the bus position, campus and any point students were already sent to must be
visited; the candidate boarding points may be visited; and the remaining stops must be covered. A stop
is covered when the walk from it to a visited point is within its walking limit. Related models trade
path length against the total access distance of the demand [3], or treat time and coverage as two
objectives and compute several compromise solutions [4], [5]. This chapter does not trade the two:
arrival time comes first and walking only breaks ties.

The bus drives on a road network, but the methods work on travel times between a few candidate
points. Solving on the table of shortest travel times between the points that matter is the standard
way to treat a tour on a road network, as in work on the Steiner travelling salesman problem [6].

School bus routing with bus stop selection lets each student board at any stop within a maximum walking
distance while the buses are routed [7], [8]. The problem here is that one with a single bus already on
its way, with blocked roads, and with a walking limit per stop. Coverage is measured from points where
the bus stops, not from anywhere along its path: students need the bus to stop, and work on meeting
points for demand-responsive transport restricts candidates to places where boarding is safe [9]. That
work uses about 400 m as an acceptable walk and 800 m as the most [9]. Montreal data put the 85th
percentile walk to a bus stop at about 524 m [10]. The walking limits tested here, 400 and 800 m, follow
these figures. Semi-flexible transit separates compulsory stops from optional ones [11]; the must-serve
flag of this chapter is the same idea.

In the dynamic routing literature this is an event-driven re-plan of a route already under way, not a
problem with requests arriving at random [12], [13]. Once a closure is reported it is treated as known
and fixed, and the bus re-plans from where it is. The real-time stop-skipping problem is the closest
transit model: it decides which stops a vehicle skips after a disruption, and it was solved by
exhaustive search because the instances were small [14]. Vehicle rerouting work prices a re-plan by
operating cost, service not given and disruption to the published route [15]. Transit disruption
research covers holding, stop-skipping, short-turning and bus bridging [16], [17], but keeps the
route's path fixed or redesigns a whole network.

Two tools from route planning carry the travel times. Customizable route planning splits preprocessing
so that new road weights are applied by a short step instead of a full rebuild [18], [19]. OSRM
implements it as its multi-level Dijkstra pipeline; `osrm-customize` can be re-run with a file of
segment speeds without partitioning again [20], [21]. What a speed of zero does in that file was left
unverified by the literature review, which is why this project tests it (Section 4.1).

The methods are arranged as an anytime ladder: a valid plan at once, then better plans as time allows,
in the sense of anytime algorithms that trade computing time for quality [22] and of search methods
that find a feasible answer fast and then tighten it [23].

The motivation is practical. A World Bank study of 2,564 cities found that a 1-in-100-year flood exposed
about 14.7% of urban roads but made 44.8% of simulated trips fail [24]. Two Karachi cases are used in
this chapter: the protest closure of Shahrah-e-Faisal between Karsaz and FTC on 24 February 2024 [25],
and ponding on University Road between Hasan Square and NIPA, where a modelled storm gave a maximum
delay of about 35 to 39 minutes [26].

The literature note behind this section found no paper that reroutes a single fixed-route shuttle in
the middle of its trip as a covering path on a blocked road network, and none that measures such a
method under an explicit small CPU and memory budget. Its searches were not exhaustive and several
databases were rate-limited, so the claim is "none found", not "none exists". The note also proposes
walking limits that depend on context (darkness, flooding, safety). Those are not studied here.

<!-- Lead: every reference above is marked [V] (record or full text opened) in the literature note.
Two details: the DOI of [14] is marked unverified there, and [20] is the documentation of OSRM
v26.5.0 while the project runs 5.27.1. [9] is cited as the arXiv version, which is the one marked
[V]; its journal version is [U]. The exact dynamic programming of Section 6.3 is of the kind
usually credited to Held and Karp; no source for it is in the literature note, so it is not named.
Add a verified source if the name is wanted. -->

## 3. Problem model

The model was fixed in logbook entry L1 on 16 November 2026, before any scenario file existed and so
before any delay had been seen.

**Scope.** The morning run to campus. One bus is rerouted at a time.

**Given.** The bus position and the time of the decision; the remaining stops, each with its students,
a walking limit and a must-serve flag; candidate boarding points, which are the remaining stops plus
other known stops within 800 m walk of one of them; walking distances from OSRM's foot profile; one or
more closures; and any points the bus is already committed to visit, because students were told to
walk there in an earlier revision.

**Decide.** Which candidates to visit, in what order, and at which visited point each stop's students
board. The boarding point is a decision of its own. A review of the first draft showed that the rule
"board at the nearest visited point" makes an exact method incorrect, because a later visit can pull
walkers away from an earlier one.

**Rules.**

- Every remaining stop boards at one visited point within its walking limit. A must-serve stop boards
  at itself. Committed points are visited.
- A visited point takes $60 + 5\,q$ seconds, where $q$ is the number of students boarding there, as in
  the optimization model.
- Walkers start 60 s after the decision and walk at 1.2 m/s. A student who walks $m$ metres is ready at
  the point $60 + m / 1.2$ seconds after the decision: 393 s for 400 m and 727 s for 800 m.
- The bus does not leave a point before its walkers have arrived. If it arrives first, it waits.
- **Reachability.** A point inside a full-block closure cannot be visited, in both travel-time sources
  (Section 4). Its students must walk. A stop with no boarding point in range is reported `unserved`.

So the bus leaves a visited point $v$ at

$$d_v = \max(a_v,\; w_v) + 60 + 5\,q_v,$$

where $a_v$ is when it arrives and $w_v$ is when the last of the walkers boarding at $v$ is ready. Its
arrival at campus is the departure from the last point plus the drive to campus.

**Objective.** Earliest arrival at campus. Among plans with the same arrival, less total walking
(students times metres) is better. This is a strict two-level order with no tolerance window, so the
best plan is never beaten on arrival time.

**Delay.** A plan's delay is its arrival minus the arrival of the published order with no closure,
from the same bus position. It is measured this way for every method and every table a plan was made
on, so delays can be compared across methods and arms.

Three properties of the model must be stated plainly.

1. **The oracle is the best plan in this model, not a bound on any reroute.** The exact method run on
   true travel times with no time limit is called the oracle. It is the best plan given known stops as
   the only boarding points, stop-to-stop walking, OSRM travel times and the closures given. A plan
   that boards students at a street corner, or a bus that waits elsewhere, is outside the model.
2. **The exact method guarantees the earliest arrival, not the least walking.** Because the bus can
   wait for walkers, two plans with the same arrival can differ in walking in ways the method does not
   compare. It finds the least walking only among the plans it holds with that arrival.
3. **Skipping a stop saves time on any day.** A visited point costs at least 60 s. Letting a stop's
   students walk to another stop saves that time with or without a closure. A gain from walking after
   a closure therefore means little on its own. The experiments measure it net of a no-closure control
   (Section 7.2).

With a walking limit of 0 and every remaining stop to be visited, the problem is to order all the stops
between the bus and campus, which is a shortest Hamiltonian path. So the problem is NP-hard in general.
This is our own reasoning, not taken from a source. It is small in practice: the current routes have 3
to 13 stops.

## 4. Travel times after a closure

Two sources of travel times are used. **Truth** is OSRM re-customized with the closure. It is used only
to build the scenario file and to score plans. **Under test** is a road graph built from the same map
file and searched in memory on a corridor around the route. It is what a deployed solver could use
inside the free-tier limits. Plans made on the graph are always scored on the truth.

### 4.1 OSRM as truth

The truth is OSRM 5.27.1 with the car profile and the multi-level Dijkstra pipeline, built from the map
file of run N1 (the Geofabrik extract of Pakistan dated 2 November 2026, cut to a box around Karachi). A
closure is applied as follows.

1. The road segments inside the closure are found on the road graph's segment table by geometry
   (Section 4.3). OSRM names a segment by its two adjacent map node ids, so the same table gives OSRM's
   speed file.
2. A fresh copy of the untouched OSRM files is made. Customizing rewrites segment data, so closures
   would otherwise pile up from one scenario to the next.
3. The copy is customized with the speed file and served, and the tables of the scenario are read from
   it.
4. In the table after the closure, the rows and columns of points inside a full-block circle are set to
   unreachable, whatever OSRM answers. This is the reachability rule.

Two checks run on every closure. The **leak check** routes each pair of consecutive open points of the
route on the customized server and counts a leak if any vertex of the returned line lies inside a
full-block circle. The build stops if any closure leaks. The **faster-pair check** counts pairs whose
time after the closure is shorter than before by more than a tolerance; a closure only removes or slows
roads, so such a pair points to a snapping difference.

The **road-block test** (run before the scenario build) answers four questions on one fixed leg, the
first leg of Jadoon route R-10:

| Question | What the answer selects | Answer |
| --- | --- | --- |
| Does a segment speed of 0 block a road in OSRM 5.27.1? | Speed 0 in the scenario build, or 1 km/h if not | [pending: entry L3] |
| Is a point on a closed segment moved silently to another road? | Confirms the reachability rule | [pending: entry L3] |
| Does a slowed segment change routes? | Whether the University Road case stays in | [pending: entry L3] |
| How long do customizing and restarting take? | Scenario build time | [pending: entry L3] |

OSRM's current source code maps speed 0 to an impassable segment, but this was not checked on version
5.27.1, which is why the test exists. `run_roadblock.py` answers with the block speed to use (0 or
1 km/h), and `build_scenarios.py --block-kmh` follows it.

### 4.2 The road graph

The graph is built once, offline, by `build_graph.py` from the same map file, with `pyosmium`. It keeps
ways whose road class a bus may use, at the class speeds of OSRM's car profile (from 90 km/h on
motorways to 10 km/h on living streets), and skips private and no-vehicle ways. It holds two tables:

- **Segments**: every directed map segment with its node ids, geometry, length and time. OSRM's speed
  file and the closure matching need this full table.
- **Compressed graph**: chains of nodes with no junction merged into one edge, for searching. Every
  stop and campus is kept as a node.

The arrays are stored as separate `.npy` files, so they can be opened memory-mapped and shared between
worker processes.

| Item | Value |
| --- | --- |
| Map file SHA-256 | [pending: entry L2] |
| Graph nodes, edges, segments | [pending: entry L2] |
| Stops snapped more than 200 m to a road | [pending: entry L2] |

**Calibration.** One speed factor is fitted against the saved OSRM matrix M1: graph times between every
pair of the matrix's nodes are compared with OSRM's, and the factor is the 60th percentile of OSRM time
over graph time, so the scaled graph runs slightly slow, not fast. The rule, fixed in entry L1: median
absolute error at most 15% and median signed error not negative. If it fails, one factor per road class
is fitted and the rule is checked again.

| Calibration | Value |
| --- | --- |
| Factor | [pending: entry L5] |
| Median absolute error | [pending: entry L5] |
| Median signed error | [pending: entry L5] |
| Pairs the graph finds unreachable | [pending: entry L5] |
| Rule met | [pending: entry L5] |

The graph errs on the safe side by design. The optimization chapter found that an overestimated travel
time keeps a plan on the legs it knows, while an underestimate draws the plan onto legs that are slower
than it believes.

### 4.3 Closures, corridors and rows

**Closures by geometry.** Each road segment is sampled every 50 m, both ends included. A segment is
closed if any sample lies inside a closure circle. Matching by the nodes in a circle alone would miss a
long segment that crosses a closure with no node inside it. A plain latitude and longitude grid indexes
the segments so only nearby ones are tested. On the graph, a fully blocked segment removes its whole
compressed edge from the edge list; a slowed segment adds seconds to its edge. A closure is never
written as a zero weight, which some sparse-matrix routines read as "no edge" and others as "free".

**Corridors.** A search over the whole city is expected to be too slow for a 5-second target at
0.1 CPU (Section 4.4 measures both), so each route has a corridor, computed offline by `build_corridors.py`: every graph node within 1,500 m
of the route's current path to campus. Searches run on the corridor's subgraph. If a target cannot be
reached inside the corridor, which happens when a closure cuts it in two, the search is repeated once
on the whole city graph and the row records `widened`.

| Corridor sizes | Value |
| --- | --- |
| Nodes, smallest / median / largest | [pending: entry L5] |
| Stops outside their route's corridor | [pending: entry L5] |

**Rows and the cache.** A travel-time row is the time from one point to every node, from one
`scipy` Dijkstra search. Rows are cached in one least-recently-used cache shared by every bus in the
process, keyed by graph version, corridor, closure set and source. Every bus hit by the same closure
therefore reuses the same rows. The cache holds at most 256 rows and at most 128 MiB: a row over the
whole city is about 1.6 MB, so a count limit alone would not bound memory. Two corridors that share a
key never share rows, because the key includes a hash of the corridor's nodes and edges.

**Reuse of pre-closure rows.** For each route, the times between its points with no closure and the
graph edges on each pair's shortest path are stored offline. A closure only makes travel slower, so a
stored shortest path that uses no closed or slowed edge is still the shortest, and that point's row is
served from the table without a search. This is the query-budget finding of the optimization chapter
carried into rerouting: after a block, re-query only what can have changed. The limits pass records
rows searched and rows reused.

### 4.4 Gate G1: is the graph fast enough?

Before the limits pass, the graph must pass a gate fixed in entry L1: on the longest route's corridor,
under 512 MB and 0.1 CPU, the 14 rows R0 needs (13 stops and the bus position) in at most 5 s of wall
time, and 31 rows in at most 30 s. `measure_graph.py` runs five repeats and judges the worst.

| Measured (longest route, under the limits) | Corridor | Whole city |
| --- | --- | --- |
| Graph load time | [pending: entry L5] | [pending: entry L5] |
| Memory after load / peak | [pending: entry L5] | [pending: entry L5] |
| 14 rows, wall seconds (worst repeat) | [pending: entry L5] | [pending: entry L5] |
| 31 rows, wall seconds (worst repeat) | [pending: entry L5] | [pending: entry L5] |
| Gate G1 | [pending: entry L5] | - |

If calibration or timing fails, the rule fixed in L1 applies: the limits pass plans on saved
pre-closure times, reports solver time only, and the travel-time source becomes a stated limitation.

## 5. Scenarios and walking distances

The scenario file `data/scenarios_reroute_v1.json` is built once, by `build_scenarios.py`, and then
frozen: every later run reads it and none needs OSRM. A frozen file is never edited by hand; a change
means a new version.

### 5.1 Walking distances

`build_walk.py` builds OSRM with the foot profile and makes one table call over all 311 stops for
walking distances. It keeps directed pairs within 1,200 m in a straight line and 1,000 m of walking.
Two statistics describe the result: the walking detour factor, the median of walking metres over
straight-line metres for pairs within 800 m in a straight line; and the share of stop visits on the
current routes that have another stop of the same route within 400 m and 800 m of walking.

| Walking | Value |
| --- | --- |
| Detour factor | [pending: entry L4] |
| Stop visits with a same-route stop within 400 m walk | [pending: entry L4] (30% in a straight line) |
| Stop visits with a same-route stop within 800 m walk | [pending: entry L4] (65% in a straight line) |

The straight-line shares were measured on 15 November for the work plan. Real walking distances can
only lower them.

### 5.2 Synthetic closures

For each current route with at least 3 stops, two closures are placed, each a full-block circle of
200 m radius centred halfway along the road line of a leg between two stops. For a route of $n$ stops
the legs closed are leg $\lceil n/3 \rceil$ and leg $\lceil 2n/3 \rceil$, the second capped at $n-1$,
where leg $k$ joins stop $k$ to stop $k+1$. Closures sit between stops on purpose: placing them by
driving time, as in the first draft of the plan, would have put many after the last stop, where every
method gives the same answer.

A stop with no students on this route (a stop shared with the other contractor) is dropped from the
route before closures are placed. A 200 m circle also closes the side roads beside the route. Closures
on roads no route uses are not included; this narrows the 10 November wording "on or near shuttle
routes" to closures on routes, as entry L1 states. If the campus lies inside a closure the build warns,
because every scenario of that closure is then unreachable.

### 5.3 Bus positions

Each closure gives two scenarios, which share one OSRM customization:

- **Early**: the bus is at the first stop with nothing served; every stop remains.
- **Late**: the bus is at the last stop before the closed leg, which it has just served; the stops
  after it remain.

The bus is assumed to be at a stop when the closure is reported.

### 5.4 Historical closures

Two real stretches are reported separately and never pooled with the synthetic scenarios:

- Shahrah-e-Faisal between Karsaz and FTC, a full block, after the closure of 24 February 2024 [25].
- University Road between Hasan Square and NIPA, slowed to 10 km/h in OSRM's speed file (never faster
  than the road's own speed) and carried as factor 0.25 in the scenario file, after the ponding study
  [26].

Each stretch is a chain of 60 m circles about 100 m apart along the road line between its two end
points, and
applies to every route whose leg lines enter it. Its scenarios are an early trigger at the first stop
and a late trigger at the last stop before the stretch. A stretch first met on the leg from the last
stop to campus gets the early trigger only, because the late one would leave nothing to serve.

The end points must be read off a map by a person and checked by routing between them on the
unblocked server. They are not guessed. In the repository they are still empty
**[pending: entry L6]**.

### 5.5 Candidates, students and tables

A scenario's candidate boarding points are the other known stops within 800 m walk of any remaining
stop. Students per stop come from the synthetic dataset of the optimization chapter, counted for this
route only. Each closure stores two square tables over its points with campus last: `pre`, with no
closure, and `post`, the truth. An unreachable pair is stored as `null` and read back as infinity,
never as zero.

Each scenario is tagged with its number of remaining stops and whether the closure contains a stop.
The quality pass adds the patched route's delay and whether the oracle differs from it.

### 5.6 The frozen file

| Item | Value |
| --- | --- |
| Synthetic closures and scenarios | [pending: entry L6] (planned: 104 and 208, less routes left with under 3 stops) |
| Historical closures and scenarios | [pending: entry L6] |
| Closures with leaks | [pending: entry L6] (must be 0) |
| Faster pairs | [pending: entry L6] |
| Scenarios whose closure contains a stop | [pending: entry L6] |
| Candidates per scenario, median and largest | [pending: entry L6] |
| Build time and customizations | [pending: entry L6] |
| File SHA-256 | [pending: entry L6] |

## 6. Methods

All methods are in `research/reroute/`. The solver core (`model.py`, `ladder.py`, `wire.py`) has no
Django, no file access and no network access, so the same code can later run inside the website; only
the road-graph module reads files (the graph and corridor arrays). Every method builds a visit order and boarding choices
and scores them with one function, `model.evaluate`, which holds the timing rules of Section 3. A
method's plan is therefore scored the same way whatever produced it.

Travel times reach the methods through one function the caller passes in, which answers a batch of
source points with their rows. The experiments pass saved tables; the limits pass and the website pass
graph rows. The number of distinct rows a method asks for is recorded, because rows are the expensive
part (Section 4.3).

### 6.1 R0: the patched published route

R0 is the baseline: what a driver does today. Every remaining stop whose own point is reachable is
visited in published order, and the road between them is whatever detour the travel times give. A stop
whose own point lies inside a full block boards at the reachable point in range with the least walking,
inserted where it adds the least driving time. R0 needs one row per visited point and one for the bus
position: 14 rows for a 13-stop route.

### 6.2 R2: greedy

R2 starts from the committed points, then repeatedly inserts the unvisited point with the largest ratio
of students it can board (from stops not yet assigned) to the driving time it adds plus 60 s of stop
time. Those stops board there. It then tries removing each visited point that is not committed, moving
its stops to the nearest visited point in range, and keeps a removal that makes the plan better; this
repeats until a pass changes nothing. Last, each stop is moved to its nearest visited point if that
does not make the plan worse. If R0 arrives earlier, R2 returns R0's plan. R2 needs a row from every
useful point: up to 31 rows for 30 points.

`backend/apps/transport/corridor.py` already holds a greedy covering-path heuristic, used to draw route
lines on the public Valhalla server. R2 is a separate implementation for a blocked network.

### 6.3 R3: exact

R3 is an exact dynamic programme in two phases. Its size is counted in **bits**: one per remaining stop
that has a reachable boarding point, plus one per committed point. R3 runs only up to 16 bits. The
current routes have at most 13 stops and the scenarios have no committed points, so every real
scenario is within the cap.

**Phase 1: a search over sets.** For every set of boarded stops (a mask of bits) and every point $k$,
the search keeps the earliest time the bus can leave $k$ having boarded exactly that set, with walking
as a tie-breaker. Masks are processed in increasing order. From each mask, every move "drive to a point
and board a group of the stops that can board there" is relaxed at once with `numpy`. At each point the
stops that may board are sorted by when their walkers are ready, so only the prefixes of that order are
worth boarding together. This phase allows the bus to visit a point twice. At the end, repeated visits
are merged into the last one, which gives a valid plan.

**Phase 2: an exact repair.** Merging is not always free. When stops that boarded at an earlier visit
move to the later one, the bus may wait there for walkers it did not wait for before, and the merged
plan can arrive later than the search's value. Review found this on 34 of 800 small random problems,
where the single search planned at first was compared with brute force (logbook, 17 November). When the
merged plan misses the search's value, a second search runs over labels (set boarded, last point,
points visited). A label is dropped when another at the same set and point leaves no later, has walked
no more, and has visited only points the dropped label also visited. A label is also dropped when a lower bound on its arrival
already exceeds the best known plan, which is the merged plan or R2's. With this phase R3 matched brute
force on all 800 problems and on every unit test, where brute force tries every subset of points, every
order and every boarding choice.

R3's result is optimal on a table that satisfies the triangle inequality. On a table that does not,
which can happen with OSRM's snapping, the search value need not be a bound and the pruning need not be
safe; R3's plan is then valid and no later than R2's, but not certified optimal.

**Cost.** Phase 1 has $2^b$ masks for $b$ bits. Each mask relaxes $K \times K$ driving pairs and the $E$
boarding pairs at once, so the work grows as $2^b (K^2 + E)$ for $K$ points. Its tables hold $2^b \times K$
entries of 20 bytes (two 8-byte floats and two 2-byte parent indices): for 16 bits and 30 points that
is about 39 MB. Phase 2 has no useful bound in theory, since its labels also carry the set of visited
points; in practice dominance and the lower bound keep it small.

Development measurements on the unthrottled Windows laptop (lead's notes, 17 November; not a logged
run): R3 with 16 stops and 30 points took about 7 CPU-seconds, and with 800 m walking limits the repair
phase took 16 to 32 CPU-seconds at 15 stops. If the tenfold slowdown of the optimization chapter holds
here, these are 70 s and several minutes at 0.1 CPU. Run RS1 gives the logged figures
**[pending: entry L10]**.

<!-- Lead: the 7 CPU-s and 16-32 CPU-s figures come from your notes only. They should go into the
logbook (or be replaced by RS1's numbers) before this section is final. -->

The work plan asked for R3 to be vectorised per layer (all masks of the same size together). It is
vectorised per mask instead. This is enough for the ladder, because R0 and R2 always give a plan first.

### 6.4 The lower bound above 16 bits

Above 16 bits R3 is not run, and the ladder reports a lower bound instead: the direct time from the bus
to campus, plus 60 s for the fewest points that could board every servable stop (the stop count divided
by the most stops any single point can board, rounded up), plus 5 s per student. The gap of R2 to this
bound is reported. Like R3, the bound holds on tables that satisfy the triangle inequality.

### 6.5 The ladder

`Ladder` runs the methods in order and keeps the best plan so far. A plan replaces the best only if it
is better and leaves no more stops unserved.

| Step | Work | Returns after |
| --- | --- | --- |
| R0 | In full, always, even past a deadline | One step |
| R2 | In full | One step |
| R3 | In slices: a number of masks (256 in the experiments) or until a deadline | Many steps |
| Done | Best plan; or best plan and lower bound when R3 was skipped | - |

A website therefore always has a plan once the first step returns, and a better one with each step.
The whole ladder, including both phases of R3, can be saved to JSON after any step and restored later
(`Ladder.to_json`, `Ladder.from_json`), with the search tables stored as base64 strings. A stopped and
resumed solve returns the same plan as an uninterrupted one; this is a unit test. At 16 bits and 30
points the phase 1 tables alone are about 39 MB, or about 52 MB once base64-encoded, which matters
for where a website keeps the state between slices (Section 9). The measured state sizes are in run
RS1 **[pending: entry L10]**.

### 6.6 R1, and what was not built

The first draft of the plan had a rung R1: accept the fastest path to campus if it happens to pass
every stop. It was dropped because it cannot be defined on saved travel-time tables and adds little. A
time-limited OR-Tools or CP-SAT model was not built: R3 is exact at the sizes of the current routes, and
"board at any one of these points" maps poorly onto OR-Tools' optional-visit constraints when the sets
of points overlap.

## 7. Experimental method

### 7.1 Rules fixed before running

Entry L1, with the problem, the methods, the scenario rules, all six thresholds and the gate G1 rules,
was committed (`50ab71b`) before the scenario file was built, so nobody had seen a delay when the
thresholds were set. The thresholds are also constants in `run_reroute.py`. Thresholds are judged on the
worst repeat as well as the median, the rule the team adopted on 10 November.

Some details of how the thresholds are judged were settled while the runner was written, before any
quality or limits run (commit `7299036` and the lead's notes of 17 November). They are listed in Section
7.5.

<!-- Lead: the judging details in Section 7.5 (your decisions 5 to 7) are in the code and your notes
but not yet in the logbook. Log them, and push, before the first quality or limits run, so the order
can be shown from the history. -->

### 7.2 Quality pass (run RQ1)

Every scenario is solved with R0, R2 and R3 on true times, with no time limit, at walking limits of 0,
400 and 800 m. Two more arms run at 400 m:

- **No-closure control.** The same solve on the `pre` table. Skipping a stop saves stop time on a normal
  day too; the control measures that. The **closure-specific gain** is
  (R0 minus R3 with the closure) minus (R0 minus R3 with no closure).
- **Must-serve.** 25% of the remaining stops (rounded up, at least one) are marked must-serve by a fixed
  draw per scenario. Reported as a table, not judged.

That is five rows per scenario.

**The judged set** is the synthetic scenarios with at least 2 remaining stops where R0's delay is at
least 60 s. A closure with a nearly free detour, or a late trigger with one stop left, leaves nothing to
decide, and would make every method look perfect. The share of scenarios outside the judged set is
reported.

**Thresholds** (entry L1), on the judged set:

1. Closure-specific gain at 400 m: median at least 60 s.
2. R2's delay within 60 s of R3's in at least 90% of scenarios, and on the median of every route.
3. No run has a student walking beyond the limit, or a stop unserved where a boarding point exists, and
   R3 never arrives later than R0.

### 7.3 Limits pass (run RL1)

Every scenario is solved at 400 m inside the free-tier limits: 512 MB, no swap and a CPU quota of 10%,
applied with systemd as in run B1, with the limits read back from the kernel before any run. One worker
process per route, arm and repeat loads the road graph once and then handles that route's scenarios in
turn; this is the condition "graph already loaded". For each scenario the clock starts before the
problem is built, so applying the closure to the graph is inside the measured time and loading the
graph is not. The worker steps the ladder in slices of 256 masks until it is done or 30 s have passed,
and records the plan held after every step.

Three arms separate the two causes of a gap to the oracle:

| Arm | Travel times | Limits | Cap | Repeats | Shows |
| --- | --- | --- | --- | --- | --- |
| `graph_limited` | Road graph | Yes | 30 s | 3 | What a deployed solver would do |
| `graph_unlimited` | Road graph | No | None | 1 | What the graph's errors cost |
| `truth_limited` | True tables | Yes | 30 s | 3 | What the time limit costs |

`graph_unlimited` runs once per scenario: it is deterministic and its timing is not judged. Every plan
is scored on true times against the oracle, which is R3 on the true table with no limit, computed by
the parent process. For each row the pass records the time to the first plan, the method and delay held
at 1, 5 and 30 s, the gap to the oracle at each, rows requested, searches, reused rows, the corridor
and whether it widened, and peak memory.

**Thresholds** (entry L1), on the judged set, `graph_limited` arm, each scenario's worst repeat:

4. A valid plan within 5 s in at least 95% of scenarios.
5. At 30 s, delay within 60 s of the oracle's in at least 90% of scenarios.
6. Peak memory under 400 MB including the graph.

### 7.4 Scaling runs (RS1) and optimizer scaling (OS1)

These report curves and have no pass or fail rule.

| Part | What grows | Recorded | Where it runs |
| --- | --- | --- | --- |
| `stops` | 4, 8, 12, 16, 20 stops; 1, 2, 4 candidates per stop; seeds 1 to 3 (45 problems) | CPU and wall time and peak memory of R2 and of R3 to the end; R2 minus R3; above 16 stops the gap to the lower bound | Windows laptop, no limits (entry of 17 November); limited part on the WSL machine |
| `graph` | 10, 30, 60 points, corridor and whole city | CPU-seconds per row, searches, memory with memory-mapped arrays | WSL machine |
| `buses` | The Shahrah-e-Faisal closure with 1, 5, 10, 20 buses in one limited process | Seconds until every bus has a valid plan and its final plan; searches; cache hits | WSL machine |
| `slices` | The three largest judged scenarios | Plan after each slice of 256 masks; size of the saved state | WSL machine |

The `stops` part uses synthetic problems: stops placed uniformly in a 2 km square, driving at 10 m/s,
straight-line walking, a 400 m limit. The plan asked for longer routes made by joining real ones, but
the scenario tables hold no times between stops of different routes. The `buses` part is the one that
matters most for the website: a closed trunk road in the morning hits many buses at once, and the
shared row cache is what should keep the cost from growing with the number of buses.

Optimizer scaling (OS1) belongs with the optimization chapter but was planned in the same entry. It runs
the optimizer on Jadoon, Nadeem and doubled copies of each (every stop copied 30 s from its original),
with two ways of giving travel times to OR-Tools (a Python callback, as in every earlier run, and a
matrix given once), 300 s each and no limits. The combined 311-stop instances need a matrix from OSRM
and wait for it; the doubled instances stand in for size until then.

### 7.5 How the verdicts are computed

These details were settled before any quality or limits run (Section 7.1):

- **Statuses.** `ok` and `infeasible` are counted results. A scenario is `infeasible` when no plan is
  possible on true times: R0 on the true table never reaches campus or serves no stop, or the published
  route itself is unreachable. Every other status is a failure, including `invalid_on_truth` (a plan
  that breaks a rule on true times, uses a truly unreachable point, or leaves unserved a stop that truth
  can serve) and `killed_memory`.
- **Threshold 3.** A stop left unserved while a boarding point in range exists is a violation.
- **Threshold 4.** "A valid plan within 5 s" means the plan held at 5 s is valid on true times, not only
  finite on the graph it was planned on. A repeat that did not finish counts as missing the threshold.
- **Threshold 6.** Memory is a property of the worker process, so it is judged on every
  `graph_limited` row, judged scenario or not. A worker killed for memory keeps the rows it finished;
  its unfinished scenarios get `killed_memory`.
- **Worst route.** Results are given per route, and the worst route is the one with the largest median
  of R2's delay minus R3's.
- Synthetic and historical scenarios are never pooled in a threshold.

Scenarios from one route are not independent: they share stops, and routes share trunk roads. This is
why results are also given per route and threshold 2 is judged on every route's median.

### 7.6 Machines and pipeline tests

The team laptop used so far for the rerouting code is a Windows 10 machine (Intel Core i7 third
generation, 4 cores and 8 threads, 8 GB) that cannot start WSL, because virtualization is off in its
firmware. It runs the parts with no limits. Peak memory there is Windows' peak working set, not Linux's
`ru_maxrss`; the two are close for one Python process but are not the same measure, so figures from it
are not pooled with WSL runs. The limits pass and the limited scaling parts need a machine with WSL and
systemd **[pending: entries L9, L10]**.

Every pass has a pipeline test (`--quick`) on a small toy file of three scenarios
(`data/scenarios_toy.json`, written by `run_reroute.py make-toy`), with results in a separate `-quick`
folder. These are checks that the code runs end to end, not reported results.

### 7.7 Changes from the work plan

| Change | Reason |
| --- | --- |
| R3 has a second, exact phase | The planned single search was not exact on 34 of 800 problems (Section 6.3) |
| R3 vectorised per mask, not per layer | The ladder gives R0 and R2 at once; per mask was enough |
| A plain grid, not H3, indexes road segments | Same job, one dependency fewer |
| No separate reverse search from campus | Every row the solver asks for already includes the time to campus |
| A cut corridor falls back to the whole city once | Simpler; how often it happens is recorded |
| The speed factor is a 60th percentile | So the graph runs slightly slow, never fast |
| `stops` scaling uses synthetic problems | Scenario tables hold no times between routes |
| Doubled contractor instances stand in for the 311-stop optimizer runs | The combined matrix needs OSRM |
| Row cache bounded by bytes as well as rows | City-wide rows are about 1.6 MB each |

No item of the work plan's cut order has been taken. Cuts taken later: **[pending: entry L11]**.

## 8. Results

### 8.1 The scenario set

[pending: entry L6]. To report: synthetic and historical closures and scenarios; the share outside the
judged set and why (too few stops, or a detour under 60 s); scenarios whose closure contains a stop;
leaks (must be 0); candidates per scenario.

### 8.2 Quality (run RQ1)

[pending: entry L8]. When, machine, code version, runs, failed or rerun rows.

| Walking limit | Method | Delay, median / 90th percentile / worst (s) | Students walking | Metres per walker | Differs from R0 |
| --- | --- | --- | --- | --- | --- |
| 0 m | R0, R2, R3 | [pending] | [pending] | [pending] | [pending] |
| 400 m | R0, R2, R3 | [pending] | [pending] | [pending] | [pending] |
| 800 m | R0, R2, R3 | [pending] | [pending] | [pending] | [pending] |
| 400 m, no-closure control | R0, R3 | [pending] | [pending] | [pending] | [pending] |
| 400 m, must-serve | R0, R2, R3 | [pending] | [pending] | [pending] | [pending] |

Per route, with the worst route named: [pending]. Historical scenarios, reported apart: [pending].

**Verdict against the thresholds fixed on 2026-11-16.**

1. Closure-specific gain at 400 m, median at least 60 s: [pending].
2. R2 within 60 s of R3 in at least 90% of scenarios and on every route's median: [pending].
3. No violations, and R3 never later than R0: [pending].

### 8.3 Decision time under the limits (run RL1)

[pending: entry L9].

| Arm | Valid plan within 5 s | Gap to oracle at 1 / 5 / 30 s (median, worst) | Method held at 5 s / 30 s | Peak memory |
| --- | --- | --- | --- | --- |
| `graph_limited` | [pending] | [pending] | [pending] | [pending] |
| `truth_limited` | [pending] | [pending] | [pending] | [pending] |
| `graph_unlimited` | - | final gap [pending] | - | - |

Rows requested, searched and reused; corridors that widened: [pending].

**Verdict against the thresholds fixed on 2026-11-16.**

4. A valid plan within 5 s in at least 95% of scenarios: [pending].
5. At 30 s, within 60 s of the oracle in at least 90%: [pending].
6. Peak memory under 400 MB: [pending].

### 8.4 Scaling (run RS1)

[pending: entry L10]. One table per part: R2 and R3 time and memory against stops and candidates, with
the largest problem solved in 5 s and in 30 s; seconds per row against points, corridor and city; time
until every bus has a plan against buses, with cache hits; plan quality and state size per slice.

### 8.5 Optimizer scaling (run OS1)

[pending: entry L10]. Build time, time to first plan, peak memory and plan cost at 10, 60 and 300 s,
for each instance and lookup. Model build times are not comparable between the two lookups, because
the callback computes costs during the search and the matrix pays for them while building.

<!-- Lead: OS1 may read better as a section of the optimization chapter. -->

## 9. Discussion and what it means for the website

### 9.1 What the results say about the question

[pending: entries L8, L9, L10]. This section should answer, in order:

- Which road: does the best plan differ from the driver's detour, and by how much delay?
- Which stops: how often is walking worth it once the no-closure control is taken away, and how far
  do students walk?
- Within the limits: is a valid plan ready in seconds, and how much of any gap to the oracle comes
  from the graph's travel times (`graph_unlimited`) and how much from the time limit (`truth_limited`)?

What can be said now is what a result will and will not mean. A large gain on the judged set would mean
the gain exists when a closure matters; the share outside the judged set says how often it matters at
all. A small closure-specific gain at 400 m would be a valid result: it would mean letting students walk
is mostly a way to save stop time that a planner could take on any day, which is a question for the
optimizer, not for rerouting.

### 9.2 Using rerouting on the website

Nothing in this section is built. It is the design of work plan Section 12, checked against the code of
the website by a backend review. The solver core was written so that it can be copied into the backend
unchanged.

**The contract.** The request and proposal formats are those of work plan Section 6.3.
`reroute/wire.py` checks a request, turns it into a problem, and turns a plan into a proposal.

- A **request** names the trip (assignment, service date, direction), the decision time with its time
  zone, a deadline, the bus position, the remaining stops with students, walking limit and must-serve
  flag, the candidates, the committed points, the closures and campus. `wire.py` checks only the fields
  the solver needs; the trip and the deadline are for the website. Stops are identified by id, never by
  name, because stop names are not unique in the website's database. A request that cannot be solved
  is refused with the name of the field at fault.
- A **proposal** has a status, a revision, the method that produced it, the visit order, one entry per
  remaining stop (`keep`, `walk` with the point and metres, or `unserved`), the arrival time, the delay
  against the published route, the students walking, the computing time and the saved solver state.
- The status is `reroute`, `no_change` (the published order is already best and nobody walks) or
  `failed`. **A failed proposal must not be acted on.** It may still carry a plan, for information.
  A `reroute` can contain unserved stops, and those must be shown to admins.

**What the website lacks today** (work plan Section 12.1): the stops a bus has still to serve are not on
the server, because the driver's phone keeps them; an approved incident never expires; traffic alerts
are bare points with no extent; email has a daily allowance of 300 that also carries login codes; and
background work runs in a thread per process.

**The design that scales** (work plan Section 12.2):

- **A trip record** on the server, one row per assignment, date and direction, holding the reached
  stops and the students per stop.
- **A reroute job row, not a thread.** One row per trip and closure set, claimed with a row lock. Each
  location ping advances the solve by one bounded slice and returns the best plan so far. Workers then
  cannot duplicate or lose work, and a solve never holds the shared tenth of a CPU for more than a
  slice. The saved state is what makes this possible (Section 6.5). At the largest problems the state
  is tens of megabytes (Section 6.5), so where it is kept between slices needs care; the measured sizes
  are **[pending: entry L10]**.
- **One closure, many buses.** Rows are cached per graph version, closure set and source, and shared by
  every affected bus. In-process the sharing is per worker; a database table would share it across
  workers. The `buses` scaling run measures what this saves **[pending: entry L10]**.
- **The graph in memory**, opened memory-mapped from `.npy` files so workers share the read-only arrays.
  `numpy` and `scipy` become backend dependencies; their memory cost is measured **[pending: entries
  L5, L10]**.
- **Students are told only after the driver has the plan.** The driver's ping acknowledges the reroute
  id and revision first. The phone currently drops a failed ping, so without this rule students could
  walk to a point the driver never learns about.
- **Cancelling or expiring a reroute creates a new revision** that still visits every committed point.
  It never restores the published order, which would strand students already walking.
- **Automatic application with admins informed**, the team's decision, under limits still to be agreed:
  a minimum saving over the patched route, the walking limit, must-serve stops, no walking reroutes on
  evening trips, and only for fixes from an authenticated driver. The plain ping endpoint accepts
  unauthenticated posts and must not be able to trigger a reroute.
- **Notifications in bulk and in-app only**, through the poll students' maps already make. Twenty buses
  of forty students would use the daily email allowance at once.
- **Two existing features must learn about reroutes**: the off-route alert, which would fire on every
  reroute, and arrival times for a bus off its saved line, which call the public routing server on every
  ping.

**Order of building, after the research:** the trip record; the solver core and graph copied in with
their tests; a shadow mode that computes and stores reroutes for real incidents and shows them to no
one; then the admin view, driver delivery with acknowledgement, and student notifications last.

## 10. Limitations

Results-dependent limitations will be added from entries L8 to L10 **[pending]**. Those known now:

- **Students are synthetic**, as in the optimization chapter. Who boards where comes from a rule, not
  from registrations.
- **Truth is OSRM, not measured trips.** OSRM gives free-flow times on default speeds, and the buses
  carry no GPS trackers whose records could check them. "Delay against the oracle" is measured in the
  same model it is planned in.
- **The limits are simulated** with control groups on a laptop. A real shared host may add noisy
  neighbours, cold starts or a request timeout.
- **The oracle is the best plan in the model**, not the best possible reroute (Section 3). Boarding
  points are known stops only; students walk on OSRM's foot network; the walk start lag (60 s) and
  speed (1.2 m/s) are assumed values, and students are assumed to walk when asked.
- **The exact method does not guarantee the least walking** among plans with the earliest arrival
  (Section 3), and on a table that breaks the triangle inequality it does not certify its own optimum
  (Section 6.3).
- **One closure, known exactly, for the whole trip.** The model has no further closures, no clearing of
  a closure during the trip and no error in the reported extent. The bus is assumed to be at a stop when
  the closure is reported.
- **One bus at a time.** The `buses` run shares travel times between buses but plans each alone; buses
  do not trade students.
- **Morning runs only.** In the evening the stop is where students walk home, often after dark, and
  walking limits would need a different rule. Local evidence on walking safety in Karachi [27] is a
  reason not to carry the morning result to the evening.
- **Walking limits are one value per run**, not per stop and situation. The model allows a limit per
  stop and a must-serve flag; the must-serve arm uses a random draw, not context.
- **Scenarios are placed by rule.** Closures sit at fixed fractions of each route, two per route.
  Closures chosen by the importance of a road to the network [28] were not used. Scenarios of one route
  are not independent (Section 7.5).
- **Historical end points are pinned by hand**, and the University Road case is one speed (10 km/h)
  over the whole stretch.
- **Checks with known gaps.** The leak check looks only at the vertices of a returned route line, so a
  long straight segment could cross a circle unseen. A historical chain gets `max(2, round(L/100) + 1)`
  circles of 60 m for a stretch of length L metres, which leaves small gaps between circles only on
  stretches of just over 120 m to under 150 m and just over 240 m to 250 m (Python rounds 2.5 down to
  2); the real stretches are kilometres long.
- **A committed point that a new closure makes unreachable** currently gives a failed proposal with the
  reason "campus unreachable", which does not name the real cause.
- **Free travel-time options not tested.** Two other free sources were not tried: per-request road
  exclusion on the public Valhalla server, whose route service accepts exclusions according to its
  documentation (whether its table service does, and what limits the public server sets, is
  unverified); and OSRM itself run inside the 512 MB limit. The work plan (Section 8.1) dropped both
  probes of its first draft and keeps them here as untested options.
- **Machines differ.** Some runs are on a Windows laptop without limits and some on WSL with limits;
  their memory figures are different measures and are not pooled.
- **Cuts from the work plan:** none so far **[pending: entry L11]**.

<!-- Lead: the Valhalla claim comes from the work plan, not from a source in the literature note.
Either add a dated citation of the Valhalla documentation or keep it as stated, unverified. -->

## 11. Summary

[pending: entries L8, L9, L10].

## References

[1] J. R. Current, H. Pirkul, and E. Rolland, "Efficient algorithms for solving the shortest covering
path problem," *Transportation Science*, vol. 28, no. 4, pp. 317-327, 1994.

[2] M. Gendreau, G. Laporte, and F. Semet, "The covering tour problem," *Operations Research*, vol. 45,
no. 4, pp. 568-576, 1997.

[3] J. R. Current, C. S. ReVelle, and J. L. Cohon, "The median shortest path problem," *Transportation
Science*, vol. 21, no. 3, pp. 188-197, 1987.

[4] N. Jozefowiez, F. Semet, and E.-G. Talbi, "The bi-objective covering tour problem," *Computers &
Operations Research*, vol. 34, no. 7, pp. 1929-1942, 2007.

[5] E. Glize, R. Roberti, N. Jozefowiez, and S. U. Ngueveu, "Exact methods for mono-objective and
bi-objective multi-vehicle covering tour problems," *European Journal of Operational Research*,
vol. 283, no. 3, pp. 812-824, 2020.

[6] A. N. Letchford, S. D. Nasiri, and D. O. Theis, "Compact formulations of the Steiner traveling
salesman problem and related problems," *European Journal of Operational Research*, vol. 228, no. 1,
pp. 83-92, 2013.

[7] P. Schittekat, J. Kinable, K. Sörensen, M. Sevaux, F. Spieksma, and J. Springael, "A metaheuristic
for the school bus routing problem with bus stop selection," *European Journal of Operational Research*,
vol. 229, no. 2, pp. 518-528, 2013.

[8] H. I. Calvete, C. Galé, J. A. Iranzo, and P. Toth, "A partial allocation local search matheuristic
for solving the school bus routing problem with bus stop selection," *Mathematics*, vol. 8, art. 1214,
2020.

[9] P. Czioska, R. Kutadinata, A. Trifunović, S. Winter, M. Sester, and B. Friedrich, "Real-world
meeting points for shared demand-responsive transportation systems," arXiv:1709.08488.

[10] A. El-Geneidy, M. Grimsrud, R. Wasfi, P. Tétreault, and J. Surprenant-Legault, "New evidence on
walking distances to transit stops," *Transportation*, vol. 41, no. 1, pp. 193-210, 2014.

[11] F. Errico, T. G. Crainic, F. Malucelli, and M. Nonato, "A survey on planning semi-flexible transit
systems," *Transportation Research Part C*, vol. 36, pp. 324-338, 2013.

[12] V. Pillac, M. Gendreau, C. Guéret, and A. L. Medaglia, "A review of dynamic vehicle routing
problems," *European Journal of Operational Research*, vol. 225, no. 1, pp. 1-11, 2013.

[13] H. N. Psaraftis, M. Wen, and C. A. Kontovas, "Dynamic vehicle routing problems: Three decades and
counting," *Networks*, vol. 67, no. 1, pp. 3-31, 2016.

[14] A. Sun and M. Hickman, "The real-time stop-skipping problem," *Journal of Intelligent
Transportation Systems*, vol. 9, no. 2, pp. 91-109, 2005.

[15] J.-Q. Li, P. B. Mirchandani, and D. Borenstein, "Real-time vehicle rerouting problems with time
windows," *European Journal of Operational Research*, vol. 194, no. 3, pp. 711-727, 2009.

[16] O. J. Ibarra-Rojas, F. Delgado, R. Giesen, and J. C. Muñoz, "Planning, operation, and control of bus
transport systems: A literature review," *Transportation Research Part B*, vol. 77, pp. 38-75, 2015.

[17] K. Gkiotsalitis and O. Cats, "At-stop control measures in public transport: Literature review and
research agenda," *Transportation Research Part E*, vol. 145, art. 102176, 2021.

[18] D. Delling, A. V. Goldberg, T. Pajor, and R. F. Werneck, "Customizable route planning," in *Proc.
10th Int. Symp. Experimental Algorithms (SEA)*, LNCS 6630, 2011.

[19] H. Bast, D. Delling, A. Goldberg, M. Müller-Hannemann, T. Pajor, P. Sanders, D. Wagner, and
R. F. Werneck, "Route planning in transportation networks," arXiv:1504.05140, 2015.

[20] Project OSRM, "OSRM documentation v26.5.0: command-line tools." [Online]. Available:
https://project-osrm.org/docs/v26.5.0/tools

[21] Project OSRM, "Traffic," osrm-backend wiki. [Online]. Available:
https://github.com/Project-OSRM/osrm-backend/wiki/Traffic

[22] S. Zilberstein, "Using anytime algorithms in intelligent systems," *AI Magazine*, vol. 17, no. 3,
p. 73, 1996.

[23] M. Likhachev, G. Gordon, and S. Thrun, "ARA*: Anytime A* with provable bounds on sub-optimality,"
in *Advances in Neural Information Processing Systems (NIPS)*, 2003.

[24] Y. He, J. Rentschler, P. Avner, J. Gao, X. Yue, and J. Radke, "Mobility and resilience: A global
assessment of flood impacts on road transportation networks," World Bank Policy Research Working Paper
10049, 2022.

[25] Aaj English TV, report on the closure of Shahrah-e-Faisal, 24 February 2024. [Online]. Available:
https://english.aaj.tv/news/30352283

[26] E. Hussain, S. Ahmed, and M. S. Ali, "Modeling the effects of rainfall on vehicular traffic,"
*Journal of Modern Transportation*, vol. 26, pp. 133-146, 2018.

[27] N. H. Anwar and A. Shakeel, "Disconnected mobility infrastructures: Female domestic workers and the
perils of bus transport in Karachi," Mahbub ul Haq Research Centre, LUMS, 2023.

[28] E. Jenelius, T. Petersen, and L.-G. Mattsson, "Importance and exposure in road network
vulnerability analysis," *Transportation Research Part A*, vol. 40, no. 7, pp. 537-560, 2006.

## Appendix A. Reproducing the results

Commands run from `research/`. The offline builds need the Docker laptop, the N1 map file and OSRM; the
experiments need only the repository's data files.

| Result | Command | Output |
| --- | --- | --- |
| Road graph (L2) | `python build_graph.py PATH/karachi.osm.pbf` | `data/graph_karachi_v1/` |
| Road-block test (L3) | `python run_roadblock.py` | `results/roadblock/result.json` |
| Walking distances (L4) | `python build_walk.py` | `data/walk_fall2026_v1.json` |
| Corridors (L5) | `python build_corridors.py` | `data/corridors_fall2026_v1/` |
| Calibration (L5) | `python calibrate_graph.py` | `speed_factor` in the graph's `meta.json` |
| Gate G1 timings (L5) | `python measure_graph.py --limited` (WSL) | `results/graph-timing/timing.json` |
| Scenarios (L6) | `python build_scenarios.py` | `data/scenarios_reroute_v1.json` |
| Quality pass (L8) | `python run_reroute.py quality --workers 2` | `results/reroute-quality/` |
| Limits pass (L9) | `python run_reroute.py limits` (WSL) | `results/reroute-limits/` |
| Rerouting scaling (L10) | `python run_reroute.py scale` | `results/reroute-scale/` |
| Optimizer scaling (L10) | `python run_scale.py` | `results/optimizer-scale/` |

Each pass also runs from the research hub, which records the code version with every run. Every pass
has a `--quick` variant on the toy file; its folder ends in `-quick` and holds no reported result.

## Appendix B. Notes for the authors (remove before submission)

- **Sources of numbers.** Apart from the logbook, this draft uses the lead's notes of 17 November for:
  the R3 development timings (Section 6.3), the 34-of-800 count (also in the logbook), the row cache's
  byte cap, and the judging details of Section 7.5. The straight-line walking shares (30% and 65%) are
  from the work plan, Section 4. Put each of these in the logbook, or replace it with a logged figure,
  before the chapter is final.
- **References.** Every reference is taken from the literature note and is marked [V] there. None was
  re-opened while writing this draft and none is cited from memory. Check the DOI of [14] (unverified
  in the note) and add a source for the Held-Karp name if it is used. The Valhalla statement in
  Section 10 has no source in the note.
- **Arithmetic, not measurement.** The 39 MB and 52 MB state sizes (Section 6.3, 6.5), the walkers'
  ready times (Section 3) and the "70 s at 0.1 CPU" estimate (Section 6.3) are computed from the code
  or from earlier results, not measured.
- **Figures.** None embedded. Suggested once runs exist: delay by method and walking limit (RQ1); gap to
  the oracle against time, per arm (RL1), which is the anytime profile the literature note recommends;
  R3 time against stops (RS1); time until every bus has a plan against buses (RS1).
- **Format.** Markdown with IEEE-style numbered references, as in the optimization chapter.
