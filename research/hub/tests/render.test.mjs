// Experiment pages for the rerouting passes and the optimizer scaling run, rendered from the real results.
// Loads hub/web/app.js in node:vm with a tiny DOM stub; reroute summaries come from results/<dir>/summary.json,
// the rest (optimizer scaling, pending passes, the overview) from data/index.json built by build_site.py.
//   node --test "research/hub/tests/*.test.mjs"      (from the repository root)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const HUB = join(dirname(fileURLToPath(import.meta.url)), '..');
const RESEARCH = join(HUB, '..');
const RESULTS = join(RESEARCH, 'results');

function buildIndex() {
  const venv = join(RESEARCH, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const py = existsSync(venv) ? venv : 'python';
  const out = mkdtempSync(join(tmpdir(), 'hub-render-'));
  const r = spawnSync(py, [join(HUB, 'build_site.py'), '--out', join(out, 'site')], { cwd: RESEARCH, encoding: 'utf-8' });
  assert.equal(r.status, 0, r.stderr);
  const index = JSON.parse(readFileSync(join(out, 'site', 'data', 'index.json'), 'utf-8'));
  rmSync(out, { recursive: true, force: true });
  return index;
}

function loadApp(source, index) {
  const el = () => ({ innerHTML: '', textContent: '', hidden: true, querySelectorAll: () => [], closest: () => null });
  const els = new Map();
  const get = k => { if (!els.has(k)) els.set(k, el()); return els.get(k); };
  const ctx = {
    console, URL, Blob: class {}, setTimeout, setInterval: () => 0,
    document: { querySelector: s => get(s), getElementById: id => get('#' + id), documentElement: {}, activeElement: null },
    window: { addEventListener() {}, scrollY: 0, scrollTo() {} },
    location: { hash: '' }, navigator: {}, getComputedStyle: () => ({ getPropertyValue: () => '' }),
    fetch: () => Promise.reject(new Error('no network in tests')),   // init() fails quietly; the tests set D
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  ctx.__index = index;
  vm.runInContext('D = __index; D.stopsByName = Object.fromEntries(D.dataset.stops.map(s => [s[0], s]));', ctx);
  return { run: code => vm.runInContext(code, ctx), ctx };
}

const APP = readFileSync(join(HUB, 'web', 'app.js'), 'utf-8');
const INDEX = buildIndex();
const app = loadApp(APP, INDEX);

// The page body for an experiment whose summary comes from a results folder (or from the index).
function page(id, summary) {
  app.ctx.__id = id;
  app.ctx.__s = summary;
  return app.run(`(() => { const e = { ...expById(__id) }; if (__s) { e.summary = __s; } return experimentBody(e, e.summary, expProgress(e)); })()`);
}
const summaryOf = dir => JSON.parse(readFileSync(join(RESULTS, dir, 'summary.json'), 'utf-8'));
const count = (html, re) => (html.match(re) || []).length;

// Every table can be exported, every chart too, and no number came out as NaN or undefined.
function assertWellFormed(html) {
  const tables = [...html.matchAll(/<table id="([^"]+)"/g)].map(m => m[1]);
  for (const id of tables) assert.ok(html.includes(`data-table="${id}"`), `table ${id} has no CSV/LaTeX buttons`);
  const charts = [...html.matchAll(/<svg class="chart" id="([^"]+)"/g)].map(m => m[1]);
  for (const id of charts) assert.ok(html.includes(`data-chart="${id}"`), `chart ${id} has no PNG/SVG buttons`);
  assert.equal(new Set(tables).size, tables.length, 'table ids are unique');
  assert.ok(!/NaN|undefined|Infinity/.test(html), 'no NaN, undefined or Infinity in the page');
}

test('quality view: verdict list, method tables, chart, per-route table and the raw runs', () => {
  const s = summaryOf('reroute-quality-quick');
  const html = page('reroute-quality-quick', s);
  for (const name of ['Closure-specific gain', 'Greedy near exact', 'No violations']) assert.ok(html.includes(name), name);
  assert.ok(html.includes('is at least 60 s'), 'threshold 1 value from summary.thresholds');
  assert.ok(html.includes('in at least 90% of judged scenarios'), 'threshold 2 share');
  assert.equal(count(html, /<span class="chip good">pass<\/span>/g), 3, 'three pass verdicts');
  assert.ok(html.includes('66.7%'), 'judged share');
  for (const id of ['q-judged-synthetic', 'q-all-synthetic', 'q-arms', 'q-routes', 'allruns']) assert.ok(html.includes(`<table id="${id}"`), id);
  assert.ok(!html.includes('<table id="q-judged-historical"'), 'no historical table without historical scenarios');
  assert.ok(html.includes('No historical scenarios'), 'says so instead');
  for (const m of ['R0', 'R2', 'R3']) assert.ok(html.includes(`<td>${m}</td>`), m);
  for (const lim of ['0 m', '400 m', '800 m']) assert.ok(html.includes(`<td>${lim}</td>`), lim);
  assert.ok(html.includes('no-closure control') && html.includes('must-serve'), 'control and must-serve arms');
  const chart = html.slice(html.indexOf('<svg class="chart" id="q-chart"'), html.indexOf('</svg>', html.indexOf('id="q-chart"')));
  assert.equal(count(chart, /<polyline /g), 3, 'one line per method');
  assert.ok(html.includes('class="worst"') && html.includes('T-T <span class="chip warn">worst</span>'), 'worst route highlighted');
  assert.ok(html.includes('median R2 minus R3 delay at 400 m'), 'how the worst route was chosen');
  assertWellFormed(html);
});

test('limits view: thresholds 4 to 6, arm by checkpoint, counts and the no-limits banner', () => {
  const html = page('reroute-limits-quick', summaryOf('reroute-limits-quick'));
  for (const name of ['First plan in time', 'Near the oracle at 30 s', 'Memory']) assert.ok(html.includes(name), name);
  assert.ok(html.includes('within 5 s in at least 95%') && html.includes('under 400 MB'), 'threshold values');
  assert.equal(count(html, /<span class="chip">pending<\/span>/g), 3, 'no graph rows: every verdict pending');
  assert.ok(html.includes('class="banner"') && html.includes('Limits: none.'), 'no-limits banner');
  assert.ok(html.includes('say nothing'), 'banner says the numbers do not speak for the free tier');
  for (const t of ['1 s', '5 s', '30 s']) assert.ok(html.includes(`<td>${t}</td>`), t);
  assert.ok(html.includes('<td>truth_limited</td>'));
  assert.ok(html.includes('<table id="l-counts"') && html.includes('Killed (memory)'));
  assertWellFormed(html);
});

test('rerouting scaling view, part stops: log chart with a line per candidate count, R2 dashed', () => {
  const s = summaryOf('reroute-scale');
  assert.equal(s.rows.length, 45);
  const html = page('reroute-scale', s);
  const chart = html.slice(html.indexOf('<svg class="chart" id="s-cpu-unlimited"'), html.indexOf('</svg>', html.indexOf('id="s-cpu-unlimited"')));
  for (const c of ['1 candidate', '2 candidates', '4 candidates']) {
    assert.ok(chart.includes(`<polyline data-series="R3, ${c} per stop"`), `R3 line for ${c}`);
    assert.match(chart, new RegExp(`<polyline data-series="R2, ${c} per stop"[^>]*stroke-dasharray`), `dashed R2 line for ${c}`);
  }
  assert.ok(chart.includes('log scale'));
  assert.ok(html.includes('<table id="s-gap-unlimited"') && html.includes('R2 above lower bound'), 'R2 minus R3 by stops');
  assert.ok(html.includes('R3 peak MB'), 'peak memory');
  assert.equal(count(html, /Not run: this pass was started with --only stops\./g), 3, 'graph, buses and slices not run');
  assert.ok(html.includes('Limits: none.'));
  assertWellFormed(html);
});

test('rerouting scaling pipeline test: slices table, graph and buses not run yet', () => {
  const html = page('reroute-scale-quick', summaryOf('reroute-scale-quick'));
  assert.ok(html.includes('<table id="s-slices"') && html.includes('max_state_bytes'));
  assert.equal(count(html, /<p class="muted">Not run yet\.<\/p>/g), 2);
  assertWellFormed(html);
  assertWellFormed(page('reroute-scale-r2-insertion', summaryOf('reroute-scale-r2-insertion')));
});

test('optimizer scaling view: instance by lookup, skipped rows with their reason, ride chart', () => {
  const e = INDEX.experiments.find(x => x.id === 'optimizer-scale');
  assert.equal(e.summary.rows.length, 12);
  const html = page('optimizer-scale');
  assert.equal(count(html, /<tr class=""><td>[A-Za-z-]+<\/td><td>(callback|matrix)<\/td>/g), 8, 'eight finished runs');
  assert.equal(count(html, /<span class="chip ">skipped<\/span>/g), 4, 'four skipped rows listed');
  assert.ok(html.includes('missing data/matrix_fall2026_v1_all.json'), 'with their reason');
  assert.ok(html.includes('build_s is not comparable between lookups'), 'the build_s caveat');
  assert.ok(html.includes('<td>31,472</td>') && html.includes('<td>53.7</td>'), 'scored ride and longest ride of Jadoon');
  const chart = html.slice(html.indexOf('id="o-ride"'), html.indexOf('</svg>', html.indexOf('id="o-ride"')));
  assert.equal(count(chart, /<polyline /g), 8, 'one line per instance and lookup');
  assert.equal(count(chart, /<polyline [^>]*stroke-dasharray/g), 4, 'matrix lines dashed');
  assertWellFormed(html);
  const quick = page('optimizer-scale-quick');
  assert.ok(quick.includes('Ride 10 s') && !quick.includes('Ride 300 s'), 'the 10 s pipeline test has one checkpoint');
  assertWellFormed(quick);
});

test('values from the results are escaped', () => {
  const s = summaryOf('reroute-quality-quick');
  s.per_route.routes[0].route = s.per_route.worst_route = '<img src=x onerror=alert(1)>';
  s.rows[0].scenario = '<script>x</script>';
  const html = page('reroute-quality-quick', s);
  assert.ok(!html.includes('<img') && !html.includes('<script>'));
});

test('overview: the Rerouting card shows its passes, with pending rules before they run', () => {
  const v = { innerHTML: '', querySelectorAll: () => [] };
  app.ctx.__v = v;
  app.run('viewOverview(__v)');
  const card = v.innerHTML.slice(v.innerHTML.indexOf('<h3>Rerouting</h3>'));
  for (const t of ['Rerouting quality pass', 'Rerouting limits pass', 'Rerouting scaling']) assert.ok(card.includes(t), t);
  assert.ok(card.includes('Walking gains at least 60 s net of the no-closure control (400 m, median): pending'), 'quality chips pending');
  assert.ok(card.includes('A valid plan within 5 s in 95% of scenarios (graph, limited, worst repeat): pending'), 'limits chips pending');
  assert.ok(card.includes('curves only, no pass or fail'), 'scaling has no verdict');
  assert.ok(card.includes('total set when it starts'), 'no "0/0 runs" for a pass whose total is not known');
  assert.ok(!/NaN|undefined/.test(card));
});

test('a pass with no runs lists the thresholds it will judge', () => {
  const v = { innerHTML: '', querySelectorAll: () => [] };
  app.ctx.__v = v;
  app.run("viewExperiment(__v, 'reroute-limits')");
  assert.ok(v.innerHTML.includes('No runs yet.') && v.innerHTML.includes('What this pass will judge'));
  assert.ok(v.innerHTML.includes('First plan in time') && v.innerHTML.includes('under 400 MB'));
});

test('every other experiment renders exactly as before', () => {
  const git = spawnSync('git', ['show', 'HEAD:research/hub/web/app.js'], { cwd: RESEARCH, encoding: 'utf-8' });
  if (git.status !== 0) return;          // no git here: nothing to compare with
  const old = loadApp(git.stdout, INDEX);
  for (const e of INDEX.experiments.filter(x => x.kind !== 'reroute' && x.kind !== 'scale')) {
    const render = a => { const v = { innerHTML: '', querySelectorAll: () => [] }; a.ctx.__v = v; a.ctx.__id = e.id; a.run('viewExperiment(__v, __id)'); return v.innerHTML; };
    assert.equal(render(app), render(old), e.id);
  }
});
