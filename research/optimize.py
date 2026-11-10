"""Plan all-stop morning routes per contractor and compare them with the current routes.

    python research/optimize.py --time-limit 60
    python research/optimize.py --time-limit 10 --contractor Jadoon

Model (decisions logged 2026-11-03 in LOGBOOK.md):
- Each contractor plans its own stops with its own buses; every stop is visited.
- A bus starts at its first stop and ends at campus, arriving exactly at 08:00.
- Stop time: 60 s plus 5 s per student. Bus capacity is respected.
- No student rides longer than 90 minutes (pickup to campus).
- Objective: total student ride time (each student's minutes from pickup to campus),
  plus driving seconds as a small tie-breaker.

Writes research/results/<run_id>.json (all numbers) and <run_id>.html (map + search progress).
Research only: no Django, no website settings, no database.
"""
import argparse
import json
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

ROOT = Path(__file__).resolve().parent
DATA, RESULTS = ROOT / "data", ROOT / "results"
DEADLINE = 3 * 3600          # 08:00, with time measured from 05:00
MAX_RIDE_S = 90 * 60
STOP_BASE_S, STOP_PER_STUDENT_S = 60, 5


def sparse_estimate(T, points, k):
    """Query experiment: keep real times only for each stop to its k nearest stops (by straight line)
    and to campus; estimate every other pair as a + b * straight-line metres, fitted on the kept pairs.
    Returns the matrix the optimizer plans on and what it cost. T itself is never changed."""
    import math
    n = len(T)
    rad = math.pi / 180

    def dist(i, j):
        (la1, lo1), (la2, lo2) = points[i], points[j]
        x = (lo2 - lo1) * rad * math.cos((la1 + la2) * rad / 2)
        return 6371000 * math.hypot(x, (la2 - la1) * rad)

    D = [[dist(i, j) for j in range(n)] for i in range(n)]
    queried = {(i, 0) for i in range(1, n)}                        # every stop to campus
    for i in range(1, n):
        near = sorted((j for j in range(1, n) if j != i), key=lambda j: D[i][j])[:k]
        queried.update((i, j) for j in near)
    xs = [D[i][j] for i, j in queried]
    ys = [T[i][j] for i, j in queried]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    M = [[T[i][j] if (i, j) in queried or i == j else a + b * D[i][j] for j in range(n)] for i in range(n)]
    errs = sorted(abs(M[i][j] - T[i][j]) / T[i][j] for i in range(1, n) for j in range(1, n)
                  if i != j and (i, j) not in queried and T[i][j] > 0)
    info = {"k": k, "queried_cells": len(queried), "full_cells": n * (n - 1),
            "query_share": round(len(queried) / (n * (n - 1)), 4),
            "fit_s": {"a": round(a, 1), "b_per_km": round(b * 1000, 1)},
            "estimate_median_abs_error_pct": round(100 * errs[len(errs) // 2], 1) if errs else 0.0}
    return M, info


def stop_time(students):
    return STOP_BASE_S + STOP_PER_STUDENT_S * students if students else 0


def score(routes, T, q):
    """Score routes (lists of node indices ending before campus 0) on matrix T, arriving at 08:00."""
    rides, total_ride, drive, longest, over_cap = [], 0, 0, 0, 0
    for stops in routes:
        legs = [T[a][b] for a, b in zip(stops, stops[1:] + [0])]
        drive += sum(legs)
        # time left until campus after leaving each stop, working backwards from 08:00
        remaining, after = 0, []
        for leg, node in zip(reversed(legs), reversed(stops)):
            remaining += leg
            after.append((node, remaining))
            remaining += stop_time(q[node])
        for node, left in after:
            ride = left + stop_time(q[node])
            rides.append(ride)
            total_ride += ride * q[node]
            longest = max(longest, ride)
    return {"buses_used": sum(1 for r in routes if r),
            "total_student_ride_min": round(total_ride / 60),
            "mean_ride_min": round(total_ride / 60 / max(1, sum(q)), 1),
            "longest_ride_min": round(longest / 60, 1),
            "stops_over_90_min": sum(1 for r in rides if r > MAX_RIDE_S),
            "bus_driving_min": round(drive / 60)}


def solve(T, q, capacities, time_limit):
    n = len(T)                       # node 0 campus, 1..n-1 stops
    dummy, size, buses = n, n + 1, len(capacities)
    manager = pywrapcp.RoutingIndexManager(size, buses, [dummy] * buses, [0] * buses)
    routing = pywrapcp.RoutingModel(manager)

    def drive(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        if a == dummy:
            return 0
        if b == dummy:
            return 10 ** 7
        return int(T[a][b])

    def transit(i, j):
        a = manager.IndexToNode(i)
        return drive(i, j) + (stop_time(q[a]) if a not in (0, dummy) else 0)

    drive_cb = routing.RegisterTransitCallback(drive)
    time_cb = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(drive_cb)

    demand_cb = routing.RegisterUnaryTransitCallback(
        lambda i: 0 if manager.IndexToNode(i) in (0, dummy) else q[manager.IndexToNode(i)])
    routing.AddDimensionWithVehicleCapacity(demand_cb, 0, capacities, True, "Load")

    routing.AddDimension(time_cb, 0, DEADLINE, False, "Time")   # no waiting mid-route
    tdim = routing.GetDimensionOrDie("Time")
    for v in range(buses):
        tdim.CumulVar(routing.End(v)).SetValue(DEADLINE)          # arrive exactly 08:00
    for node in range(1, n):
        idx = manager.NodeToIndex(node)
        tdim.CumulVar(idx).SetMin(DEADLINE - MAX_RIDE_S)          # ride at most 90 min
        # cost q * (08:00 - pickup) = this stop's student ride seconds; x1 per second
        tdim.SetCumulVarSoftLowerBound(idx, DEADLINE, q[node])
        routing.AddDisjunction([idx], 10 ** 9)                    # dropped only if impossible

    progress, t0 = [], time.perf_counter()
    routing.AddAtSolutionCallback(lambda: progress.append(
        (round(time.perf_counter() - t0, 2), routing.CostVar().Max())))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(time_limit)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return None, progress
    routes = []
    for v in range(buses):
        idx, stops = routing.Start(v), []
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node not in (0, dummy):
                stops.append(node)
            idx = solution.Value(routing.NextVar(idx))
        routes.append(stops)
    visited = {s for r in routes for s in r}
    return {"routes": routes, "dropped": [i for i in range(1, n) if i not in visited]}, progress


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=int, default=60, help="search seconds per contractor")
    ap.add_argument("--contractor", default=None)
    ap.add_argument("--tag", default="", help="label added to the run id, e.g. limited")
    ap.add_argument("--render", metavar="RUN_JSON", help="only rebuild the HTML page of an earlier run")
    ap.add_argument("--out-dir", type=Path, default=RESULTS, help="where to write the run files")
    ap.add_argument("--run-id", default=None, help="fixed run id instead of a timestamp (used by run_budget.py)")
    ap.add_argument("--no-html", action="store_true", help="write only the JSON")
    ap.add_argument("--k", type=int, default=0,
                    help="query experiment: plan on real times to the k nearest stops only, the rest estimated "
                         "(0 = full real matrix). Plans are always scored on the full real matrix.")
    args = ap.parse_args()
    if args.render:
        run = Path(args.render)
        inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
        write_html(run.with_suffix(".html"), json.loads(run.read_text()), inst)
        print(f"wrote {run.with_suffix('.html')}")
        return

    inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
    mat = json.loads((DATA / "matrix_fall2026_v1.json").read_text())
    by_name = {s["name"]: s for s in inst["stops"]}
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"opt-{stamp}-t{args.time_limit}" + (f"-{args.tag}" if args.tag else "")
    report = {"run_id": run_id, "instance": inst["version"], "time_limit_s": args.time_limit,
              "model": {"deadline": "08:00", "max_ride_min": 90, "stop_time": "60 s + 5 s/student",
                        "objective": "total student ride time, driving time as tie-breaker"},
              "contractors": {}}

    for cname, c in inst["contractors"].items():
        if args.contractor and cname != args.contractor:
            continue
        m = mat["contractors"][cname]
        nodes, T = m["nodes"], m["durations_s"]
        q = [0] + [by_name[n]["students"].get(cname, 0) for n in nodes[1:]]
        pos = {n: i for i, n in enumerate(nodes)}
        caps = [b["capacity"] for b in c["buses"]]

        baseline_routes = [[pos[s] for s in r["stops"]] for r in c["baseline_routes"]]
        baseline = score(baseline_routes, T, q)

        cpu0, wall0 = time.process_time(), time.perf_counter()
        if args.k:
            points = [(inst["campus"]["lat"], inst["campus"]["lng"])] + \
                     [(by_name[n]["lat"], by_name[n]["lng"]) for n in nodes[1:]]
            T_plan, matrix_info = sparse_estimate(T, points, args.k)
        else:
            T_plan, matrix_info = T, {"k": 0, "queried_cells": len(T) * (len(T) - 1),
                                      "full_cells": len(T) * (len(T) - 1), "query_share": 1.0}
        result, progress = solve(T_plan, q, caps, args.time_limit)
        cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
        entry = {"baseline": baseline, "solve_wall_s": round(wall, 1), "solve_cpu_s": round(cpu, 1),
                 "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                 "progress": progress, "matrix": matrix_info}
        if result is None:
            entry["optimized"] = None
            print(f"{cname}: no feasible plan found in {args.time_limit} s")
        else:
            opt = score(result["routes"], T, q)          # always the real matrix
            opt["dropped_stops"] = [nodes[i] for i in result["dropped"]]
            entry["optimized"] = opt
            entry["routes"] = [[nodes[i] for i in r] for r in result["routes"] if r]
            delta = (opt["total_student_ride_min"] - baseline["total_student_ride_min"]) / baseline["total_student_ride_min"]
            print(f"{cname}: current {baseline['total_student_ride_min']} student-min, "
                  f"{baseline['buses_used']} buses, longest {baseline['longest_ride_min']} min | "
                  f"optimized {opt['total_student_ride_min']} student-min ({delta:+.1%}), "
                  f"{opt['buses_used']} buses, longest {opt['longest_ride_min']} min, "
                  f"dropped {len(opt['dropped_stops'])} | {wall:.0f} s wall, peak {entry['peak_rss_mb']} MB")
        entry["baseline_routes"] = [r["stops"] for r in c["baseline_routes"]]
        report["contractors"][cname] = entry

    (out / f"{run_id}.json").write_text(json.dumps(report, indent=1))
    if not args.no_html:
        write_html(out / f"{run_id}.html", report, inst)
    print(f"wrote {out / run_id}.json" + ("" if args.no_html else " and .html"))


def write_html(path, report, inst):
    stops = {s["name"]: [s["lat"], s["lng"]] for s in inst["stops"]}
    stops["CAMPUS"] = [inst["campus"]["lat"], inst["campus"]["lng"]]
    students = {s["name"]: s["students"] for s in inst["stops"]}
    payload = json.dumps({"report": report, "stops": stops, "students": students})
    path.write_text(HTML.replace("__DATA__", payload).replace("__TITLE__", report["run_id"]))


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--good:#047857;--bad:#b91c1c;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#111827;color:#fff;padding:18px 24px}header h1{margin:0;font-size:20px;font-weight:600}
header p{margin:4px 0 0;color:#cbd5e1;font-size:13px}main{max-width:1280px;margin:0 auto;padding:20px 16px}
.bar{display:flex;gap:8px;align-items:center;margin-bottom:16px}.bar button{border:1px solid var(--line);background:#fff;padding:7px 14px;border-radius:8px;cursor:pointer;font:inherit}
.bar button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.card .v{font-size:24px;font-weight:600;margin-top:4px}
.card .d{font-size:13px;margin-top:2px}.good{color:var(--good)}.bad{color:var(--bad)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:16px}
.panel h2{font-size:15px;margin:0 0 10px}.maps{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:800px){.maps{grid-template-columns:1fr}}.map{height:480px;border-radius:8px;border:1px solid var(--line)}
.map-title{font-weight:600;margin-bottom:6px}table{width:100%;border-collapse:collapse}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:500;font-size:12px;text-transform:uppercase}.note{color:var(--muted);font-size:12px;margin-top:8px}
svg text{font:12px system-ui,sans-serif;fill:var(--muted)}
</style></head><body>
<header><h1>Route optimization run</h1><p id="sub"></p></header>
<main><div class="bar" id="tabs"></div><div class="cards" id="cards"></div>
<div class="panel"><h2>Routes</h2><div class="maps"><div><div class="map-title">Current routes</div><div id="m1" class="map"></div></div>
<div><div class="map-title">Optimized routes</div><div id="m2" class="map"></div></div></div>
<div class="note">One colour per bus. Solid lines join stops in visiting order; the dashed line is the drive from the last stop to campus. Straight lines, not roads. Maps move together. Hover a stop for its name and students.</div></div>
<div class="panel"><h2>Comparison</h2><div id="table"></div></div>
<div class="panel"><h2>How the search improved the plan</h2><svg id="chart" viewBox="0 0 900 300" width="100%"></svg>
<div class="note">Each step is a better plan found. Steep early drop, then flat: extra search time stops paying off where the line flattens.</div></div>
</main><script>
const D=__DATA__,R=D.report,S=D.stops,ST=D.students,names=Object.keys(R.contractors);let cur=names[0];
document.getElementById('sub').textContent=`${R.run_id} · instance ${R.instance} · search limit ${R.time_limit_s} s per contractor · synthetic students, free-flow travel times`;
const tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',attr='Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors';
const maps=['m1','m2'].map(id=>{const m=L.map(id,{zoomControl:true});L.tileLayer(tiles,{attribution:attr,maxZoom:16}).addTo(m);return m});
const layers=maps.map(m=>L.layerGroup().addTo(m));let sync=false;
maps.forEach((m,i)=>m.on('move',()=>{if(sync)return;sync=true;maps[1-i].setView(m.getCenter(),m.getZoom(),{animate:false});sync=false}));
const colour=i=>`hsl(${(i*137.5)%360},65%,45%)`;
function draw(layer,routes,c){layer.clearLayers();routes.forEach((r,i)=>{const pts=r.map(n=>S[n]);
 L.polyline(pts,{color:colour(i),weight:3,opacity:.9}).addTo(layer);
 L.polyline([pts[pts.length-1],S.CAMPUS],{color:colour(i),weight:1.5,opacity:.35,dashArray:'4 6'}).addTo(layer);
 r.forEach(n=>L.circleMarker(S[n],{radius:4,color:'#fff',weight:1,fillColor:colour(i),fillOpacity:1}).bindTooltip(`${n}: ${(ST[n]||{})[c]||0} students`).addTo(layer))});
 L.circleMarker(S.CAMPUS,{radius:8,color:'#111827',fillColor:'#facc15',fillOpacity:1,weight:2}).bindTooltip('FAST NUCES campus').addTo(layer)}
function pct(a,b){const p=(b-a)/a*100;return isFinite(p)?`${p>0?'+':''}${p.toFixed(1)}%`:''}
function card(k,a,b,lowerBetter=true){const better=lowerBetter?b<a:b>a,cls=b===a?'':(better?'good':'bad');
 return `<div class="card"><div class="k">${k}</div><div class="v">${b??'-'}</div><div class="d ${cls}">${a} now ${b!=null?'· '+pct(a,b):''}</div></div>`}
function show(){document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.c===cur));
 const c=R.contractors[cur],b=c.baseline,o=c.optimized||{};
 document.getElementById('cards').innerHTML=card('Total student ride (min)',b.total_student_ride_min,o.total_student_ride_min)+
  card('Mean ride (min)',b.mean_ride_min,o.mean_ride_min)+card('Longest ride (min)',b.longest_ride_min,o.longest_ride_min)+
  card('Buses used',b.buses_used,o.buses_used)+`<div class="card"><div class="k">Compute</div><div class="v">${c.solve_wall_s} s</div><div class="d">${c.solve_cpu_s} s CPU · peak ${c.peak_rss_mb} MB</div></div>`;
 const rows=[['Buses used','buses_used'],['Total student ride (min)','total_student_ride_min'],['Mean ride (min)','mean_ride_min'],['Longest ride (min)','longest_ride_min'],['Stops over 90 min','stops_over_90_min'],['Bus driving (min)','bus_driving_min']];
 document.getElementById('table').innerHTML='<table><tr><th>Measure</th><th>Current</th><th>Optimized</th><th>Change</th></tr>'+
  rows.map(([l,k])=>`<tr><td>${l}</td><td>${b[k]}</td><td>${o[k]??'-'}</td><td>${o[k]!=null?pct(b[k],o[k]):''}</td></tr>`).join('')+'</table>'+
  `<div class="note">Stops dropped: ${(o.dropped_stops||[]).length}. Both plans scored the same way on the same travel-time matrix.</div>`;
 draw(layers[0],c.baseline_routes,cur);draw(layers[1],c.routes||[],cur);
 maps[0].fitBounds(L.latLngBounds(c.baseline_routes.flat().map(n=>S[n]).concat([S.CAMPUS])),{padding:[20,20]});
 chart(c.progress)}
function chart(p){const svg=document.getElementById('chart');svg.innerHTML='';if(!p.length)return;
 const W=900,H=300,l=70,r=20,t=20,bm=40,t1=Math.max(...p.map(x=>x[0]),1),v=p.map(x=>x[1]/60),y0=Math.min(...v),y1=Math.max(...v);
 const X=s=>l+(W-l-r)*s/t1,Y=y=>t+(H-t-bm)*(y1===y0?.5:(y1-y)/(y1-y0));let g='';
 for(let i=0;i<=4;i++){const y=y0+(y1-y0)*i/4;g+=`<line x1="${l}" x2="${W-r}" y1="${Y(y)}" y2="${Y(y)}" stroke="#eef0f3"/><text x="${l-8}" y="${Y(y)+4}" text-anchor="end">${Math.round(y).toLocaleString()}</text>`}
 for(let i=0;i<=4;i++){const s=t1*i/4;g+=`<text x="${X(s)}" y="${H-bm+18}" text-anchor="middle">${s.toFixed(s<10?1:0)} s</text>`}
 let d='';p.forEach(([s,_],i)=>{d+=i?` H${X(s)} V${Y(v[i])}`:`M${X(s)} ${Y(v[i])}`});d+=` H${X(t1)}`;
 svg.innerHTML=g+`<path d="${d}" fill="none" stroke="#2563eb" stroke-width="2.5"/><text x="${l}" y="12">Cost of best plan (approx. student-minutes)</text>
 <text x="${W-r}" y="${H-4}" text-anchor="end">search time · ${p.length} improvements</text>`}
names.forEach(n=>{const b=document.createElement('button');b.textContent=n;b.dataset.c=n;b.onclick=()=>{cur=n;show()};document.getElementById('tabs').append(b)});
show();
</script></body></html>"""

if __name__ == "__main__":
    main()
