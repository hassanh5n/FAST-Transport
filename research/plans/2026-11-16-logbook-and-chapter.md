# Logbook and Chapter Plan (work items C1, S1, S2)

This plan has no code. It lists the logbook entries the rerouting work must produce, in order, with a
draft of the first one, and the outline of the chapter.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2).

**Rules that apply to every entry** (from the logbook itself and the 10 November review):

- Entries are dated and appended. An old entry is never rewritten; a correction is a new entry.
- The entry with a pass or fail rule is **pushed before the first run** it governs.
- Thresholds are judged on the worst case as well as the median.
- Result entries are written the same day as the run. The traffic and seed results waited five days.

---

## Entries, in order

| # | Entry | When | Gates |
| --- | --- | --- | --- |
| L1 | Rerouting: problem, methods, scenario rules, thresholds, gate rules | Tue 17 Nov | Everything else |
| L2 | Map file hash; graph built (counts) | Wed 18 Nov | - |
| L3 | Road-block test results | Fri 20 Nov | Scenario build |
| L4 | Walking distances (detour factor, shares) | Sun 22 Nov | - |
| L5 | Graph calibration and timings under limits; gate G1 verdict | Sun 22 Nov | Limits pass design stands or falls back |
| L6 | Scenarios frozen (counts, tags, leaks, build time) | Thu 26 Nov | Runs |
| L7 | Optimizer scaling: planned | before that run | Optimizer scaling run |
| L8 | Quality pass results | day of run | - |
| L9 | Limits pass results | day of run | - |
| L10 | Scaling results, rerouting and optimizer | day of run | - |
| L11 | Any cut taken from the work plan's cut order | when taken | - |

- [ ] L1 pushed
- [ ] L2 written
- [ ] L3 written
- [ ] L4 written
- [ ] L5 written
- [ ] L6 written
- [ ] L7 pushed before the optimizer scaling run
- [ ] L8 written
- [ ] L9 written
- [ ] L10 written

---

## Draft of entry L1

Edit the values marked **[decide]** with the team, then append to `LOGBOOK.md` and push. Nothing that
uses the scenario file may run before this is pushed.

```markdown
## 2026-11-17: Rerouting: problem, methods and rules (fixed before any scenario exists)

Plan: `research/plans/2026-11-15-rerouting-plan.md` (version 2). This entry fixes what the experiments
will judge. It is written before the scenario file is built, so no delay has been seen.

**Problem (one bus, morning run)**

- Given: bus position and time; remaining stops with students, a walking limit and a must-serve flag;
  candidate boarding points (the remaining stops plus other known stops within 800 m walk); walking
  distances from OSRM's foot profile; one or more closures; points already committed to.
- Decide: which candidates to visit, in what order, and where each stop's students board.
- Rules: every stop boards at one visited point within its walking limit; a must-serve stop boards at
  itself; stop time 60 s per visited point plus 5 s per student; walkers start **[decide: 60 s]** after
  the decision at **[decide: 1.2 m/s]**; the bus does not leave a point before its walkers arrive.
- Reachability: a point inside a full-block closure cannot be visited, in both travel-time sources.
  A stop with no boarding point in range is `unserved` and counts as a failure.
- Objective: earliest arrival at campus. Total walking breaks ties between plans the solver holds with
  equal arrival; the exact method guarantees the earliest arrival, not the least walking.

**Methods**

- R0: published order, every remaining stop visited, detour around the closure. Baseline.
- R2: greedy (add the point that boards the most students per second of detour, then try removals).
- R3: exact, by dynamic programming over (set of boarded stops, last point). On true travel times with
  no time limit this is the oracle: the best plan in this model, not a bound on any possible reroute.
  Run only for 16 or fewer stops plus committed points.

**Two travel-time sources**

- Truth: OSRM 5.27.1 re-customized with the closure, each time from an untouched copy of its files.
  Used only to build the scenario file and to score plans.
- Under test: a road graph built from the same map file, searched in memory on a corridor around the
  route. Plans made on it are scored on the truth. `backend/apps/transport/corridor.py` already holds
  a greedy covering-path heuristic for drawing route lines on the public Valhalla server; R2 here is
  a separate implementation for a blocked network.

**Scenarios**

- Synthetic: for each current route with at least 3 stops, two full-block closures, each a 200 m circle
  at the middle of a leg between two stops: leg ceil(n/3) and leg ceil(2n/3). Two bus positions each:
  at the first stop with nothing served, and at the last stop before the closure.
- Historical, reported separately and never pooled: Shahrah-e-Faisal between Karsaz and FTC, full
  block; University Road between Hasan Square and NIPA, slowed to 10 km/h.
- This narrows the 10 November wording "on or near shuttle routes" to closures on routes; a 200 m
  circle also closes the side roads beside them.
- Judged set: scenarios with at least 2 remaining stops where R0 loses at least 60 s. The share outside
  it is reported.

**Thresholds, fixed now, judged on synthetic scenarios in the judged set**

Quality pass (true times, no time limit; walking limits 0, 400, 800 m):
1. Closure-specific gain at 400 m, that is (R0 minus R3 with the closure) minus (R0 minus R3 with no
   closure): median at least **[decide: 60 s]**.
2. R2's delay within **[decide: 60 s]** of R3's in at least **[decide: 90%]** of scenarios, and on the
   median of every route.
3. No run has a student walking beyond the limit or unserved where a boarding point exists, and R3
   never arrives later than R0.

Limits pass (512 MB, no swap, 0.1 CPU; graph loaded; plans made on the graph; 3 repeats; worst repeat):
4. A valid plan within **[decide: 5 s]** in at least **[decide: 95%]** of scenarios.
5. At 30 s, delay within **[decide: 60 s]** of the oracle's in at least **[decide: 90%]** of scenarios.
6. Peak memory under 400 MB including the graph.

Reported, not judged: must-serve stops (25% of remaining stops, fixed draw); the two arms that separate
graph error from the time limit; results per route with the worst route named; scaling runs.

**Gate rules for week 1, fixed now**

- Graph calibration against matrix M1: median absolute error at most 15%, median signed error not
  negative. One factor first; one factor per road class if that fails.
- Graph timing on the longest route's corridor under the limits: the 14 rows R0 needs in at most 5 s,
  31 rows in at most 30 s.
- If either fails: the limits pass plans on saved pre-closure times, reports solver-only time, and the
  travel-time source is stated as a limitation.

**Caveats carried over**: synthetic students; OSRM free-flow times as truth; limits simulated with
cgroups on a laptop; the bus is assumed to be at a stop when the closure is reported.
```

---

## Result entry template (L8, L9, L10)

Follow the T1 and S1 entries:

1. Heading with the date and the run label (`RQ1` quality, `RL1` limits, `RS1` rerouting scaling, `OS1` optimizer scaling).
2. When it ran, machine, code version, how many runs, any failed or rerun rows.
3. Tables: by walking limit and method (quality); by checkpoint and arm (limits); the curves as tables (scaling).
4. Results per route, with the worst route named.
5. **Verdict against the thresholds fixed on 2026-11-17**, one line each, pass or fail with the number.
6. Observations for the report.
7. What the run does not show.

---

## Chapter outline (S2)

File: `research/report/rerouting_chapter.md`, in the same form as `optimization_chapter.md`.

| Section | Source | Can be written from |
| --- | --- | --- |
| 1. Introduction and question | Work plan Section 1; logbook 10 Nov | now |
| 2. Background: covering paths, stop skipping, dynamic rerouting | Literature note | now |
| 3. Problem model | Entry L1 | 17 Nov |
| 4. Travel times after a closure: OSRM as truth, the road graph, corridors | Entries L2, L3, L5 | 22 Nov |
| 5. Scenarios and walking distances | Entries L4, L6 | 26 Nov |
| 6. Methods R0, R2, R3 and the ladder | Solver plan; code | 22 Nov |
| 7. Experimental method | Entry L1 | 17 Nov |
| 8. Results: quality, limits, scaling | Entries L8 to L10 | after runs |
| 9. Discussion and what it means for the website | Work plan Section 12 | after runs |
| 10. Limitations | Entries' caveats; work plan Section 13 | after runs |

- [ ] Sections 1, 2, 3, 7 drafted (week 1)
- [ ] Sections 4, 5, 6 drafted (week 2)
- [ ] Sections 8, 9, 10 drafted (week 3)
- [ ] References checked against the literature note's verification marks; none cited from memory
- [ ] Internal review by a second team member, Friday 4 December

Points the chapter must state, because reviewers of the plan raised them:

- The oracle is the best plan in the model, not a bound on any reroute.
- The exact method guarantees the earliest arrival, not the least walking.
- Skipping a stop saves stop time on any day; the walking result is reported net of the no-closure control.
- Scenarios from one route are not independent; results are also given per route.
- Which free travel-time options were not tested (per-request exclusion on a public Valhalla server; OSRM on a second free instance).
- Every item taken from the cut order.
