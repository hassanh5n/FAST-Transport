'use strict';
/* FleetCentric research site. Same file for the local hub (with run controls) and the
   shared GitHub Pages copy (read-only). Data comes from data/index.json, built by build_site.py. */

const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => (n == null ? '–' : Number(n).toLocaleString());
const sign = n => (n == null ? '–' : `${n > 0 ? '+' : ''}${n}%`);
const when = iso => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '–');
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

let D = null;          // index.json
let LOCAL = false;     // true when served by serve.py
let STATUS = null;     // /api/status
let PAGE = 'overview';
let maps = [];
let runFilter = 'all';
let lastVersion = null;

const NAV = [['overview', 'Overview'], ['experiments', 'Experiments'], ['runs', 'Runs'], ['data', 'Data'], ['docs', 'Documents']];

async function loadIndex() {
  const r = await fetch('data/index.json', { cache: 'no-store' });
  D = await r.json();
  D.stopsByName = Object.fromEntries(D.dataset.stops.map(s => [s[0], s]));
}

async function api(path, body) {
  const r = await fetch('api/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Hub': '1', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

/* ------------------------------------------------------------------ shell */

function renderNav() {
  const items = LOCAL ? [...NAV, ['control', 'Run & publish']] : NAV;
  $('#nav').innerHTML = items.map(([id, label]) => `<a href="#/${id}" class="${PAGE === id ? 'on' : ''}">${label}</a>`).join('');
  $('#sub').textContent = D.project.subtitle;
  $('#mode').innerHTML = LOCAL
    ? '<span class="dot live"></span>Local hub'
    : `<span class="dot"></span>Shared view · updated ${esc(when(D.generated_at))}`;
  $('#foot').innerHTML = `Built ${esc(when(D.generated_at))}${D.git && D.git.commit ? ` from commit <code>${esc(D.git.commit.slice(0, 7))}</code>` : ''} · ` +
    `${esc(D.project.caveats.join(' '))}`;
}

function clearMaps() { maps.forEach(m => m.remove()); maps = []; }

function route() {
  const h = location.hash.replace(/^#\/?/, '') || 'overview';
  const [page, ...rest] = h.split('/');
  const arg = rest.map(decodeURIComponent).join('/');
  PAGE = page;
  clearMaps();
  renderNav();
  const v = $('#view');
  v.innerHTML = '';
  const views = {
    overview: viewOverview, experiments: arg ? () => viewExperiment(v, arg) : viewExperiments,
    runs: arg ? () => viewRun(v, arg) : viewRuns, data: viewData, docs: () => viewDocs(v, arg), control: viewControl,
  };
  (views[page] || viewOverview)(v, arg);
}

function rerenderIfSafe() {
  // Pages with maps or a document open are not redrawn under the reader.
  if (['overview', 'experiments', 'runs', 'control'].includes(PAGE) && !location.hash.match(/#\/runs\/./)) {
    const y = window.scrollY; route(); window.scrollTo(0, y);
  } else renderNav();
}

/* ------------------------------------------------------------------ helpers */

const stateChip = s => `<span class="chip ${{ complete: 'good', partial: 'warn', 'in progress': 'warn', 'not started': '', later: '' }[s] ?? ''}">${esc(s)}</span>`;
const verdictChip = (v, label, final = true) => v == null ? `<span class="chip">${esc(label)}: pending</span>`
  : `<span class="chip ${v === 'pass' ? 'good' : 'bad'}" title="${final ? 'final' : 'based on the runs finished so far'}">${esc(label)}: ${esc(v)}${final ? '' : ' so far'}</span>`;
const bar = (done, total) => `<div class="bar" title="${done} of ${total}"><i style="width:${total ? Math.min(100, done / total * 100) : 0}%"></i></div>`;
const tile = (k, v, d = '') => `<div class="card tile"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
const expById = id => D.experiments.find(e => e.id === id);

function expProgress(e) {
  const s = e.summary;
  return s ? { done: s.runs_done, total: s.runs_total } : { done: 0, total: e.id === 'time-budget' ? 50 : 6 };
}

function expVerdicts(e) {
  const v = (e.summary || {}).verdict || {};
  const T = D.thresholds;
  return verdictChip(v.gap, `Gap at ${T.gap_budget_s} s`, v.complete) + ' ' + verdictChip(v.memory, 'Memory', v.complete);
}

/* ------------------------------------------------------------------ overview */

function viewOverview(v) {
  const P = D.project, ds = D.dataset, cs = Object.values(ds.contractors);
  const main = D.experiments.filter(e => e.main);
  const done = main.filter(e => e.state === 'complete').length;
  const auto = main.filter(e => e.state !== 'complete').map(e => {
    const p = expProgress(e);
    return `Finish the <a href="#/experiments/${e.id}">${esc(e.title)}</a>: ${p.done} of ${p.total} runs done.` +
      (LOCAL ? ` <a href="#/control">Run it here</a>.` : '');
  });
  v.innerHTML = `
  <div class="card hero">
    <div class="row"><span class="chip info">Research question</span><span class="chip">Research only, separate from the website</span></div>
    <p class="q">${esc(P.question)}</p>
    <ul class="caveats">${P.caveats.map(c => `<li>${esc(c)}</li>`).join('')}</ul>
  </div>
  <div class="tiles">
    ${tile('Stops', fmt(ds.stops.length), `${Object.keys(ds.contractors).length} contractors`)}
    ${tile('Current routes', fmt(cs.reduce((a, c) => a + c.routes, 0)), `${fmt(cs.reduce((a, c) => a + c.buses, 0))} buses`)}
    ${tile('Students', fmt(cs.reduce((a, c) => a + c.students, 0)), ds.synthetic ? 'synthetic' : 'real')}
    ${tile('Runs recorded', fmt(D.runs.length), 'optimizer runs with results')}
    ${tile('Experiments complete', `${done} / ${main.length}`, `${D.project.planned_experiments.length} more planned`)}
  </div>
  <div class="grid g2">
    ${P.phases.map(ph => `
      <div class="card phase ${ph.items.every(i => i.status === 'later') ? 'later' : ''}">
        <h2>${esc(ph.name)}</h2>
        ${ph.items.map(it => `
          <div class="item">
            <div class="spread"><h3>${esc(it.title)}</h3>${stateChip(it.status)}</div>
            <p>${esc(it.question)}</p>
            ${it.experiments.map(id => { const e = expById(id); if (!e) return ''; const p = expProgress(e);
              return `<a href="#/experiments/${e.id}" style="text-decoration:none;color:inherit"><div class="row" style="margin-bottom:6px">
                <strong>${esc(e.title)}</strong>${stateChip(e.state)}<span class="muted">${p.done}/${p.total} runs</span></div>
                ${bar(p.done, p.total)}<div class="row" style="margin-top:8px">${expVerdicts(e)}</div></a>`; }).join('')}
          </div>`).join('')}
      </div>`).join('')}
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>What's next</h2><ol class="steps">
      ${[...auto, ...P.next_steps.map(esc), ...P.planned_experiments.map(p => `Run the <strong>${esc(p.title)}</strong>: ${esc(p.question)}`)].map(s => `<li>${s}</li>`).join('')}
    </ol></div>
    <div class="card"><div class="spread"><h2>Latest logbook entries</h2><a href="#/docs/logbook">Open logbook</a></div>
      <ul class="log-list">${D.logbook.filter(e => e.date).slice(-6).reverse().map(e =>
        `<li><span class="date">${esc(e.date)}</span><a href="#/docs/logbook/${slug(e.date + ' ' + e.title)}">${esc(e.title)}</a></li>`).join('')}</ul>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ experiments */

function viewExperiments(v) {
  const planned = D.project.planned_experiments;
  v.innerHTML = `<h1>Experiments</h1><p class="muted">Each experiment's design and pass/fail thresholds are fixed in the logbook before it runs.</p>
  <div class="stack">${D.experiments.slice().sort((a, b) => b.main - a.main).map(e => { const p = expProgress(e);
    return `<div class="card"><div class="spread"><div class="row"><h2 style="margin:0">${esc(e.title)}</h2>${stateChip(e.state)}${e.main ? '' : '<span class="chip">check only</span>'}</div>
      <a class="btn" href="#/experiments/${e.id}">Open results</a></div>
      <p style="margin:8px 0 4px">${esc(e.question)}</p><p class="muted" style="margin:0 0 10px">${esc(e.design)}</p>
      <div class="row" style="margin-bottom:6px"><span class="muted">${p.done} of ${p.total} runs</span></div>${bar(p.done, p.total)}
      ${e.main ? `<div class="row" style="margin-top:10px">${expVerdicts(e)}</div>` : ''}</div>`; }).join('')}
    ${planned.map(p => `<div class="card" style="border-style:dashed"><div class="row"><h2 style="margin:0">${esc(p.title)}</h2><span class="chip">planned</span></div>
      <p class="muted" style="margin:8px 0 0">${esc(p.question)}</p></div>`).join('')}
  </div>`;
}

function viewExperiment(v, id) {
  const e = expById(id);
  if (!e) { v.innerHTML = '<div class="empty">Experiment not found.</div>'; return; }
  const s = e.summary, T = D.thresholds, p = expProgress(e);
  let html = `<p><a href="#/experiments">← Experiments</a></p><div class="spread"><h1>${esc(e.title)}</h1>${stateChip(e.state)}</div>
    <p style="margin:4px 0">${esc(e.question)}</p><p class="muted" style="margin:0 0 14px">${esc(e.design)}</p>`;
  if (!s) {
    v.innerHTML = html + `<div class="card empty">No runs yet.${LOCAL ? ' Start it from <a href="#/control">Run &amp; publish</a>.' : ''}</div>`;
    return;
  }
  const V = s.verdict;
  html += `<div class="tiles">
    ${tile(`Gap at ${T.gap_budget_s} s, limited`, V.gap ? `<span class="${V.gap === 'pass' ? 'good-t' : 'bad-t'}">${V.gap}${V.complete ? '' : ' so far'}</span>` : 'pending',
      `pass if within ${T.gap_threshold_pct}% of the best known plan`)}
    ${tile('Memory, limited', V.memory ? `<span class="${V.memory === 'pass' ? 'good-t' : 'bad-t'}">${V.memory}${V.complete ? '' : ' so far'}</span>` : 'pending',
      `peak ${fmt(V.limited_peak_mb)} MB, limit ${T.memory_threshold_mb} MB, ${V.limited_killed} killed`)}
    ${tile('Progress', `${p.done} / ${p.total}`, V.complete ? 'complete: verdicts are final' : 'partial: verdicts may change')}
  </div>`;
  for (const [c, d] of Object.entries(s.contractors)) {
    if (!d.cells.length) { html += `<div class="card"><h2>${esc(c)}</h2>${esc(d.note || '')}</div>`; continue; }
    html += `<div class="card" style="margin-bottom:14px"><h2>${esc(c)}</h2>
      <div class="legend"><span><i style="background:var(--lim)"></i>limited (512 MB, 0.1 CPU)</span><span><i style="background:var(--unl)"></i>unlimited</span>
      <span><i style="background:var(--bad)"></i>${T.gap_threshold_pct}% threshold</span></div>
      <svg class="chart" id="gap-${esc(c)}" viewBox="0 0 900 280"></svg>
      <p class="muted" style="font-size:12px">Gap = median total student ride time over repeats, compared with the best plan any run found
      (${fmt(d.best_known_ride_min)} student-min, from ${esc(d.best_from)}). The current hand-made routes are ${d.current_routes_gap_pct}% above it
      (${fmt(d.current_routes_ride_min)} student-min).</p>
      <div class="tbl-wrap"><table><tr><th>Setup</th><th>Budget</th><th>Runs ok</th><th>Student-min</th><th>Gap</th><th>First plan</th><th>Wall</th><th>Solver CPU</th><th>Peak MB</th></tr>
      ${d.cells.map(x => `<tr><td>${esc(x.setup)}</td><td>${x.budget_s} s</td><td>${x.ok}/${x.runs}${x.not_ok.length ? ` <span class="bad-t">(${esc(x.not_ok.join(', '))})</span>` : ''}</td>
        <td>${fmt(x.ride_min)}</td><td>${x.gap_pct == null ? '–' : x.gap_pct + '%'}</td><td>${x.first_plan_s ?? '–'} s</td><td>${x.wall_s ?? '–'} s</td><td>${x.cpu_s ?? '–'} s</td><td>${x.peak_mb ?? '–'}</td></tr>`).join('')}
      </table></div></div>`;
  }
  html += `<div class="card" style="margin-bottom:14px"><h2>Every run</h2><div class="tbl-wrap"><table>
    <tr><th>Run</th><th>Status</th><th>Started</th><th>Student-min</th><th>Peak MB</th><th>Wall</th></tr>
    ${s.rows.map(r => `<tr class="${r.status === 'ok' ? 'click' : ''}" data-run="${esc(r.key)}"><td>${esc(r.key)}</td>
      <td><span class="chip ${r.status === 'ok' ? 'good' : 'bad'}">${esc(r.status)}</span></td><td>${esc(when(r.started_at))}</td>
      <td>${fmt(r.total_student_ride_min)}</td><td>${r.peak_mb ?? '–'}</td><td>${r.wall_s} s</td></tr>`).join('')}
    </table></div><p class="muted" style="font-size:12px">Click a run to see its routes on a map.</p></div>`;
  const m = s.meta || {}, mc = m.machine || {};
  html += `<div class="card"><h2>Machine</h2><div class="tbl-wrap"><table>
    ${[['Host', mc.host], ['CPU', mc.cpu], ['Cores', mc.cpus], ['RAM', mc.ram_gb ? mc.ram_gb + ' GB' : null], ['Kernel', mc.kernel], ['Python', mc.python],
      ['OR-Tools', mc.ortools], ['Limits the kernel applied', m.limits ? Object.entries(m.limits.found || {}).map(([k, x]) => `${k}=${x}`).join(', ') : null],
      ['Started', when(m.started_at)]].map(([k, x]) => `<tr><td>${esc(k)}</td><td class="l">${esc(x ?? '–')}</td></tr>`).join('')}
    </table></div></div>`;
  v.innerHTML = html;
  v.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}`; });
  for (const [c, d] of Object.entries(s.contractors)) if (d.cells.length) gapChart(document.getElementById(`gap-${c}`), d.cells, T.gap_threshold_pct);
}

function gapChart(svg, cells, threshold) {
  const W = 900, H = 280, l = 56, r = 90, t = 30, b = 36;
  const bud = [...new Set(cells.map(x => x.budget_s))].sort((a, z) => a - z);
  const gaps = cells.map(x => x.gap_pct).filter(x => x != null);
  const y1 = Math.max(threshold * 1.4, Math.max(...gaps, 0) * 1.1, 1);
  const X = s => l + (W - l - r) * (bud.length < 2 ? 0.5 : Math.log(s / bud[0]) / Math.log(bud[bud.length - 1] / bud[0]));
  const Y = g => t + (H - t - b) * (1 - g / y1);
  let g = '';
  for (let i = 0; i <= 4; i++) { const val = y1 * i / 4; g += `<line x1="${l}" x2="${W - r}" y1="${Y(val)}" y2="${Y(val)}" stroke="var(--line)"/><text x="${l - 8}" y="${Y(val) + 4}" text-anchor="end">${val.toFixed(1)}%</text>`; }
  bud.forEach(s => { g += `<text x="${X(s)}" y="${H - b + 18}" text-anchor="middle">${s} s</text>`; });
  g += `<line x1="${l}" x2="${W - r}" y1="${Y(threshold)}" y2="${Y(threshold)}" stroke="var(--bad)" stroke-dasharray="5 5"/>`;
  for (const [setup, col] of [['limited', 'var(--lim)'], ['unlimited', 'var(--unl)']]) {
    const pts = cells.filter(x => x.setup === setup && x.gap_pct != null).map(x => [X(x.budget_s), Y(x.gap_pct), x]);
    if (!pts.length) continue;
    g += `<polyline points="${pts.map(p => p[0] + ',' + p[1]).join(' ')}" fill="none" stroke="${col}" stroke-width="2.5"/>`;
    g += pts.map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="4.5" fill="${col}"><title>${setup}, ${p[2].budget_s} s: ${p[2].gap_pct}% gap</title></circle>`).join('');
    const last = pts[pts.length - 1];
    g += `<text x="${last[0] + 10}" y="${last[1] + 4}" style="fill:${col}">${setup}</text>`;
  }
  svg.innerHTML = g + `<text x="${l}" y="10">Gap to best known plan (lower is better)</text><text x="${W - r}" y="${H - 2}" text-anchor="end">search budget (log scale)</text>`;
}

/* ------------------------------------------------------------------ runs */

function viewRuns(v) {
  const sources = ['all', ...new Set(D.runs.map(r => r.source))];
  const label = s => s === 'all' ? 'All' : s === 'development' ? 'Development runs' : (expById(s) || {}).title || s;
  const rows = D.runs.filter(r => runFilter === 'all' || r.source === runFilter)
    .flatMap(r => Object.entries(r.contractors).map(([c, x]) => ({ r, c, x })));
  v.innerHTML = `<h1>Runs</h1><p class="muted">Every optimizer run with a result. Click one to compare its routes with the current routes on a map.</p>
    <div class="seg" id="filt" style="margin:8px 0 14px">${sources.map(s => `<button data-s="${esc(s)}" class="${s === runFilter ? 'on' : ''}">${esc(label(s))}</button>`).join('')}</div>
    <div class="card">${rows.length ? `<div class="tbl-wrap"><table>
      <tr><th>Run</th><th>Contractor</th><th>Setup</th><th>Budget</th><th>Student-min</th><th>vs current</th><th>Buses</th><th>Peak MB</th><th>Started</th></tr>
      ${rows.map(({ r, c, x }) => `<tr class="click" data-run="${esc(r.id)}" data-c="${esc(c)}"><td>${esc(r.id)}</td><td>${esc(c)}</td><td>${esc(r.setup)}</td>
        <td>${r.time_limit_s} s</td><td>${fmt(x.ride_min)}</td><td class="${x.vs_current_pct < 0 ? 'good-t' : ''}">${sign(x.vs_current_pct)}</td>
        <td>${x.buses ?? '–'}</td><td>${r.peak_mb ?? x.peak_mb ?? '–'}</td><td>${esc(when(r.started_at))}</td></tr>`).join('')}
      </table></div>` : '<div class="empty">No runs yet.</div>'}</div>`;
  v.querySelectorAll('#filt button').forEach(b => b.onclick = () => { runFilter = b.dataset.s; route(); });
  v.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}/${encodeURIComponent(tr.dataset.c)}`; });
}

const colour = i => `hsl(${(i * 137.5) % 360},65%,48%)`;

function baseMap(el) {
  const m = L.map(el, { zoomControl: true, preferCanvas: true });
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors', maxZoom: 16 }).addTo(m);
  maps.push(m);
  return m;
}

function campusMarker(layer) {
  const c = D.dataset.campus;
  L.circleMarker([c.lat, c.lng], { radius: 8, color: '#111827', fillColor: '#facc15', fillOpacity: 1, weight: 2 }).bindTooltip(c.name).addTo(layer);
}

function drawRoutes(layer, routes, contractor) {
  layer.clearLayers();
  const c = D.dataset.campus;
  routes.forEach((r, i) => {
    const pts = r.map(n => D.stopsByName[n]).filter(Boolean).map(s => [s[1], s[2]]);
    if (!pts.length) return;
    L.polyline(pts, { color: colour(i), weight: 3, opacity: 0.9 }).addTo(layer);
    L.polyline([pts[pts.length - 1], [c.lat, c.lng]], { color: colour(i), weight: 1.5, opacity: 0.35, dashArray: '4 6' }).addTo(layer);
    r.forEach(n => { const s = D.stopsByName[n]; if (s) L.circleMarker([s[1], s[2]], { radius: 4, color: '#fff', weight: 1, fillColor: colour(i), fillOpacity: 1 })
      .bindTooltip(`${n}: ${(s[3] || {})[contractor] || 0} students`).addTo(layer); });
  });
  campusMarker(layer);
}

async function viewRun(v, arg) {
  const [id, wantC] = arg.split('/');
  const meta = D.runs.find(r => r.id === id);
  if (!meta) { v.innerHTML = '<div class="empty">Run not found.</div>'; return; }
  v.innerHTML = '<p class="muted">Loading run…</p>';
  const R = await (await fetch(meta.file, { cache: 'no-store' })).json();
  const names = Object.keys(R.contractors);
  let cur = names.includes(wantC) ? wantC : names[0];
  v.innerHTML = `<p><a href="#/runs">← Runs</a></p><div class="spread"><h1>${esc(id)}</h1>
    <div class="seg" id="ctabs">${names.map(n => `<button data-c="${esc(n)}">${esc(n)}</button>`).join('')}</div></div>
    <p class="muted" style="margin:0 0 4px">${esc(meta.setup)} · search limit ${R.time_limit_s} s · instance ${esc(R.instance)} · ${esc(when(meta.started_at))}</p>
    <div class="tiles" id="rcards"></div>
    <div class="card" style="margin-bottom:14px"><h2>Routes</h2><div class="maps">
      <div><h3>Current routes</h3><div id="m1" class="map"></div></div><div><h3>Optimized routes</h3><div id="m2" class="map"></div></div></div>
      <p class="muted" style="font-size:12px">One colour per bus. Lines join stops in visiting order (straight lines, not roads); the dashed line is the drive to campus. The two maps move together.</p></div>
    <div class="grid g2"><div class="card"><h2>Comparison</h2><div class="tbl-wrap" id="rtable"></div></div>
      <div class="card"><h2>How the search improved the plan</h2><svg class="chart" id="prog" viewBox="0 0 900 300"></svg>
      <p class="muted" style="font-size:12px">Each step is a better plan found. Where the line goes flat, extra search time stops paying off.</p></div></div>`;
  const ms = [baseMap('m1'), baseMap('m2')];
  const layers = ms.map(m => L.layerGroup().addTo(m));
  let sync = false;
  ms.forEach((m, i) => m.on('move', () => { if (sync) return; sync = true; ms[1 - i].setView(m.getCenter(), m.getZoom(), { animate: false }); sync = false; }));
  const show = () => {
    v.querySelectorAll('#ctabs button').forEach(b => b.classList.toggle('on', b.dataset.c === cur));
    const c = R.contractors[cur], b = c.baseline, o = c.optimized || {};
    const card = (k, a, z) => tile(k, fmt(z), `${fmt(a)} now${z != null && a ? ` · <span class="${z < a ? 'good-t' : z > a ? 'bad-t' : ''}">${sign(Math.round((z - a) / a * 1000) / 10)}</span>` : ''}`);
    $('#rcards').innerHTML = card('Total student ride (min)', b.total_student_ride_min, o.total_student_ride_min) + card('Mean ride (min)', b.mean_ride_min, o.mean_ride_min) +
      card('Longest ride (min)', b.longest_ride_min, o.longest_ride_min) + card('Buses used', b.buses_used, o.buses_used) +
      tile('Compute', `${c.solve_wall_s} s`, `${c.solve_cpu_s} s CPU · peak ${c.peak_rss_mb} MB`);
    const rows = [['Buses used', 'buses_used'], ['Total student ride (min)', 'total_student_ride_min'], ['Mean ride (min)', 'mean_ride_min'],
      ['Longest ride (min)', 'longest_ride_min'], ['Stops over 90 min', 'stops_over_90_min'], ['Bus driving (min)', 'bus_driving_min']];
    $('#rtable').innerHTML = `<table><tr><th>Measure</th><th>Current</th><th>Optimized</th></tr>${rows.map(([l, k]) =>
      `<tr><td>${l}</td><td>${fmt(b[k])}</td><td>${fmt(o[k])}</td></tr>`).join('')}</table>
      <p class="muted" style="font-size:12px">Stops dropped: ${(o.dropped_stops || []).length}. Both plans scored the same way on the same travel-time matrix.</p>`;
    drawRoutes(layers[0], c.baseline_routes, cur);
    drawRoutes(layers[1], c.routes || [], cur);
    const pts = c.baseline_routes.flat().map(n => D.stopsByName[n]).filter(Boolean).map(s => [s[1], s[2]]);
    pts.push([D.dataset.campus.lat, D.dataset.campus.lng]);
    ms[0].fitBounds(L.latLngBounds(pts), { padding: [20, 20] });
    progressChart($('#prog'), c.progress || []);
  };
  v.querySelectorAll('#ctabs button').forEach(b => b.onclick = () => { cur = b.dataset.c; show(); });
  show();
}

function progressChart(svg, p) {
  svg.innerHTML = '';
  if (!p.length) return;
  const W = 900, H = 300, l = 70, r = 20, t = 20, bm = 40, t1 = Math.max(...p.map(x => x[0]), 1), vals = p.map(x => x[1] / 60);
  const y0 = Math.min(...vals), y1 = Math.max(...vals);
  const X = s => l + (W - l - r) * s / t1, Y = y => t + (H - t - bm) * (y1 === y0 ? 0.5 : (y1 - y) / (y1 - y0));
  let g = '';
  for (let i = 0; i <= 4; i++) { const y = y0 + (y1 - y0) * i / 4; g += `<line x1="${l}" x2="${W - r}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--line)"/><text x="${l - 8}" y="${Y(y) + 4}" text-anchor="end">${Math.round(y).toLocaleString()}</text>`; }
  for (let i = 0; i <= 4; i++) { const s = t1 * i / 4; g += `<text x="${X(s)}" y="${H - bm + 18}" text-anchor="middle">${s.toFixed(s < 10 ? 1 : 0)} s</text>`; }
  let d = '';
  p.forEach(([s], i) => { d += i ? ` H${X(s)} V${Y(vals[i])}` : `M${X(s)} ${Y(vals[i])}`; });
  d += ` H${X(t1)}`;
  svg.innerHTML = g + `<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2.5"/><text x="${l}" y="12">Cost of best plan (approx. student-minutes)</text>
    <text x="${W - r}" y="${H - 4}" text-anchor="end">search time · ${p.length} improvements</text>`;
}

/* ------------------------------------------------------------------ data */

function viewData(v) {
  const ds = D.dataset, names = Object.keys(ds.contractors);
  const cols = { [names[0]]: 'var(--c1)', [names[1]]: 'var(--c2)' };
  const hex = n => getComputedStyle(document.documentElement).getPropertyValue(n.slice(4, -1)).trim() || '#2457d6';
  v.innerHTML = `<h1>Data</h1><p class="muted">Dataset <code>${esc(ds.version)}</code>, frozen. Every experiment uses this same dataset. Students are ${ds.synthetic ? 'synthetic' : 'real'}; buses arrive at campus by ${esc(ds.arrival)}.</p>
    <div class="tiles">${names.map(n => { const c = ds.contractors[n];
      return tile(n, `${c.stops} stops`, `${c.routes} routes · ${c.buses} buses · ${fmt(c.seats)} seats · ${fmt(c.students)} students`); }).join('')}
      ${tile('Shared stops', ds.stops.filter(s => Object.keys(s[3]).length > 1).length, 'served by both contractors')}
      ${tile('Placed by hand', ds.stops.filter(s => s[4] === 'interpolated').length, 'stops with no location, placed between route neighbours')}</div>
    <div class="card" style="margin-bottom:14px"><div class="spread"><h2>Stops</h2>
      <div class="row"><span class="muted">Show current routes:</span><div class="seg" id="rt"><button data-c="" class="on">None</button>${names.map(n => `<button data-c="${esc(n)}">${esc(n)}</button>`).join('')}</div></div></div>
      <div class="legend" style="margin-bottom:8px">${names.map(n => `<span><i style="background:${cols[n]}"></i>${esc(n)}</span>`).join('')}<span><i style="background:var(--c3)"></i>both</span><span>Circle size = students at the stop</span></div>
      <div id="dmap" class="map tall"></div></div>
    <div class="card"><div class="spread"><h2>Current routes</h2><div class="seg" id="rtab">${names.map((n, i) => `<button data-c="${esc(n)}" class="${i ? '' : 'on'}">${esc(n)}</button>`).join('')}</div></div>
      <div class="tbl-wrap" id="rtbl"></div></div>`;
  const m = baseMap('dmap');
  const stopLayer = L.layerGroup().addTo(m), routeLayer = L.layerGroup().addTo(m);
  ds.stops.forEach(s => {
    const who = Object.keys(s[3]), n = Object.values(s[3]).reduce((a, x) => a + x, 0);
    const col = who.length > 1 ? hex('var(--c3)') : hex(cols[who[0]] || 'var(--c1)');
    L.circleMarker([s[1], s[2]], { radius: 3 + Math.sqrt(n) * 1.4, color: '#fff', weight: 1, fillColor: col, fillOpacity: 0.85 })
      .bindTooltip(`${esc(s[0])}<br>${who.map(w => `${w}: ${s[3][w]} students`).join('<br>')}${s[4] === 'interpolated' ? '<br><i>location placed by hand</i>' : ''}`).addTo(stopLayer);
  });
  campusMarker(stopLayer);
  m.fitBounds(L.latLngBounds(ds.stops.map(s => [s[1], s[2]]).concat([[ds.campus.lat, ds.campus.lng]])), { padding: [20, 20] });
  v.querySelectorAll('#rt button').forEach(b => b.onclick = () => {
    v.querySelectorAll('#rt button').forEach(x => x.classList.toggle('on', x === b));
    if (!b.dataset.c) routeLayer.clearLayers(); else drawRoutes(routeLayer, ds.contractors[b.dataset.c].current_routes.map(r => r.stops), b.dataset.c);
  });
  const table = c => {
    $('#rtbl').innerHTML = `<table><tr><th>Route</th><th>Bus</th><th>Seats</th><th>Students</th><th>Load</th><th>Stops</th><th class="l">First and last stop</th></tr>
      ${ds.contractors[c].current_routes.map(r => `<tr><td>${esc(r.code)}</td><td>${esc(r.bus)}</td><td>${r.capacity}</td><td>${r.students}</td>
        <td>${Math.round(r.students / r.capacity * 100)}%</td><td>${r.stops.length}</td><td class="l">${esc(r.stops[0])} → ${esc(r.stops[r.stops.length - 1])}</td></tr>`).join('')}</table>`;
    v.querySelectorAll('#rtab button').forEach(x => x.classList.toggle('on', x.dataset.c === c));
  };
  v.querySelectorAll('#rtab button').forEach(b => b.onclick = () => table(b.dataset.c));
  table(names[0]);
}

/* ------------------------------------------------------------------ documents */

function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }

async function viewDocs(v, arg) {
  const [id, anchor] = (arg || 'logbook').split('/');
  const doc = D.docs.find(d => d.id === id) || D.docs[0];
  const groups = [...new Set(D.docs.map(d => d.group))];
  v.innerHTML = `<div class="docs"><aside class="card doclist">${groups.map(g => `<div class="g">${esc(g)}</div>` +
      D.docs.filter(d => d.group === g).map(d => `<a href="#/docs/${d.id}" class="${d.id === doc.id ? 'on' : ''}">${esc(d.title)}</a>`).join('')).join('')}
      ${D.files.length ? `<div class="g">Files</div>${D.files.map(f => `<a href="${esc(f.file)}" target="_blank" rel="noopener">${esc(f.title)} (PDF)</a>`).join('')}` : ''}</aside>
    <article class="card md" id="doc"><p class="muted">Loading…</p></article></div>`;
  const text = await (await fetch(doc.file, { cache: 'no-store' })).text();
  const el = $('#doc');
  el.innerHTML = window.marked ? marked.parse(text) : `<pre>${esc(text)}</pre>`;
  el.querySelectorAll('h1,h2,h3').forEach(h => { h.id = slug(h.textContent.replace(/:/g, ' ')); });
  el.querySelectorAll('a[href^="http"]').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });
  if (anchor) { const t = document.getElementById(anchor); if (t) t.scrollIntoView(); }
}

/* ------------------------------------------------------------------ local control (hub only) */

const icon = ok => ok == null ? '<span class="q-i">?</span>' : ok ? '<span class="ok-i">✓</span>' : '<span class="no-i">✕</span>';

function viewControl(v) {
  if (!LOCAL) { v.innerHTML = '<div class="empty">Run controls exist only in the local hub on the research laptop.</div>'; return; }
  v.innerHTML = `<h1>Run &amp; publish</h1><p class="muted">Everything runs in WSL on this laptop. Results show up in the other tabs as runs finish.</p>
    <div class="grid g2">
      <div class="card"><div class="spread"><h2>Setup</h2><button class="btn" id="chk">Check setup</button></div><div id="env"></div></div>
      <div class="card"><h2>Publish to the shared page</h2><div id="pub"></div></div>
    </div>
    <div class="card" style="margin-top:14px"><h2>Experiments</h2><div id="jobs"></div></div>`;
  $('#chk').onclick = async e => { e.target.disabled = true; e.target.textContent = 'Checking…'; try { STATUS.env = (await api('check', {})).env; } catch (x) { alert(x.message); } renderControl(); };
  renderControl();
}

function renderControl() {
  if (PAGE !== 'control' || !STATUS) return;
  const env = STATUS.env, job = STATUS.job, git = STATUS.git || {};
  const chk = $('#chk'); if (chk) { chk.disabled = false; chk.textContent = 'Check setup'; }
  const items = [['WSL starts', env && env.wsl], ['Python environment (~/fc-research-venv)', env && env.venv],
    ['OR-Tools installed', env && env.ortools ? true : env ? false : null], ['Free-tier limits apply (512 MB, 0.1 CPU)', env && env.limits]];
  $('#env').innerHTML = `<ul class="checks">${items.map(([t, ok]) => `<li>${icon(ok)}<span>${esc(t)}</span>${t.startsWith('OR') && env && env.ortools ? `<span class="muted">${esc(env.ortools)}</span>` : ''}</li>`).join('')}</ul>
    ${!env ? '<p class="msg muted">Not checked yet. Checking takes a few seconds.</p>' : ''}
    ${env && env.wsl && !env.ortools ? `<p class="msg">The research Python environment is missing. <button class="btn primary" id="inst">Install it</button></p>` : ''}
    ${env && env.message ? `<p class="msg bad-t">${esc(env.message)}</p>` : ''}
    ${env ? `<p class="msg muted">Checked ${esc(when(env.checked_at))}.</p>` : ''}`;
  const inst = $('#inst'); if (inst) inst.onclick = () => startJob('install');

  const running = job && job.state === 'running';
  $('#jobs').innerHTML = D.experiments.slice().sort((a, b) => b.main - a.main).map(e => {
    const p = expProgress(e), mine = running && job.experiment === e.id, left = p.total - p.done;
    const action = mine ? `<button class="btn danger" data-stop>Stop</button>`
      : `<button class="btn ${e.main ? 'primary' : ''}" data-start="${e.id}" ${running ? 'disabled' : ''}>${p.done === 0 ? 'Start' : left > 0 ? 'Resume' : 'Run again'}</button>`;
    return `<div class="item"><div class="spread"><div class="row"><strong>${esc(e.title)}</strong>${stateChip(mine ? 'running' : e.state)}<span class="muted">${p.done}/${p.total} runs</span></div>${action}</div>
      <p>${esc(e.design)}</p>${bar(p.done, p.total)}
      ${mine && job.log_tail ? `<pre class="log">${esc(job.log_tail.join('\n'))}</pre>` : ''}</div>`;
  }).join('') + (job && job.state === 'running' && job.experiment === 'install' ? `<pre class="log">${esc((job.log_tail || []).join('\n'))}</pre>` : '') +
    (job && job.state !== 'running' && job.finished_at ? `<p class="msg muted">Last job: ${esc(job.title)} ${job.exit_code === 0 ? 'finished' : `stopped (exit ${job.exit_code})`} at ${esc(when(job.finished_at))}.</p>` : '') +
    `<p class="msg muted">While a job runs, the hub keeps this PC from sleeping. Keep this hub window open; if it closes, press Resume later and it continues from the last finished run.</p>`;
  $('#jobs').querySelectorAll('[data-start]').forEach(b => b.onclick = () => startJob(b.dataset.start));
  $('#jobs').querySelectorAll('[data-stop]').forEach(b => b.onclick = stopJob);

  $('#pub').innerHTML = `<p style="margin-top:0">${git.changes ? `<strong>${plural(git.changes, 'research change')}</strong> not published yet.` : 'Everything in research/ is saved to git.'}
    ${git.ahead ? ` ${plural(git.ahead, 'commit')} waiting to be pushed.` : ''}</p>
    <p class="muted">Publishing saves research/ to git (only that folder) and pushes it. The shared page updates a minute or two later${git.pages_url ? `: <a href="${esc(git.pages_url)}" target="_blank" rel="noopener">${esc(git.pages_url)}</a>` : ''}.</p>
    ${git.branch && git.branch !== 'main' ? `<p class="msg bad-t">You are on branch ${esc(git.branch)}. The shared page only updates from main.</p>` : ''}
    <button class="btn primary" id="pubbtn" ${running || (!git.changes && !git.ahead) ? 'disabled' : ''}>Publish results</button><div id="pubmsg" class="msg"></div>`;
  const pb = $('#pubbtn');
  if (pb) pb.onclick = async () => {
    pb.disabled = true; pb.textContent = 'Publishing…';
    try { const r = await api('publish', {}); $('#pubmsg').innerHTML = `<span class="${r.ok ? 'good-t' : 'bad-t'}">${esc(r.message)}</span>`; }
    catch (x) { $('#pubmsg').innerHTML = `<span class="bad-t">${esc(x.message)}</span>`; }
    pb.textContent = 'Publish results'; await poll();
  };
}

async function startJob(id) {
  try { STATUS = await api('start', { experiment: id }); } catch (x) { alert(x.message); }
  renderStrip(); renderControl();
}
async function stopJob() {
  if (!confirm('Stop the running job? Finished runs are kept, and Resume continues from there.')) return;
  try { STATUS = await api('stop', {}); } catch (x) { alert(x.message); }
  renderStrip(); renderControl();
}

function renderStrip() {
  const el = $('#strip'), job = STATUS && STATUS.job;
  if ((!job || job.state !== 'running') && STATUS && STATUS.wsl_busy) {
    el.hidden = false;
    el.innerHTML = `<strong>An experiment is running in WSL</strong><span class="muted">started outside this hub; results still show up here as runs finish.</span>
      <button class="btn danger" id="xstop">Stop it</button>`;
    $('#xstop').onclick = stopJob;
    return;
  }
  if (!job || job.state !== 'running') { el.hidden = true; return; }
  const e = expById(job.experiment), p = e ? expProgress(e) : null;
  el.hidden = false;
  el.innerHTML = `<strong>Running:</strong> ${esc(job.title)}${p ? ` · ${p.done}/${p.total} runs` : ''}
    ${p ? `<div class="bar"><i style="width:${p.total ? p.done / p.total * 100 : 0}%"></i></div>` : ''}
    <span class="muted">started ${esc(when(job.started_at))}</span><a href="#/control">Details</a>`;
}

async function poll() {
  try { STATUS = await api('status'); } catch { return; }
  if (STATUS.site_version !== lastVersion) {
    lastVersion = STATUS.site_version;
    await loadIndex();
    rerenderIfSafe();
  }
  renderStrip(); renderControl();
}

/* ------------------------------------------------------------------ start */

(async function init() {
  try { await loadIndex(); } catch (x) { $('#view').innerHTML = `<div class="empty">Could not load data/index.json (${esc(x.message)}).</div>`; return; }
  try { STATUS = await api('status'); LOCAL = !!STATUS.local; lastVersion = STATUS.site_version; } catch { LOCAL = false; }
  window.addEventListener('hashchange', route);
  route();
  if (LOCAL) { renderStrip(); setInterval(poll, 3000); }
})();
