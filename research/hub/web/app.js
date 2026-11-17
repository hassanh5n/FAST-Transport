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
  return s ? { done: s.runs_done, total: s.runs_total, left: s.remaining_s } : { done: 0, total: e.runs_total || 0, left: null };
}

const dur = s => s == null ? '' : s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min`
  : `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
const leftText = p => (p.left && p.done < p.total ? ` · about ${dur(p.left)} left` : '');
// "3/12 runs"; a pass whose total is set by its script when it starts has no total before then.
const runsText = p => (p.total ? `${p.done}/${p.total} runs` : `${p.done} runs, total set when it starts`);

/* ------------------------------------------------------------------ export (charts and tables, for the report) */

const EXPORT_COLOURS = { '--line': '#e4e7ec', '--muted': '#667085', '--bad': '#b42318', '--lim': '#2457d6', '--unl': '#8b3fd9',
  '--accent': '#2457d6', '--ink': '#1c2330', '--good': '#067647', '--c1': '#2457d6', '--c2': '#d9480f', '--c3': '#8b3fd9' };

function svgForExport(svg) {
  const vb = svg.viewBox.baseVal, w = vb.width || 900, h = vb.height || 300;
  const clone = svg.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', w); clone.setAttribute('height', h);
  let s = new XMLSerializer().serializeToString(clone).replace(/var\((--[a-z0-9-]+)\)/g, (m, n) => EXPORT_COLOURS[n] || '#333');
  s = s.replace(/(<svg[^>]*>)/, `$1<style>text{font:12px Arial,Helvetica,sans-serif;fill:${EXPORT_COLOURS['--muted']}}</style><rect width="100%" height="100%" fill="#ffffff"/>`);
  return { s, w, h };
}

function download(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function exportChart(svg, name, fmt) {
  const { s, w, h } = svgForExport(svg);
  if (fmt === 'svg') return download(`${name}.svg`, new Blob([s], { type: 'image/svg+xml' }));
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas'); c.width = w * 2; c.height = h * 2;
    const ctx = c.getContext('2d'); ctx.scale(2, 2); ctx.drawImage(img, 0, 0, w, h);
    c.toBlob(b => download(`${name}.png`, b), 'image/png');
  };
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
}

const tableRows = t => [...t.rows].map(r => [...r.cells].map(c => c.textContent.replace(/\s+/g, ' ').trim()));
const csvCell = x => /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x;
const texCell = x => x.replace(/\\/g, '\\textbackslash{}').replace(/([&%$#_{}])/g, '\\$1').replace(/~/g, '\\textasciitilde{}')
  .replace(/\^/g, '\\textasciicircum{}').replace(/→/g, '$\\rightarrow$').replace(/–/g, '--');

function toLatex(rows) {
  const n = Math.max(...rows.map(r => r.length));
  const line = r => r.map(texCell).join(' & ') + ' \\\\';
  return [`\\begin{tabular}{l${'r'.repeat(n - 1)}}`, '\\toprule', line(rows[0]), '\\midrule', ...rows.slice(1).map(line),
    '\\bottomrule', '\\end{tabular}'].join('\n');
}

async function exportTable(t, name, fmt) {
  const rows = tableRows(t);
  if (fmt === 'csv') return download(`${name}.csv`, new Blob([rows.map(r => r.map(csvCell).join(',')).join('\n')], { type: 'text/csv' }));
  const tex = toLatex(rows);
  try { await navigator.clipboard.writeText(tex); toast('LaTeX table copied. Needs \\usepackage{booktabs}.'); }
  catch { download(`${name}.tex`, new Blob([tex], { type: 'text/plain' })); }
}

function toast(msg) {
  const el = document.createElement('div');
  el.className = 'toast'; el.textContent = msg;
  document.body.append(el);
  setTimeout(() => el.remove(), 3200);
}

// Buttons: chartTools('svg-id', 'file-name') and tableTools('table-id', 'file-name'); bindExports(root) wires them.
const chartTools = (id, name) => `<span class="tools"><button class="mini" data-chart="${esc(id)}" data-name="${esc(name)}" data-fmt="png" title="Download as PNG">PNG</button><button class="mini" data-chart="${esc(id)}" data-name="${esc(name)}" data-fmt="svg" title="Download as SVG">SVG</button></span>`;
const tableTools = (id, name) => `<span class="tools"><button class="mini" data-table="${esc(id)}" data-name="${esc(name)}" data-fmt="csv" title="Download as CSV">CSV</button><button class="mini" data-table="${esc(id)}" data-name="${esc(name)}" data-fmt="tex" title="Copy as a LaTeX table">LaTeX</button></span>`;

function bindExports(root) {
  root.querySelectorAll('[data-chart]').forEach(b => b.onclick = () => exportChart(document.getElementById(b.dataset.chart), b.dataset.name, b.dataset.fmt));
  root.querySelectorAll('[data-table]').forEach(b => b.onclick = () => exportTable(document.getElementById(b.dataset.table), b.dataset.name, b.dataset.fmt));
}

function expVerdicts(e) {
  const s = e.summary || {}, v = s.verdict || {};
  if (e.kind === 'query-budget') {
    const t = s.thresholds || {};
    return verdictChip(v.gap, `Gap at ${t.primary || 'K=10'}`, v.complete) + ' ' +
      verdictChip(v.feasibility, `Nobody over 90 min (K ≥ ${t.feasible_from_k ?? 10})`, v.complete);
  }
  if (e.kind === 'reroute') {
    // A pass with no runs shows the rules it will judge; the scaling pass has no pass or fail.
    const chips = s.chips || (e.pending || {}).chips || [];
    const note = (s.thresholds || (e.pending || {}).thresholds || {}).note;
    return chips.map(c => verdictChip(c.result, c.label, v.complete)).join(' ') + (note ? `<span class="chip">${esc(note)}</span>` : '');
  }
  if (s.chips) return s.chips.map(c => verdictChip(c.result, c.label, v.complete)).join(' ');
  if (e.kind !== 'budget') return '';
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
                <strong>${esc(e.title)}</strong>${stateChip(e.state)}<span class="muted">${runsText(p)}</span></div>
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
      <div class="row" style="margin-bottom:6px"><span class="muted">${p.total ? `${p.done} of ${p.total} runs` : runsText(p)}</span></div>${bar(p.done, p.total)}
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
    v.innerHTML = html + `<div class="card empty">No runs yet.${LOCAL ? ' Start it from <a href="#/control">Run &amp; publish</a>.' : ''}</div>` +
      (e.pending ? pendingRules(e.pending) : '');
    return;
  }
  if (e.kind !== 'budget') {
    v.innerHTML = html + experimentBody(e, s, p); bindRunRows(v); bindExports(v);
    if (e.kind === 'reroute' && s.pass === 'quality') bindPlanMap(v, e, s);
    return;
  }
  const V = s.verdict;
  html += `<div class="tiles">
    ${tile(`Gap at ${T.gap_budget_s} s, limited`, V.gap ? `<span class="${V.gap === 'pass' ? 'good-t' : 'bad-t'}">${V.gap}${V.complete ? '' : ' so far'}</span>` : 'pending',
      `pass if within ${T.gap_threshold_pct}% of the best known plan`)}
    ${tile('Memory, limited', V.memory ? `<span class="${V.memory === 'pass' ? 'good-t' : 'bad-t'}">${V.memory}${V.complete ? '' : ' so far'}</span>` : 'pending',
      `peak ${fmt(V.limited_peak_mb)} MB, limit ${T.memory_threshold_mb} MB, ${V.limited_killed} killed`)}
    ${tile('Progress', `${p.done} / ${p.total}`, (V.complete ? 'complete: verdicts are final' : 'partial: verdicts may change') + leftText(p))}
  </div>`;
  for (const [c, d] of Object.entries(s.contractors)) {
    if (!d.cells.length) { html += `<div class="card"><h2>${esc(c)}</h2>${esc(d.note || '')}</div>`; continue; }
    html += `<div class="card" style="margin-bottom:14px"><div class="spread"><h2>${esc(c)}</h2>${chartTools(`gap-${c}`, `${e.id}-${c}-gap`)}</div>
      <div class="legend"><span><i style="background:var(--lim)"></i>limited (512 MB, 0.1 CPU)</span><span><i style="background:var(--unl)"></i>unlimited</span>
      <span><i style="background:var(--bad)"></i>${T.gap_threshold_pct}% threshold</span><span>bars: range over repeats</span></div>
      <svg class="chart" id="gap-${esc(c)}" viewBox="0 0 900 280"></svg>
      <p class="muted" style="font-size:12px">Gap = median total student ride time over repeats, compared with the best plan any run found
      (${fmt(d.best_known_ride_min)} student-min, from ${esc(d.best_from)}). The current hand-made routes are ${d.current_routes_gap_pct}% above it
      (${fmt(d.current_routes_ride_min)} student-min).</p>
      <div class="spread" style="margin-top:6px"><h3 style="margin:0">Results by setup and budget</h3>${tableTools(`cells-${c}`, `${e.id}-${c}-results`)}</div>
      <div class="tbl-wrap"><table id="cells-${esc(c)}"><tr><th>Setup</th><th>Budget</th><th>Runs ok</th><th>Student-min</th><th>Gap</th><th>First plan</th><th>Wall</th><th>Solver CPU</th><th>Peak MB</th></tr>
      ${d.cells.map(x => `<tr><td>${esc(x.setup)}</td><td>${x.budget_s} s</td><td>${x.ok}/${x.runs}${x.not_ok.length ? ` <span class="bad-t">(${esc(x.not_ok.join(', '))})</span>` : ''}</td>
        <td>${fmt(x.ride_min)}</td><td>${x.gap_pct == null ? '–' : x.gap_pct + '%'}</td><td>${x.first_plan_s ?? '–'} s</td><td>${x.wall_s ?? '–'} s</td><td>${x.cpu_s ?? '–'} s</td><td>${x.peak_mb ?? '–'}</td></tr>`).join('')}
      </table></div></div>`;
  }
  html += `<div class="card" style="margin-bottom:14px"><div class="spread"><h2>Every run</h2>${tableTools('allruns', `${e.id}-runs`)}</div><div class="tbl-wrap"><table id="allruns">
    <tr><th>Run</th><th>Status</th><th>Started</th><th>Student-min</th><th>Peak MB</th><th>Wall</th></tr>
    ${s.rows.map(r => `<tr class="${r.status === 'ok' ? 'click' : ''}" data-run="${esc(r.key)}"><td>${esc(r.key)}</td>
      <td><span class="chip ${r.status === 'ok' ? 'good' : 'bad'}">${esc(r.status)}</span></td><td>${esc(when(r.started_at))}</td>
      <td>${fmt(r.total_student_ride_min)}</td><td>${r.peak_mb ?? '–'}</td><td>${r.wall_s} s</td></tr>`).join('')}
    </table></div><p class="muted" style="font-size:12px">Click a run to see its routes on a map.</p></div>`;
  const m = s.meta || {}, mc = m.machine || {};
  html += `<div class="card"><h2>Machine</h2><div class="tbl-wrap"><table>
    ${[['Host', mc.host], ['CPU', mc.cpu], ['Cores', mc.cpus], ['RAM', mc.ram_gb ? mc.ram_gb + ' GB' : null], ['Kernel', mc.kernel], ['Python', mc.python],
      ['OR-Tools', mc.ortools], ['Limits the kernel applied', m.limits ? Object.entries(m.limits.found || {}).map(([k, x]) => `${k}=${x}`).join(', ') : null],
      ['Code version', codeVersions(s.rows, m)], ['Python packages', (mc.packages || []).join(', ') || null],
      ['Started', when(m.started_at)]].map(([k, x]) => `<tr><td>${esc(k)}</td><td class="l" style="white-space:normal">${esc(x ?? '–')}</td></tr>`).join('')}
    </table></div></div>`;
  v.innerHTML = html;
  bindRunRows(v);
  bindExports(v);
  for (const [c, d] of Object.entries(s.contractors)) {
    if (!d.cells.length) continue;
    const spread = repeatSpread(s.rows.filter(r => r.contractor === c), d.best_known_ride_min);
    gapChart(document.getElementById(`gap-${c}`), d.cells, T.gap_threshold_pct, spread);
  }
}

function bindRunRows(v) {
  v.querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { location.hash = `#/runs/${encodeURIComponent(tr.dataset.run)}`; });
}

function codeVersions(rows, meta) {
  const vs = [...new Set(rows.map(r => r.code_version).filter(Boolean))];
  if (!vs.length && meta.code_version) vs.push(meta.code_version);
  return vs.length ? vs.map(x => x.slice(0, 7) + (x.endsWith('-dirty') ? ' (with uncommitted edits)' : '')).join(', ') : 'not recorded (runs before 2026-11-04)';
}

// Min and max gap per (setup, budget) over the repeats, for the range bars.
function repeatSpread(rows, best) {
  const out = {};
  rows.filter(r => r.status === 'ok' && r.setup !== 'reference').forEach(r => {
    const k = `${r.setup}|${r.budget_s}`, g = (r.total_student_ride_min - best) / best * 100;
    out[k] = out[k] ? [Math.min(out[k][0], g), Math.max(out[k][1], g)] : [g, g];
  });
  return out;
}

function genericExperiment(e, s, p) {
  const rows = s.rows || [];
  const verdicts = expVerdicts(e);
  const cols = [...new Set(rows.flatMap(r => Object.keys(r).filter(k => r[k] === null || typeof r[k] !== 'object')))].slice(0, 10);
  return `${verdicts ? `<p>${verdicts}</p>` : ''}<div class="tiles">${tile('Progress', `${p.done} / ${p.total}`, leftText(p).replace(' · ', ''))}
      ${tile('Runs ok', rows.filter(r => r.status === 'ok').length, `${rows.filter(r => r.status && r.status !== 'ok').length} not ok`)}</div>
    <div class="card"><div class="spread"><h2>Every run</h2>${tableTools('allruns', `${e.id}-runs`)}</div>
    ${rows.length ? `<div class="tbl-wrap"><table id="allruns"><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr>
      ${rows.map(r => `<tr class="${D.runs.some(x => x.id === r.key) ? 'click' : ''}" data-run="${esc(r.key)}">${cols.map(c => `<td>${esc(typeof r[c] === 'number' ? fmt(r[c]) : r[c] ?? '–')}</td>`).join('')}</tr>`).join('')}
      </table></div>` : '<div class="empty">No runs yet.</div>'}</div>`;
}

/* ------------------------------------------------------------------ rerouting and scaling views */

// Which page an experiment gets: by kind, then by the summary's shape. Anything else keeps the generic page.
function experimentBody(e, s, p) {
  if (e.kind === 'reroute' && s.pass === 'quality') return qualityExperiment(e, s, p);
  if (e.kind === 'reroute' && s.pass === 'limits') return limitsExperiment(e, s, p);
  if (e.kind === 'reroute' && s.pass === 'scale') return rerouteScaleExperiment(e, s, p);
  if (e.kind === 'scale') return optimizerScaleExperiment(e, s, p);
  return genericExperiment(e, s, p);
}

const num = x => (x == null ? '–' : fmt(x));
const pctOf = x => (x == null ? '–' : `${Math.round(x * 1000) / 10}%`);
const roundTo = (x, d = 1) => (x == null ? null : Math.round(x * 10 ** d) / 10 ** d);
const vals = a => a.filter(x => x != null && Number.isFinite(x));
const medianOf = a => { const v = vals(a).sort((x, z) => x - z), m = v.length >> 1; return !v.length ? null : v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2; };
const maxOf = a => { const v = vals(a); return v.length ? Math.max(...v) : null; };
const uniq = a => [...new Set(a)];
const rawCell = s => ({ html: s }); // a table cell that is already HTML (every other cell is escaped)
const card = (title, tools, body, note = '') => `<div class="card" style="margin-bottom:14px"><div class="spread"><h2>${esc(title)}</h2>${tools}</div>${body}
  ${note ? `<p class="muted" style="font-size:12px">${note}</p>` : ''}</div>`;
const subHead = (title, tools) => `<div class="spread" style="margin-top:10px"><h3 style="margin:0">${esc(title)}</h3>${tools}</div>`;

function dataTable(id, head, rows, rowClass = () => '') {
  const cell = c => (c && typeof c === 'object' && 'html' in c ? c.html : esc(c ?? '–'));
  return `<div class="tbl-wrap"><table id="${esc(id)}"><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr>
    ${rows.map((r, i) => `<tr class="${esc(rowClass(i))}">${r.map(c => `<td>${cell(c)}</td>`).join('')}</tr>`).join('')}</table></div>`;
}

// The raw run table under every dedicated page: the generic page's "Every run" card, unchanged.
function rawRuns(e, s) {
  const rows = s.rows || [];
  const cols = [...new Set(rows.flatMap(r => Object.keys(r).filter(k => r[k] === null || typeof r[k] !== 'object')))].slice(0, 10);
  return `<div class="card"><div class="spread"><h2>Every run</h2>${tableTools('allruns', `${e.id}-runs`)}</div>
    ${rows.length ? `<div class="tbl-wrap"><table id="allruns"><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr>
      ${rows.map(r => `<tr class="${D.runs.some(x => x.id === r.key) ? 'click' : ''}" data-run="${esc(r.key)}">${cols.map(c => `<td>${esc(typeof r[c] === 'number' ? fmt(r[c]) : r[c] ?? '–')}</td>`).join('')}</tr>`).join('')}
      </table></div>` : '<div class="empty">No runs yet.</div>'}</div>`;
}

function progressTile(s, p) {
  const v = s.verdict || {}, judged = (s.chips || []).length, done = judged ? v.complete : p.done >= p.total;
  // A verdict still null on a complete pass had no judged row to work on: it is pending, not final.
  const pending = rerouteRules(s.pass, {}).filter(r => v[r.key] == null).length;
  const final = !judged ? '' : !pending ? ': verdicts are final'
    : `: ${plural(pending, 'verdict')} pending, no judged rows to decide ${pending === 1 ? 'it' : 'them'}`;
  return tile('Progress', `${p.done} / ${p.total}`, `${s.runs_failed ? `${plural(s.runs_failed, 'failed run')} · ` : ''}` +
    (done ? `complete${final}` : `partial${judged ? ': verdicts may change' : ''}`) + leftText(p));
}

// Thresholds 1 to 6 of the logbook (2026-11-16), worded from the summary's own threshold values.
function rerouteRules(pass, t) {
  if (pass === 'quality') return [
    { key: 'gain', n: 1, name: 'Closure-specific gain', rule: `median of (R0 − R3 with the closure) − (R0 − R3 with no closure) at ${t.judged_limit_m} m is at least ${t.gain_min_s} s` },
    { key: 'near_oracle', n: 2, name: 'Greedy near exact', rule: `R2 within ${t.near_oracle_s} s of R3 in at least ${pctOf(t.near_oracle_share)} of judged scenarios, and on every route's median (${t.judged_limit_m} m)` },
    { key: 'no_violations', n: 3, name: 'No violations', rule: 'no failed run, nobody unserved where a boarding point exists, R3 never later than R0' }];
  if (pass === 'limits') return [
    { key: 'first_plan', n: 4, name: 'First plan in time', rule: `a plan valid on true times within ${t.first_plan_s} s in at least ${pctOf(t.first_plan_share)} of judged scenarios (graph_limited, worst repeat)` },
    { key: 'at_30', n: 5, name: 'Near the oracle at 30 s', rule: `at 30 s within ${t.near_oracle_s} s of the oracle in at least ${pctOf(t.at_30_share)} of judged scenarios (graph_limited, worst repeat)` },
    { key: 'memory', n: 6, name: 'Memory', rule: `peak under ${t.memory_mb} MB including the graph, no worker killed (every graph_limited row)` }];
  return [];
}

function verdictList(pass, thresholds, verdict) {
  const rules = rerouteRules(pass, thresholds || {});
  if (!rules.length) return '';
  const word = r => (r == null ? '<span class="chip">pending</span>'
    : `<span class="chip ${r === 'pass' ? 'good' : 'bad'}">${esc(r)}${verdict.complete ? '' : ' so far'}</span>`);
  return `<ul class="checks verdicts">${rules.map(r => `<li>${word(verdict[r.key])}<span><strong>${r.n}. ${esc(r.name)}</strong>
    <span class="muted">${esc(r.rule)}</span></span></li>`).join('')}</ul>
    <p class="muted" style="font-size:12px;margin:8px 0 0">${pass === 'limits'
    ? `Thresholds 4 and 5 are judged on graph_limited rows of synthetic scenarios in the judged set (at least 2 remaining stops, R0 loses at least 60 s),
      each scenario's worst repeat. Threshold 6 is a property of the worker process, so it is judged on every graph_limited row (any scenario, judged or not,
      synthetic or historical) once a judged scenario exists.`
    : `Judged on synthetic scenarios in the judged set (at least 2 remaining stops, R0 loses at least 60 s); threshold 3 also fails on a failed run of any
      synthetic scenario. Historical scenarios are reported apart and never pooled.`} Fixed in the logbook on 2026-11-16, before any scenario existed.</p>`;
}

function pendingRules(pending) {
  const list = verdictList(pending.pass, pending.thresholds, {});
  return list ? `<div class="card" style="margin-top:14px"><h2>What this pass will judge</h2>${list}</div>` : '';
}

// Rows that should have run under the free-tier limits: graph_unlimited rows of the limits pass and
// unlimited-setup rows of the scale pass record "none" by design, so they are left out.
const meantLimited = (pass, r) => (pass === 'limits' ? r.arm !== 'graph_unlimited' : pass === 'scale' ? r.setup !== 'unlimited' : true);

// Rows from a machine with no free-tier limits say nothing about the free tier: say so above the numbers.
function limitsNote(s) {
  const m = s.meta || {}, mc = m.machine || {}, rows = s.rows || [];
  const seen = uniq([m.limits, ...rows.filter(r => meantLimited(s.pass, r)).map(r => r.limits)].filter(x => x != null));
  const byDesign = s.pass === 'limits' ? 'graph_unlimited rows' : s.pass === 'scale' ? 'unlimited-setup rows' : '';
  const unlimited = byDesign && rows.some(r => !meantLimited(s.pass, r)) ? ` The ${byDesign} ran without limits by design.` : '';
  if (!seen.length) return '';
  if (seen.includes('none')) {
    return `<div class="banner"><strong>Limits: none.</strong> ${seen.length > 1 ? `Some rows ran with limits ${esc(seen.filter(x => x !== 'none').join(', '))}, others with none. ` : ''}
      These runs had no memory or CPU limits${mc.host ? ` (${esc(mc.host)}${mc.system ? `, ${esc(mc.system)}` : ''})` : ''}, so their times and memory say nothing
      about the free tier (512 MB, no swap, 0.1 CPU). Only rows run under systemd limits in WSL do.</div>`;
  }
  const found = m.limits_check && m.limits_check.found ? Object.entries(m.limits_check.found).map(([k, x]) => `${k}=${x}`).join(', ') : '';
  return `<p class="muted">Limits recorded: <strong>${esc(seen.join(', '))}</strong>${found ? ` (${esc(found)})` : ''}.${esc(unlimited)}</p>`;
}

/* charts: one SVG string, so a test can read it and chartTools can export it */

function lineChart(id, o) {
  const all = o.series.flatMap(s => s.pts);
  if (!all.length) return '<div class="empty">Nothing to chart yet.</div>';
  const W = 900, H = o.h || 300, l = 64, r = 190, t = 28, b = 40;
  const xs = o.xs || uniq(all.map(q => q[0])).sort((a, z) => a - z), x0 = xs[0], x1 = xs[xs.length - 1];
  const fx = x => (xs.length < 2 ? 0.5 : o.xScale === 'cat' ? xs.indexOf(x) / (xs.length - 1)
    : o.xScale === 'log' ? Math.log(x / x0) / Math.log(x1 / x0) : (x - x0) / (x1 - x0));
  const X = x => roundTo(l + (W - l - r) * fx(x));
  const ys = all.map(q => q[1]);
  let Y, ticks;
  if (o.yLog) {
    const lo = Math.floor(Math.log10(Math.min(...ys))), hi = Math.max(Math.ceil(Math.log10(Math.max(...ys))), lo + 1);
    Y = y => roundTo(t + (H - t - b) * (1 - (Math.log10(y) - lo) / (hi - lo)));
    ticks = Array.from({ length: hi - lo + 1 }, (_, i) => 10 ** (lo + i));
  } else {
    const y0 = Math.min(0, ...ys), top = Math.max(0, ...ys), y1 = top === y0 ? y0 + 1 : top + (top - y0) * 0.08;
    Y = y => roundTo(t + (H - t - b) * (1 - (y - y0) / (y1 - y0)));
    ticks = Array.from({ length: 5 }, (_, i) => y0 + (y1 - y0) * i / 4);
  }
  const yLabel = o.yFmt || (y => fmt(roundTo(y, 1)));
  let g = ticks.map(y => `<line x1="${l}" x2="${W - r}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--line)"/><text x="${l - 8}" y="${Y(y) + 4}" text-anchor="end">${esc(yLabel(y))}</text>`).join('');
  g += xs.map(x => `<text x="${X(x)}" y="${H - b + 18}" text-anchor="middle">${esc((o.xFmt || String)(x))}</text>`).join('');
  o.series.forEach((s, i) => {
    if (!s.pts.length) return;
    const dash = s.dash ? ' stroke-dasharray="7 5"' : '';
    g += `<polyline data-series="${esc(s.name)}" points="${s.pts.map(q => `${X(q[0])},${Y(q[1])}`).join(' ')}" fill="none" stroke="${s.colour}" stroke-width="2.5"${dash}/>`;
    g += s.pts.map(q => `<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="4" fill="${s.colour}"><title>${esc(`${s.name}: ${(o.xFmt || String)(q[0])}, ${q[2] ?? yLabel(q[1])}`)}</title></circle>`).join('');
    const ly = t + 4 + i * 18;
    g += `<line x1="${W - r + 16}" x2="${W - r + 40}" y1="${ly}" y2="${ly}" stroke="${s.colour}" stroke-width="2.5"${dash}/><text x="${W - r + 46}" y="${ly + 4}">${esc(s.name)}</text>`;
  });
  return `<svg class="chart" id="${esc(id)}" viewBox="0 0 ${W} ${H}">${g}<text x="${l}" y="12">${esc(o.title)}</text>
    <text x="${W - r}" y="${H - 2}" text-anchor="end">${esc(o.xTitle)}</text></svg>`;
}

const SERIES = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--good)', 'var(--bad)', 'var(--muted)'];

/* quality pass */

function qualityExperiment(e, s, p) {
  const cells = s.cells || [], rows = s.rows || [], pr = s.per_route || {}, M = ['R0', 'R2', 'R3'];
  const scen = kind => uniq(rows.filter(r => r.kind === kind).map(r => r.scenario)).length;
  const cellsOf = (scope, kind, arm) => cells.filter(c => c.scope === scope && c.kind === kind && c.arm === arm);
  let out = `<div class="card" style="margin-bottom:14px"><h2>Verdicts</h2>${verdictList('quality', s.thresholds, s.verdict || {})}</div>
    <div class="tiles">${progressTile(s, p)}
      ${tile('Judged share', pctOf(s.judged_share), 'main-arm rows with at least 2 remaining stops where R0 loses at least 60 s')}
      ${tile('Scenarios', `${scen('synthetic')} + ${scen('historical')}`, 'synthetic + historical, reported apart')}
      ${tile('Worst route', esc(pr.worst_route ?? '–'), esc(pr.worst_by ? `by ${pr.worst_by}` : ''))}</div>`;

  // R0, R2, R3 x walking limit, per scope; synthetic and historical in separate tables, never pooled.
  const head = ['Limit', 'Method', 'Scenarios ok', 'Infeasible', 'Median delay (s)', 'P90 delay (s)', 'Worst delay (s)', 'Walkers (median)', 'Walk per walker (m)', 'Differs from R0'];
  const methodRows = cs => uniq(cs.map(c => c.limit_m)).sort((a, z) => a - z).flatMap(lim => M.map(m => cs.find(c => c.limit_m === lim && c.method === m)).filter(Boolean))
    .map(c => [`${c.limit_m} m`, c.method, `${c.ok}/${c.scenarios}`, c.infeasible, num(c.median_delay_s), num(c.p90_delay_s), num(c.worst_delay_s),
      num(c.median_walkers), num(c.median_walk_m_per_walker), c.method === 'R3' ? pctOf(c.share_differs_from_r0) : '']);
  for (const [scope, title] of [['judged', 'Methods on the judged set'], ['all', 'Methods on every scenario']]) {
    let body = '';
    for (const kind of ['synthetic', 'historical']) {
      const cs = cellsOf(scope, kind, 'main'), id = `q-${scope}-${kind}`;
      body += subHead(kind === 'synthetic' ? 'Synthetic scenarios' : 'Historical scenarios', cs.length ? tableTools(id, `${e.id}-${scope}-${kind}-methods`) : '') +
        (cs.length ? dataTable(id, head, methodRows(cs)) : `<p class="muted">No ${kind} scenarios ${scope === 'judged' ? 'in the judged set ' : ''}yet.</p>`);
    }
    out += card(title, '', body, 'Delay = arrival at campus minus the no-closure arrival, in seconds. "Differs from R0": share of scenarios where the exact plan is not the patched route.');
  }

  // The control and must-serve arms, at the judged limit only.
  const armRows = [];
  for (const arm of ['control', 'must_serve']) for (const scope of ['judged', 'all']) for (const kind of ['synthetic', 'historical']) {
    cellsOf(scope, kind, arm).forEach(c => armRows.push([arm === 'control' ? 'no-closure control' : 'must-serve', scope, kind, c.method, `${c.ok}/${c.scenarios}`,
      num(c.median_delay_s), num(c.p90_delay_s), num(c.worst_delay_s), num(c.median_walkers)]));
  }
  const lim = (s.thresholds || {}).judged_limit_m ?? 400;
  out += card(`Control and must-serve arms (${lim} m)`, armRows.length ? tableTools('q-arms', `${e.id}-arms`) : '',
    armRows.length ? dataTable('q-arms', ['Arm', 'Scope', 'Kind', 'Method', 'Scenarios ok', 'Median delay (s)', 'P90 delay (s)', 'Worst delay (s)', 'Walkers (median)'], armRows)
      : '<p class="muted">No control or must-serve rows yet.</p>',
    'Control: the same solve on times with no closure; its R0 − R3 gain is what skipping stops saves on a normal day, subtracted in threshold 1. ' +
    'Must-serve: 25% of the remaining stops (fixed draw) must board at their own stop.');

  // Median delay by method and limit, on the judged synthetic set (or every synthetic scenario before any is judged).
  const scope = cellsOf('judged', 'synthetic', 'main').length ? 'judged' : 'all', cs = cellsOf(scope, 'synthetic', 'main');
  const limits = uniq(cs.map(c => c.limit_m)).sort((a, z) => a - z);
  out += card('Median delay by method and walking limit', chartTools('q-chart', `${e.id}-median-delay`),
    lineChart('q-chart', { xs: limits, xScale: 'cat', xFmt: x => `${x} m`, title: 'Median delay (s), lower is better', xTitle: 'walking limit',
      series: M.map((m, i) => ({ name: m, colour: [SERIES[1], SERIES[2], SERIES[0]][i],
        pts: cs.filter(c => c.method === m && c.median_delay_s != null).sort((a, z) => a.limit_m - z.limit_m).map(c => [c.limit_m, c.median_delay_s, `${fmt(c.median_delay_s)} s`]) })) }),
    `Synthetic scenarios, ${scope === 'judged' ? 'judged set' : 'every scenario (none judged yet)'}; historical ones are in their own tables above. R0: patched published route. R2: greedy with improvement rounds. R3: exact (the oracle).`);

  // Per route, judged synthetic scenarios at the judged limit, worst route highlighted.
  const routes = pr.routes || [];
  out += card('By route', routes.length ? tableTools('q-routes', `${e.id}-routes`) : '',
    routes.length ? dataTable('q-routes', ['Route', 'Scenarios', 'R2 − R3 median (s)', 'R2 − R3 worst (s)', 'Net gain median (s)', 'Net gain worst (s)', 'R3 delay median (s)', 'R3 delay worst (s)'],
      routes.map(r => [rawCell(`${esc(r.route)}${r.route === pr.worst_route ? ' <span class="chip warn">worst</span>' : ''}`), r.scenarios, num(r.median_r2_minus_r3_s), num(r.worst_r2_minus_r3_s),
        num(r.median_net_gain_s), num(r.worst_net_gain_s), num(r.median_r3_delay_s), num(r.worst_r3_delay_s)]),
      i => (routes[i].route === pr.worst_route ? 'worst' : ''))
      : '<p class="muted">No judged synthetic scenarios yet.</p>',
    pr.worst_route ? `Worst route: <strong>${esc(pr.worst_route)}</strong>, chosen by ${esc(pr.worst_by)} (largest median, then largest worst). Judged synthetic scenarios at ${lim} m; net gain is the main arm's R0 − R3 gain minus the control's.` : '');
  out += `<div class="card" style="margin-bottom:14px" id="pm-card">${planMapCard(e, s, planMapData, planPick)}</div>`;
  return out + rawRuns(e, s);
}

/* plan map: what the rerouter did for one scenario of the quality pass */

const PLAN_METHODS = [['R0', 'patched published route', '--c2', 7, 0.45], ['R2', 'greedy', '--c3', 4.5, 0.85], ['R3', 'exact', '--c1', 2.5, 1]];
let planMapData;        // data/reroute_map.json: undefined until fetched, null when not published or not loaded
let planMapSrc = null;  // which published map file (path and site build time) planMapData came from
let planMapPaint = null; // repaints the plan map card on screen; set by the latest bindPlanMap
let planPick = null;    // { exp, scenario, limit, show } chosen on the quality page
let planMap = null;     // the Leaflet map drawn by bindPlanMap

// Main-arm rows that carry their plans, as { scenario: { limit: row } }.
function planRows(rows) {
  const out = {};
  (rows || []).filter(r => r.arm === 'main' && r.plans).forEach(r => { (out[r.scenario] = out[r.scenario] || {})[r.limit_m] = r; });
  return out;
}

// The picked scenario and limit, kept when still valid; else the first scenario at the judged limit.
function planChoice(e, s, pick) {
  const byScen = planRows(s.rows), ids = Object.keys(byScen).sort();
  if (!ids.length) return null;
  const p = pick && pick.exp === e.id ? pick : {};
  const scenario = byScen[p.scenario] ? p.scenario : ids[0];
  const limits = Object.keys(byScen[scenario]).map(Number).sort((a, z) => a - z);
  const want = p.limit ?? (s.thresholds || {}).judged_limit_m ?? 400;
  const limit = limits.includes(want) ? want : limits[limits.length - 1];
  const show = ['all', ...PLAN_METHODS.map(m => m[0])].includes(p.show) ? p.show : 'all';
  return { exp: e.id, scenario, limit, show, ids, limits, row: byScen[scenario][limit] };
}

const mapMsg = text => `<div class="empty map-msg" id="pm-msg">${text}</div>`;

// The picker, legend, arrivals table and the map's slot (or why there is no map). HTML only, so a test can read it.
function planMapCard(e, s, md, pick) {
  const c = planChoice(e, s, pick);
  const head = `<div class="spread"><h2>Plans on a map</h2>${c ? tableTools('pm-table', `${e.id}-${c.scenario}-${c.limit}m-plans`) : ''}</div>`;
  if (!c) return head + '<p class="muted">These rows were recorded before the quality pass stored its plans, so there is nothing to draw. Rerun the pass to see each scenario\'s R0, R2 and R3 plans here.</p>';
  const r = c.row, sc = md && md.scenarios ? md.scenarios[c.scenario] : null, byScen = planRows(s.rows);
  const label = id => { const x = byScen[id], any = x[Object.keys(x)[0]]; return `${id} (${any.route}, ${any.kind}, ${any.trigger})`; };
  const picker = `<div class="row pick" style="margin:6px 0 10px"><label for="pm-scen" class="muted">Scenario</label>
      <select id="pm-scen">${c.ids.map(id => `<option value="${esc(id)}"${id === c.scenario ? ' selected' : ''}>${esc(label(id))}</option>`).join('')}</select>
      <span class="muted">Walking limit</span><div class="seg" id="pm-lim">${c.limits.map(l => `<button data-l="${esc(l)}" class="${l === c.limit ? 'on' : ''}">${esc(l)} m</button>`).join('')}</div>
      <span class="muted">Show</span><div class="seg" id="pm-show">${['all', ...PLAN_METHODS.map(m => m[0])].map(m => `<button data-m="${esc(m)}" class="${m === c.show ? 'on' : ''}">${esc(m === 'all' ? 'All' : m)}</button>`).join('')}</div></div>`;
  const legend = `<div class="legend" style="margin-bottom:8px">${PLAN_METHODS.map(([m, name, col, w]) => `<span><i style="background:var(${col});height:${Math.min(w, 5)}px"></i>${esc(m)}: ${esc(name)}</span>`).join('')}
      <span><i class="dash"></i>students walking to a boarding point</span><span><i class="ring" style="border-color:var(--bad)"></i>closure</span>
      <span><i class="dotm" style="background:var(--ink)"></i>bus at the trigger</span><span><i class="dotm" style="background:var(--muted)"></i>remaining stop</span>
      <span><i class="dotm hollow"></i>other boarding point</span><span><i class="dotm" style="background:#facc15"></i>campus</span></div>`;
  const rows = PLAN_METHODS.map(([m, name]) => {
    const p = (r.plans || {})[m] || {}, k = m.toLowerCase(), walk = (p.board_at || []).filter(([a, b]) => a !== b);
    return [rawCell(`<strong>${esc(m)}</strong> <span class="muted">${esc(name)}</span>`), num(p.arrival_s), num(r[`${k}_delay_s`]), (p.visit || []).length,
      walk.length ? `${walk.length} stop${walk.length === 1 ? '' : 's'}, ${num(r[`${k}_walkers`])} students` : 'none', (p.unserved || []).length || 'none'];
  });
  const table = dataTable('pm-table', ['Method', 'Arrival (s after the trigger)', 'Delay (s)', 'Points visited', 'Walking', 'Unserved'], rows);
  const status = r.status === 'ok' ? '' : `<p class="bad-t" style="font-size:13px">This row is <strong>${esc(r.status)}</strong>: its plans are drawn as planned, but no delay was scored.</p>`;
  let where;
  if (md === undefined && D.reroute_map) where = mapMsg('Loading the map…');
  else if (!md) where = mapMsg('The map appears once the scenario file (data/scenarios_reroute_v1.json) is built: the toy scenarios of a --quick run have no coordinates. The plans are in the table above.');
  else if (!sc) where = mapMsg(`${esc(c.scenario)} is not in the scenario file the map was built from (toy scenarios have made-up point ids and no coordinates), so it cannot be drawn.`);
  else where = '<div id="pm-map" class="map"></div>';
  return head + picker + table + status + legend + where +
    `<p class="muted" style="font-size:12px">Lines join points in visiting order from the bus to campus: straight lines, not roads. Delay = arrival minus the no-closure arrival
    (${num(r.baseline_arrival_s)} s); negative means earlier than a normal day. ${sc ? `Route ${esc(sc.route)}, closure ${esc(sc.closure)}.` : ''}</p>`;
}

// Draws one scenario's closure, stops and plans on a Leaflet layer; returns the [lat, lng] points it drew, for fitting the view.
function drawPlanMap(layer, md, sc, row, show, cssColour) {
  layer.clearLayers();
  const at = id => { const p = md.points[String(id)]; return p ? [p[0], p[1]] : null; };
  const name = id => (md.points[String(id)] || [])[2] || `point ${id}`;
  const drawn = [];
  (sc.circles || []).forEach(([lat, lng, rad]) => { L.circle([lat, lng], { radius: rad, color: cssColour('--bad'), weight: 1.5, fillOpacity: 0.12 }).bindTooltip(`Closure ${esc(sc.closure)}`).addTo(layer); drawn.push([lat, lng]); });
  for (const [m, label, col, weight, opacity] of PLAN_METHODS) {
    if (show !== 'all' && show !== m) continue;
    const p = (row.plans || {})[m];
    if (!p) continue;
    const path = [sc.position, ...p.visit, -1].map(at).filter(Boolean);
    L.polyline(path, { color: cssColour(col), weight, opacity }).bindTooltip(`${m} (${esc(label)}): arrival ${p.arrival_s == null ? 'never' : `${fmt(p.arrival_s)} s`}`).addTo(layer);
    p.board_at.filter(([s, b]) => s !== b).forEach(([s, b]) => {
      const line = [at(s), at(b)];
      if (line[0] && line[1]) L.polyline(line, { color: cssColour(col), weight: 2, opacity: 0.9, dashArray: '4 6' }).bindTooltip(`${m}: students of ${esc(name(s))} walk to ${esc(name(b))}`).addTo(layer);
    });
    drawn.push(...path);
  }
  const closed = new Set(sc.closed_points || []), rem = new Set(sc.remaining);
  (sc.candidates || []).filter(id => !rem.has(id)).forEach(id => { const q = at(id); if (q) L.circleMarker(q, { radius: 4, color: cssColour('--muted'), weight: 1.5, fillOpacity: 0 }).bindTooltip(`${esc(name(id))}: boarding point`).addTo(layer); });
  sc.remaining.forEach(id => { const q = at(id); if (!q) return; drawn.push(q);
    L.circleMarker(q, { radius: 5, color: '#fff', weight: 1, fillColor: cssColour(closed.has(id) ? '--bad' : '--muted'), fillOpacity: 1 })
      .bindTooltip(`${esc(name(id))}: ${esc((sc.students || {})[id] ?? '?')} students${closed.has(id) ? ', inside the closure' : ''}`).addTo(layer); });
  const bus = at(sc.position);
  if (bus) { L.circleMarker(bus, { radius: 7, color: '#fff', weight: 2, fillColor: cssColour('--ink'), fillOpacity: 1 }).bindTooltip(`Bus at ${esc(name(sc.position))} (${esc(sc.trigger)} trigger)`).addTo(layer); drawn.push(bus); }
  campusMarker(layer);
  return drawn;
}

const cssColour = n => (typeof getComputedStyle === 'function' && getComputedStyle(document.documentElement).getPropertyValue(n).trim()) || EXPORT_COLOURS[n] || '#333';

// After the quality page is on screen: picker handlers, the map file (fetched again after each site build) and the map itself.
function bindPlanMap(v, e, s) {
  const holder = v.querySelector('#pm-card');
  if (!holder) return;
  const paint = () => {
    if (planMap && maps.includes(planMap)) { planMap.remove(); maps = maps.filter(x => x !== planMap); }
    planMap = null;
    const c = planChoice(e, s, planPick);
    holder.innerHTML = planMapCard(e, s, planMapData, planPick);
    bindExports(holder);
    if (!c) return;
    const set = patch => { planPick = { exp: c.exp, scenario: c.scenario, limit: c.limit, show: c.show, ...patch }; paint(); };
    const sel = holder.querySelector('#pm-scen');
    if (sel) sel.onchange = () => set({ scenario: sel.value });
    holder.querySelectorAll('#pm-lim button').forEach(b => b.onclick = () => set({ limit: Number(b.dataset.l) }));
    holder.querySelectorAll('#pm-show button').forEach(b => b.onclick = () => set({ show: b.dataset.m }));
    const el = holder.querySelector('#pm-map'), sc = planMapData && planMapData.scenarios[c.scenario];
    if (!el || !sc || typeof L === 'undefined') return;
    const m = planMap = baseMap(el), layer = L.layerGroup().addTo(m);
    const pts = drawPlanMap(layer, planMapData, sc, c.row, c.show, cssColour);
    if (pts.length) m.fitBounds(L.latLngBounds(pts), { padding: [24, 24], maxZoom: 15 });
  };
  planMapPaint = () => { if (v.contains(holder)) paint(); };
  // Keyed by the site's build time too: under serve.py a rebuild can publish the file, or new content in it.
  const src = D.reroute_map ? `${D.reroute_map}@${D.generated_at ?? ''}` : null;
  if (!src) { planMapData = null; planMapSrc = null; }
  else if (src !== planMapSrc) {
    planMapSrc = src; planMapData = undefined;
    fetch(D.reroute_map, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
      .then(x => { if (planMapSrc !== src) return; planMapData = x; if (planMapPaint) planMapPaint(); });
  }
  paint();
}

/* limits pass */

function limitsExperiment(e, s, p) {
  const cells = s.cells || [], rows = s.rows || [], pr = s.per_route || {}, T = [1, 5, 30];
  const all = cells.filter(c => c.scope === 'all'), sum = k => all.reduce((a, c) => a + (c[k] || 0), 0);
  let out = limitsNote(s) + `<div class="card" style="margin-bottom:14px"><h2>Verdicts</h2>${verdictList('limits', s.thresholds, s.verdict || {})}</div>
    <div class="tiles">${progressTile(s, p)}
      ${tile('Judged share', pctOf(s.judged_share), 'graph_limited rows in the judged set')}
      ${tile('Killed for memory', sum('killed_memory'), 'rows of every arm')}
      ${tile('Invalid on true times', sum('invalid_on_truth'), `${plural(sum('infeasible'), 'infeasible row')}`)}</div>`;
  const rowsOf = (scope, kind, arm) => rows.filter(r => r.kind === kind && r.arm === arm && (scope === 'all' || r.judged));
  for (const [scope, title] of [['judged', 'Arms by checkpoint, judged set'], ['all', 'Arms by checkpoint, every scenario']]) {
    let body = '';
    for (const kind of ['synthetic', 'historical']) {
      const cs = cells.filter(c => c.scope === scope && c.kind === kind), id = `l-${scope}-${kind}`;
      const trs = cs.flatMap(c => T.map(t => {
        const rs = rowsOf(scope, kind, c.arm);
        const valid = rs.length ? rs.filter(r => r[`delay_${t}s`] != null).length / rs.length : null;
        return [c.arm, `${t} s`, `${c.ok}/${c.runs}`, pctOf(valid), num(c[`median_gap_${t}s`]), num(c[`worst_gap_${t}s`]), num(c.median_t_first_s), num(c.peak_mb)];
      }));
      body += subHead(kind === 'synthetic' ? 'Synthetic scenarios' : 'Historical scenarios', cs.length ? tableTools(id, `${e.id}-${scope}-${kind}-checkpoints`) : '') +
        (cs.length ? dataTable(id, ['Arm', 'At', 'Runs ok', 'Valid plan', 'Median gap (s)', 'Worst gap (s)', 'First plan median (s)', 'Peak MB'], trs)
          : `<p class="muted">No ${kind} scenarios ${scope === 'judged' ? 'in the judged set ' : ''}yet.</p>`);
    }
    out += card(title, '', body, 'Valid plan: share of rows whose plan held at that time is valid on true times. Gap: its delay on true times minus the oracle\'s (R3 on true times, no limit). ' +
      'graph_limited plans on the road graph under the limits (judged); graph_unlimited separates graph error; truth_limited separates the time limit.');
  }
  const cnt = cells.map(c => [c.arm, c.scope, c.kind, c.runs, c.ok, c.killed_memory, c.invalid_on_truth, c.infeasible, c.widened, c.city_fallback, num(c.median_planned_minus_true_s)]);
  out += card('Killed, invalid and fallbacks', cnt.length ? tableTools('l-counts', `${e.id}-counts`) : '',
    cnt.length ? dataTable('l-counts', ['Arm', 'Scope', 'Kind', 'Runs', 'Ok', 'Killed (memory)', 'Invalid on truth', 'Infeasible', 'Corridor widened', 'City fallback', 'Planned − true (s, median)'], cnt)
      : '<p class="muted">No rows yet.</p>');
  const routes = pr.routes || [];
  out += card('By route (graph_limited, judged synthetic)', routes.length ? tableTools('l-routes', `${e.id}-routes`) : '',
    routes.length ? dataTable('l-routes', ['Route', 'Runs', 'Ok', 'First plan median (s)', 'First plan worst (s)', 'Gap at 30 s median (s)', 'Gap at 30 s worst (s)'],
      routes.map(r => [rawCell(`${esc(r.route)}${r.route === pr.worst_route ? ' <span class="chip warn">worst</span>' : ''}`), r.runs, r.ok, num(r.median_t_first_s), num(r.worst_t_first_s), num(r.median_gap_30s), num(r.worst_gap_30s)]),
      i => (routes[i].route === pr.worst_route ? 'worst' : ''))
      : '<p class="muted">No graph_limited rows on judged synthetic scenarios yet.</p>',
    pr.worst_route ? `Worst route: <strong>${esc(pr.worst_route)}</strong>, chosen by ${esc(pr.worst_by)}.` : '');
  return out + rawRuns(e, s);
}

/* rerouting scaling */

const SCALE_SKIP = new Set(['key', 'part', 'status', 'started_at', 'code_version', 'limits', 'slices']);

function rerouteScaleExperiment(e, s, p) {
  const rows = (s.rows || []).filter(r => r.status === 'ok'), m = s.meta || {}, cells = s.cells || [];
  const parts = ['stops', 'graph', 'buses', 'slices'];
  let out = limitsNote(s) + `<div class="tiles">${progressTile(s, p)}
    ${tile('Parts with results', parts.filter(x => rows.some(r => r.part === x)).length + ' / 4', esc(parts.map(x => `${x} ${rows.filter(r => r.part === x).length}`).join(' · ')))}
    ${tile('Peak memory', `${num(maxOf(rows.flatMap(r => [r.r2_peak_mb, r.r3_peak_mb, r.peak_mb])))} MB`, 'largest of any row')}</div>`;
  const stops = rows.filter(r => r.part === 'stops');
  for (const setup of uniq(stops.map(r => r.setup))) {
    const rs = stops.filter(r => r.setup === setup), ns = uniq(rs.map(r => r.n_stops)).sort((a, z) => a - z), cs = uniq(rs.map(r => r.per_stop)).sort((a, z) => a - z);
    const FLOOR = 0.001, at = (c, n) => rs.filter(r => r.per_stop === c && r.n_stops === n);
    // R3 over every seed it ran on; a seed stopped at the time cap only gives a lower bound, so such a point says "at least".
    const r3Point = (c, n) => {
      const x = at(c, n).filter(r => r.r3_ran !== false && r.r3_cpu_s != null), y = medianOf(x.map(r => r.r3_cpu_s)), cut = x.filter(r => !r.r3_done).length;
      return y == null ? null : [n, Math.max(y, FLOOR), cut ? `at least ${fmt(y)} CPU-s (${cut} of ${x.length} seeds stopped at the cap)` : `${fmt(y)} CPU-s`];
    };
    const capped = rs.some(r => r.r3_ran !== false && r.r3_cpu_s != null && !r.r3_done);
    const series = cs.flatMap((c, i) => [
      { name: `R3, ${plural(c, 'candidate')} per stop`, colour: SERIES[i % SERIES.length], pts: ns.map(n => r3Point(c, n)).filter(Boolean) },
      { name: `R2, ${plural(c, 'candidate')} per stop`, colour: SERIES[i % SERIES.length], dash: true,
        pts: ns.map(n => [n, medianOf(at(c, n).map(r => r.r2_cpu_s))]).filter(q => q[1] != null).map(([n, y]) => [n, Math.max(y, FLOOR), `${fmt(y)} CPU-s`]) }]);
    const id = `s-cpu-${setup}`;
    out += card(`Stops: solver time against problem size (${setup})`, chartTools(id, `${e.id}-${setup}-cpu`),
      lineChart(id, { xs: ns, xScale: 'lin', xFmt: n => `${n} stops`, yLog: true, yFmt: y => `${fmt(y)} s`, title: 'CPU seconds, median over seeds (log scale)', xTitle: 'remaining stops', series }),
      `Solid: R3 (exact); dashed: R2 (greedy with improvement rounds). R3 is not run above 16 stops. Values under ${FLOOR} s are drawn at ${FLOOR} s. ` +
      `${capped ? 'Some R3 runs stopped at the time cap before finishing: their CPU time is a lower bound, so a point that includes one is a lower bound too (its tooltip says "at least"). ' : ''}` +
      `${setup === 'unlimited' ? 'Unlimited CPU: under 0.1 CPU expect roughly ten times these times.' : 'Wall time under the limits is in the table below.'}`);
    // R2 minus R3 by stops, per problem
    const gapRows = ns.map(n => {
      const g = rs.filter(r => r.n_stops === n && r.r2_minus_r3_s != null).map(r => r.r2_minus_r3_s), bound = rs.filter(r => r.n_stops === n).map(r => r.r2_gap_to_bound_s);
      return [n, g.length, g.filter(x => x <= 0.05).length, g.filter(x => x <= 60).length, num(roundTo(medianOf(g))), num(maxOf(g)), num(roundTo(medianOf(bound)))];
    });
    const gid = `s-gap-${setup}`;
    out += card(`Stops: R2 minus R3 by size (${setup})`, tableTools(gid, `${e.id}-${setup}-r2-minus-r3`),
      dataTable(gid, ['Stops', 'Problems with R3', 'R2 = R3', 'Within 60 s', 'Median (s)', 'Largest (s)', 'R2 above lower bound, median (s)'], gapRows),
      'Per problem, every candidate count and seed. Above 16 stops R3 is not run and only the gap to a weak lower bound is known; it is reported, not used to judge R2.');
    const tid = `s-stops-${setup}`;
    out += card(`Stops: every size and candidate count (${setup})`, tableTools(tid, `${e.id}-${setup}-stops`),
      dataTable(tid, ['Stops', 'Candidates per stop', 'Points', 'Problems', 'R2 CPU median (s)', 'R3 CPU median (s)', 'R3 CPU max (s)', 'R3 wall max (s)', 'R3 done', 'R2 peak MB', 'R3 peak MB'],
        ns.flatMap(n => cs.map(c => at(c, n)).filter(x => x.length).map(x => [x[0].n_stops, x[0].per_stop, uniq(x.map(r => r.points)).join(', '), x.length,
          num(roundTo(medianOf(x.map(r => r.r2_cpu_s)), 3)), num(roundTo(medianOf(x.map(r => r.r3_cpu_s)), 3)), num(maxOf(x.map(r => r.r3_cpu_s))), num(maxOf(x.map(r => r.r3_wall_s))),
          `${x.filter(r => r.r3_done).length}/${x.length}`, num(maxOf(x.map(r => r.r2_peak_mb))), num(maxOf(x.map(r => r.r3_peak_mb)))]))),
      esc(cells.filter(c => c.setup === setup && c.largest_solved_within_s != null)
        .map(c => c.n_stops != null
          ? `Largest size R3 solved on every problem within ${c.largest_solved_within_s} s (${c.basis}): ${c.n_stops} stops.`
          : `R3 did not solve every problem of any size within ${c.largest_solved_within_s} s (${c.basis}).`).join(' ')));
  }
  if (!stops.length) out += card('Stops', '', `<p class="muted">${notRun(m, 'stops')}</p>`);
  for (const part of ['graph', 'buses', 'slices']) {
    const rs = rows.filter(r => r.part === part), id = `s-${part}`;
    const cols = uniq(rs.flatMap(r => Object.keys(r).filter(k => !SCALE_SKIP.has(k) && (r[k] === null || typeof r[k] !== 'object'))));
    out += card(`${part[0].toUpperCase()}${part.slice(1)}`, rs.length ? tableTools(id, `${e.id}-${part}`) : '',
      rs.length ? dataTable(id, cols, rs.map(r => cols.map(k => (typeof r[k] === 'number' ? fmt(r[k]) : r[k])))) : `<p class="muted">${notRun(m, part)}</p>`);
  }
  return out + rawRuns(e, s);
}

const notRun = (meta, part) => (meta.only && meta.only !== part ? `Not run: this pass was started with --only ${meta.only}.` : 'Not run yet.');

/* optimizer scaling */

function optimizerScaleExperiment(e, s, p) {
  const rows = s.rows || [], m = s.meta || {}, mc = m.machine || {};
  const ok = rows.filter(r => r.status === 'ok').sort((a, z) => (a.stops - z.stops) || String(a.lookup).localeCompare(z.lookup));
  const other = rows.filter(r => r.status !== 'ok');
  const cps = [10, 60, 300].filter(t => !m.budget_s || t <= m.budget_s);
  let out = `<div class="tiles">${tile('Progress', `${p.done} / ${p.total}`, `${other.length} not run or not ok` + leftText(p))}
    ${tile('Budget', `${num(m.budget_s)} s`, `${esc(m.setup || '')} · each run a fresh process`)}
    ${tile('Machine', esc(mc.host || '–'), esc([mc.cpus && `${mc.cpus} CPUs`, mc.ortools && `OR-Tools ${mc.ortools}`].filter(Boolean).join(' · ')))}</div>`;
  out += card('Instance by lookup', ok.length ? tableTools('o-runs', `${e.id}-results`) : '',
    ok.length ? dataTable('o-runs', ['Instance', 'Lookup', 'Stops', 'Buses', 'Build (s)', 'First plan (s)', 'Peak MB', ...cps.map(t => `Ride ${t} s`), 'Scored (student-min)', 'Longest ride (min)'],
      ok.map(r => [r.instance, r.lookup, r.stops, r.buses, num(r.build_s), num(r.first_plan_s), num(r.peak_mb), ...cps.map(t => num(r[`ride_${t}s`])), num(r.total_student_ride_min), num(r.longest_ride_min)]))
      : '<p class="muted">No finished runs yet.</p>',
    '<strong>build_s is not comparable between lookups:</strong> the matrix lookup builds its tables inside build_s, while the callback computes arc costs during the search (in first plan and the search). ' +
    'Ride = the solver\'s best cost / 60 after that much search (student-minutes plus a small driving tie-breaker); Scored = total student ride time of the returned plan. ' +
    'Peak memory is the operating system\'s figure for the machine that ran it. Doubled instances copy every stop and bus 30 s from the original: they test model size, not geography.');
  if (other.length) {
    out += card('Not run', '', `<ul class="log-list">${other.map(r => `<li><span class="chip ${r.status === 'skipped' ? '' : 'bad'}">${esc(r.status)}</span>
      <strong>${esc(r.instance || r.key)}</strong> ${esc(r.lookup || '')}<span class="muted">${esc(r.reason || r.error || '')}</span></li>`).join('')}</ul>`,
      'Skipped runs are run on the next start once their data exists.');
  }
  const insts = uniq(ok.map(r => r.instance)), lookups = uniq(ok.map(r => r.lookup)).sort();
  const series = insts.flatMap((inst, i) => {
    const best = Math.min(...vals(ok.filter(r => r.instance === inst).flatMap(r => cps.map(t => r[`ride_${t}s`]))));
    return lookups.map(lk => {
      const r = ok.find(x => x.instance === inst && x.lookup === lk);
      return { name: `${inst}, ${lk}`, colour: colour(i), dash: lk !== 'callback',
        pts: r ? cps.filter(t => r[`ride_${t}s`] != null).map(t => [t, (r[`ride_${t}s`] - best) / best * 100, `${fmt(r[`ride_${t}s`])} (${roundTo((r[`ride_${t}s`] - best) / best * 100, 2)}% above)`]) : [] };
    });
  });
  if (ok.length) {
    out += card('Ride cost against search time', chartTools('o-ride', `${e.id}-ride`),
      lineChart('o-ride', { xs: cps, xScale: 'log', xFmt: t => `${t} s`, yFmt: y => `${roundTo(y, 2)}%`, title: "Ride cost above the instance's best plan (either lookup), lower is better", xTitle: 'search time (log scale)', series, h: 320 }),
      'Solid: callback lookup; dashed: matrix. One colour per instance. Hover a point for the ride cost itself.');
    out += card('Peak memory against stops', chartTools('o-mem', `${e.id}-memory`),
      lineChart('o-mem', { xScale: 'lin', xFmt: n => `${n}`, yFmt: y => `${Math.round(y)} MB`, title: 'Peak memory (MB)', xTitle: 'stops',
        series: lookups.map((lk, i) => ({ name: lk, colour: SERIES[i], dash: lk !== 'callback',
          pts: ok.filter(r => r.lookup === lk && r.peak_mb != null).map(r => [r.stops, r.peak_mb, `${r.instance}: ${r.peak_mb} MB`]) })) }));
  }
  return out + rawRuns(e, s);
}

function gapChart(svg, cells, threshold, spread = {}) {
  const W = 900, H = 280, l = 56, r = 90, t = 30, b = 36;
  const bud = [...new Set(cells.map(x => x.budget_s))].sort((a, z) => a - z);
  const gaps = cells.map(x => x.gap_pct).filter(x => x != null).concat(Object.values(spread).map(s => s[1]));
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
    pts.forEach(([px, , x]) => {
      const sp = spread[`${setup}|${x.budget_s}`];
      if (sp && sp[1] - sp[0] > 0.01) {
        g += `<line x1="${px}" x2="${px}" y1="${Y(sp[0])}" y2="${Y(sp[1])}" stroke="${col}" stroke-width="1.5" opacity=".5"/>` +
          `<line x1="${px - 5}" x2="${px + 5}" y1="${Y(sp[0])}" y2="${Y(sp[0])}" stroke="${col}" opacity=".5"/><line x1="${px - 5}" x2="${px + 5}" y1="${Y(sp[1])}" y2="${Y(sp[1])}" stroke="${col}" opacity=".5"/>`;
      }
    });
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
    <div class="card">${rows.length ? `<div class="spread" style="margin-bottom:6px"><span class="muted">${plural(rows.length, 'row')}</span>${tableTools('runslist', 'runs')}</div>
      <div class="tbl-wrap"><table id="runslist">
      <tr><th>Run</th><th>Contractor</th><th>Setup</th><th>Budget</th><th>Student-min</th><th>vs current</th><th>Buses</th><th>Peak MB</th><th>Started</th></tr>
      ${rows.map(({ r, c, x }) => `<tr class="click" data-run="${esc(r.id)}" data-c="${esc(c)}"><td>${esc(r.id)}</td><td>${esc(c)}</td><td>${esc(r.setup)}</td>
        <td>${r.time_limit_s} s</td><td>${fmt(x.ride_min)}</td><td class="${x.vs_current_pct < 0 ? 'good-t' : ''}">${sign(x.vs_current_pct)}</td>
        <td>${x.buses ?? '–'}</td><td>${r.peak_mb ?? x.peak_mb ?? '–'}</td><td>${esc(when(r.started_at))}</td></tr>`).join('')}
      </table></div>` : '<div class="empty">No runs yet.</div>'}</div>`;
  bindExports(v);
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
    <div class="grid g2"><div class="card"><div class="spread"><h2>Comparison</h2><span id="cmptools"></span></div><div class="tbl-wrap" id="rtable"></div></div>
      <div class="card"><div class="spread"><h2>How the search improved the plan</h2><span id="progtools"></span></div><svg class="chart" id="prog" viewBox="0 0 900 300"></svg>
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
    $('#cmptools').innerHTML = tableTools('cmp', `${id}-${cur}-comparison`);
    $('#progtools').innerHTML = chartTools('prog', `${id}-${cur}-search`);
    bindExports(v);
    $('#rtable').innerHTML = `<table id="cmp"><tr><th>Measure</th><th>Current</th><th>Optimized</th></tr>${rows.map(([l, k]) =>
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
    <div class="card"><div class="spread"><h2>Current routes</h2><div class="row">${tableTools('routes-tbl', 'current-routes')}<div class="seg" id="rtab">${names.map((n, i) => `<button data-c="${esc(n)}" class="${i ? '' : 'on'}">${esc(n)}</button>`).join('')}</div></div></div>
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
    $('#rtbl').innerHTML = `<table id="routes-tbl"><tr><th>Route</th><th>Bus</th><th>Seats</th><th>Students</th><th>Load</th><th>Stops</th><th class="l">First and last stop</th></tr>
      ${ds.contractors[c].current_routes.map(r => `<tr><td>${esc(r.code)}</td><td>${esc(r.bus)}</td><td>${r.capacity}</td><td>${r.students}</td>
        <td>${Math.round(r.students / r.capacity * 100)}%</td><td>${r.stops.length}</td><td class="l">${esc(r.stops[0])} → ${esc(r.stops[r.stops.length - 1])}</td></tr>`).join('')}</table>`;
    v.querySelectorAll('#rtab button').forEach(x => x.classList.toggle('on', x.dataset.c === c));
  };
  v.querySelectorAll('#rtab button').forEach(b => b.onclick = () => table(b.dataset.c));
  table(names[0]);
  bindExports(v);
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
let autoPublish = true;        // "Publish when it finishes" box
let schedFor = null;           // experiment whose schedule form is open
let schedAt = '01:00';

// Where jobs run: in WSL when the setup check found it working, else on this PC with research/.venv (serve.py decides).
const nativeRunner = env => !!env && env.runner === 'native';
const runsWhere = env => !env ? 'Experiments run in WSL when it works, otherwise on this PC.'
  : nativeRunner(env) ? 'WSL is not available, so experiments run on this PC (no WSL) with research/.venv. Those that need the free-tier limits need WSL and are greyed out.'
  : 'Everything runs in WSL on this laptop.';
const blockedHere = (e, env) => nativeRunner(env) && e.needs === 'linux';

function viewControl(v) {
  if (!LOCAL) { v.innerHTML = '<div class="empty">Run controls exist only in the local hub on the research laptop.</div>'; return; }
  v.innerHTML = `<h1>Run &amp; publish</h1><p class="muted"><span id="where">${esc(runsWhere(STATUS && STATUS.env))}</span> Results show up in the other tabs as runs finish.</p>
    <div class="grid g2">
      <div class="card"><div class="spread"><h2>Setup</h2><button class="btn" id="chk">Check setup</button></div><div id="env"></div></div>
      <div class="card"><h2>Publish to the shared page</h2><div id="pub"></div></div>
    </div>
    <div class="card" style="margin-top:14px"><div class="spread"><h2>Experiments</h2>
      <label class="row" style="gap:6px;cursor:pointer"><input type="checkbox" id="autopub" ${autoPublish ? 'checked' : ''}>Publish to the shared page when a run finishes</label></div>
      <div id="sched"></div><div id="jobs"></div></div>`;
  $('#chk').onclick = async e => { e.target.disabled = true; e.target.textContent = 'Checking…'; try { STATUS.env = (await api('check', {})).env; } catch (x) { alert(x.message); } renderControl(); };
  $('#autopub').onchange = e => { autoPublish = e.target.checked; };
  renderControl();
}

function renderControl() {
  if (PAGE !== 'control' || !STATUS || !$('#jobs')) return;
  const env = STATUS.env, job = STATUS.job, git = STATUS.git || {}, sch = STATUS.schedule || {};
  const chk = $('#chk'); if (chk) { chk.disabled = false; chk.textContent = 'Check setup'; }
  const native = nativeRunner(env);
  const wh = $('#where'); if (wh) wh.textContent = runsWhere(env);
  const items = native
    ? [['WSL starts (not needed: runs on this PC)', false], ['Python environment (research/.venv)', env.venv],
      ['OR-Tools installed', !!env.ortools], ['Free-tier limits apply: only through WSL', false]]
    : [['WSL starts', env && env.wsl], ['Python environment (~/fc-research-venv)', env && env.venv],
      ['OR-Tools installed', env && env.ortools ? true : env ? false : null], ['Free-tier limits apply (512 MB, 0.1 CPU)', env && env.limits]];
  $('#env').innerHTML = `<ul class="checks">${items.map(([t, ok]) => `<li>${icon(ok)}<span>${esc(t)}</span>${t.startsWith('OR') && env && env.ortools ? `<span class="muted">${esc(env.ortools)}</span>` : ''}</li>`).join('')}</ul>
    ${!env ? '<p class="msg muted">Checking… this takes a few seconds after the hub starts.</p>' : ''}
    ${env && ((env.wsl && !env.ortools) || (native && (!env.venv || !env.ortools))) ? `<p class="msg">The research Python environment is missing. <button class="btn primary" id="inst">Install it</button></p>` : ''}
    ${env && env.message ? `<p class="msg bad-t">${esc(env.message)}</p>` : ''}
    ${env ? `<p class="msg muted">Checked ${esc(when(env.checked_at))}.</p>` : ''}`;
  const inst = $('#inst'); if (inst) inst.onclick = () => startJob('install');

  const running = job && job.state === 'running';
  const busy = running || (STATUS && STATUS.wsl_busy);
  $('#sched').innerHTML = sch.pending ? `<div class="notice"><div><strong>Scheduled:</strong> ${esc(sch.pending.title)} starts at
      ${esc(new Date(sch.pending.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }))}${sch.pending.publish_after ? ', then publishes' : ''}.
      <span class="muted">Keep this hub open and the PC plugged in; the hub stops it from sleeping until then.</span></div>
      <button class="btn" id="unsched">Cancel</button></div>`
    : sch.last ? `<p class="msg muted">${esc(sch.last)}</p>` : '';
  const un = $('#unsched'); if (un) un.onclick = async () => { try { STATUS = await api('schedule/cancel', {}); } catch (x) { alert(x.message); } renderStrip(); renderControl(); };

  // Do not redraw the list under someone typing a time.
  const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest('#jobs');
  if (!typing) {
    $('#jobs').innerHTML = D.experiments.slice().sort((a, b) => b.main - a.main).map(e => {
      const p = expProgress(e), mine = running && job.experiment === e.id, left = p.total - p.done;
      const label = p.done === 0 ? 'Start now' : left > 0 ? 'Resume now' : 'Run again';
      const blocked = blockedHere(e, env), why = blocked ? ' title="Needs WSL: its free-tier limits come from systemd cgroups"' : '';
      const action = mine ? `<button class="btn danger" data-stop>Stop</button>`
        : `<div class="row"><button class="btn ${e.main && !blocked ? 'primary' : ''}" data-start="${esc(e.id)}" ${busy || blocked ? 'disabled' : ''}${why}>${label}</button>
           <button class="btn" data-sched="${esc(e.id)}" ${sch.pending || blocked ? 'disabled' : ''}${why}>Schedule…</button></div>`;
      return `<div class="item"${blocked ? ' style="opacity:.65"' : ''}><div class="spread"><div class="row"><strong>${esc(e.title)}</strong>${stateChip(mine ? 'running' : e.state)}
          ${blocked ? '<span class="chip">needs WSL</span>' : ''}<span class="muted">${p.done}/${p.total} runs${leftText(p)}</span></div>${action}</div>
        ${blocked ? '<p class="msg muted">Needs Linux: its free-tier limits come from systemd cgroups, which this PC can only provide through WSL. Install WSL with systemd (see research/README.md), then press Check setup.</p>' : ''}
        ${schedFor === e.id ? `<div class="row schedform">Start at <input type="time" id="schedat" value="${esc(schedAt)}"> (tonight or tomorrow)
          <button class="btn primary" data-setsched="${e.id}">Set</button><button class="btn" data-closesched>Close</button></div>` : ''}
        <p>${esc(e.design)}</p>${bar(p.done, p.total)}
        ${mine && job.log_tail ? `<pre class="log">${esc(job.log_tail.join('\n'))}</pre>` : ''}</div>`;
    }).join('') + (running && job.experiment === 'install' ? `<pre class="log">${esc((job.log_tail || []).join('\n'))}</pre>` : '') +
      (job && !running && job.finished_at ? `<p class="msg muted">Last job: ${esc(job.title)} ${job.exit_code === 0 && !job.stopped ? 'finished' : job.stopped ? 'stopped' : `failed (exit ${job.exit_code})`} at ${esc(when(job.finished_at))}.
        ${job.publish_result ? `<span class="${job.publish_result.ok ? 'good-t' : 'bad-t'}">${esc(job.publish_result.message)}</span>` : ''}</p>` : '') +
      `<p class="msg muted">While a job runs or waits for its start time, the hub keeps this PC from sleeping. If the hub closes, press Resume later: it continues from the last finished run.</p>`;
    $('#jobs').querySelectorAll('[data-start]').forEach(b => b.onclick = () => startJob(b.dataset.start));
    $('#jobs').querySelectorAll('[data-stop]').forEach(b => b.onclick = stopJob);
    $('#jobs').querySelectorAll('[data-sched]').forEach(b => b.onclick = () => { schedFor = b.dataset.sched; renderControl(); const t = $('#schedat'); if (t) t.focus(); });
    $('#jobs').querySelectorAll('[data-closesched]').forEach(b => b.onclick = () => { schedFor = null; renderControl(); });
    const t = $('#schedat'); if (t) t.oninput = () => { schedAt = t.value; };
    $('#jobs').querySelectorAll('[data-setsched]').forEach(b => b.onclick = async () => {
      try { STATUS = await api('schedule', { experiment: b.dataset.setsched, at: schedAt, publish_after: autoPublish }); schedFor = null; }
      catch (x) { alert(x.message); }
      renderStrip(); renderControl();
    });
  }

  $('#pub').innerHTML = `<p style="margin-top:0">${git.changes ? `<strong>${plural(git.changes, 'research change')}</strong> not published yet.` : 'Everything in research/ is saved to git.'}
    ${git.ahead ? ` ${plural(git.ahead, 'commit')} waiting to be pushed.` : ''}</p>
    <p class="muted">Publishing saves research/ to git (only that folder) and pushes it. The shared page updates a minute or two later${git.pages_url ? `: <a href="${esc(git.pages_url)}" target="_blank" rel="noopener">${esc(git.pages_url)}</a>` : ''}.</p>
    ${git.error ? `<p class="msg bad-t">${esc(git.error)}</p>` : ''}
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
  try { STATUS = await api('start', { experiment: id, publish_after: id !== 'install' && autoPublish }); } catch (x) { alert(x.message); }
  renderStrip(); renderControl();
}
async function stopJob() {
  if (!confirm('Stop the running job? Finished runs are kept, and Resume continues from there.')) return;
  try { STATUS = await api('stop', {}); } catch (x) { alert(x.message); }
  renderStrip(); renderControl();
}

function renderStrip() {
  const el = $('#strip'), job = STATUS && STATUS.job, sch = STATUS && STATUS.schedule && STATUS.schedule.pending;
  if ((!job || job.state !== 'running') && STATUS && STATUS.wsl_busy) {
    el.hidden = false;
    el.innerHTML = `<strong>An experiment is running ${nativeRunner(STATUS.env) ? 'on this PC' : 'in WSL'}</strong><span class="muted">started outside this hub; results still show up here as runs finish.</span>
      <button class="btn danger" id="xstop">Stop it</button>`;
    $('#xstop').onclick = stopJob;
    return;
  }
  if (job && job.state === 'running') {
    const e = expById(job.experiment), p = e ? expProgress(e) : null;
    el.hidden = false;
    el.innerHTML = `<strong>Running:</strong> ${esc(job.title)}${p ? ` · ${p.done}/${p.total} runs${leftText(p)}` : ''}
      ${p ? `<div class="bar"><i style="width:${p.total ? p.done / p.total * 100 : 0}%"></i></div>` : ''}
      <span class="muted">started ${esc(when(job.started_at))}${job.publish_after ? ' · publishes when finished' : ''}</span><a href="#/control">Details</a>`;
    return;
  }
  if (sch) {
    el.hidden = false;
    el.innerHTML = `<strong>Scheduled:</strong> ${esc(sch.title)} at ${esc(new Date(sch.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }))}
      <span class="muted">keep this hub open and the PC plugged in</span><a href="#/control">Details</a>`;
    return;
  }
  el.hidden = true;
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
