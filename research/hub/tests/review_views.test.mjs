// Reviewer's failing tests for the rerouting/scaling views and the plan map in hub/web/app.js.
// Each test pins one defect a review found (now fixed), so it does not come back.
//   node --test "research/hub/tests/*.test.mjs"      (from the repository root)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const HUB = join(dirname(fileURLToPath(import.meta.url)), '..');
const RESULTS = join(HUB, '..', 'results');
const APP = readFileSync(join(HUB, 'web', 'app.js'), 'utf-8');
const summaryOf = dir => JSON.parse(readFileSync(join(RESULTS, dir, 'summary.json'), 'utf-8'));

function loadApp(index, extra = {}) {
  const el = () => ({ innerHTML: '', textContent: '', hidden: true, querySelector: () => null, querySelectorAll: () => [], closest: () => null });
  const els = new Map();
  const get = k => { if (!els.has(k)) els.set(k, el()); return els.get(k); };
  const ctx = {
    console, URL, Blob: class {}, setTimeout, setInterval: () => 0,
    document: { querySelector: s => get(s), getElementById: id => get('#' + id), documentElement: {}, activeElement: null },
    window: { addEventListener() {}, scrollY: 0, scrollTo() {} },
    location: { hash: '' }, navigator: {}, getComputedStyle: () => ({ getPropertyValue: () => '' }),
    fetch: () => Promise.reject(new Error('no network in tests')),
    ...extra,
  };
  vm.createContext(ctx);
  vm.runInContext(APP, ctx);
  ctx.__index = index;
  vm.runInContext('D = __index; D.stopsByName = {};', ctx);
  return { run: code => vm.runInContext(code, ctx), ctx };
}

const INDEX = { dataset: { campus: { name: 'Campus', lat: 24.85, lng: 67.26 }, stops: [] }, runs: [], experiments: [], reroute_map: null };
const page = (app, e, s) => { Object.assign(app.ctx, { __e: e, __s: s }); return app.run('experimentBody(__e, __s, { done: __s.runs_done, total: __s.runs_total, left: 0 })'); };

// ---------------------------------------------------------------- 1. false "Limits: none" banner on a real limited run

// cmd_limits writes "limits": "none" on every graph_unlimited row by design (that arm is never limited),
// and cmd_scale writes "none" on every unlimited-setup row. A real systemd run therefore always mixes
// 'systemd' and 'none' rows, and limitsNote() then prints the "say nothing about the free tier" banner.
test('limits pass under systemd: no "Limits: none" banner just because graph_unlimited rows say none', () => {
  const app = loadApp(INDEX);
  const row = (arm, limits) => ({ key: `S1-${arm}-r1`, scenario: 'S1', route: 'J-1', kind: 'synthetic', arm, repeat: 1, status: 'ok',
    judged: true, limits, delay_1s: 10, delay_5s: 10, delay_30s: 10, gap_30s: 0, t_first_s: 0.5, peak_mb: 200 });
  const s = { pass: 'limits', meta: { limits: 'systemd', limits_check: { ok: true, found: { MemoryMax: '512M' } }, machine: { host: 'wsl' } },
    thresholds: { first_plan_s: 5, first_plan_share: 0.95, near_oracle_s: 60, at_30_share: 0.9, memory_mb: 400 },
    verdict: { first_plan: 'pass', at_30: 'pass', memory: 'pass', complete: true }, chips: [{}, {}, {}],
    runs_done: 3, runs_total: 3, runs_failed: 0, cells: [], per_route: {},
    rows: [row('graph_limited', 'systemd'), row('truth_limited', 'systemd'), row('graph_unlimited', 'none')] };
  const html = page(app, { id: 'reroute-limits', kind: 'reroute' }, s);
  assert.ok(!html.includes('Limits: none.'), 'a properly limited run is told its numbers "say nothing about the free tier"');
});

test('scale pass under systemd: unlimited-setup rows (limits none by design) do not trigger the banner', () => {
  const app = loadApp(INDEX);
  const row = (setup, limits, seed) => ({ key: `stops-n4-c1-s${seed}-${setup}`, part: 'stops', setup, status: 'ok', n_stops: 4, per_stop: 1, seed,
    points: 8, r2_cpu_s: 0.01, r3_cpu_s: 0.1, r3_wall_s: 1.0, r3_done: true, r2_minus_r3_s: 0, limits });
  const s = { pass: 'scale', meta: { limits: 'systemd', only: null }, thresholds: { note: 'curves only, no pass or fail' }, verdict: {}, chips: [],
    runs_done: 2, runs_total: 2, runs_failed: 0, cells: [], per_route: {}, rows: [row('limited', 'systemd', 1), row('unlimited', 'none', 1)] };
  const html = page(app, { id: 'reroute-scale', kind: 'reroute' }, s);
  assert.ok(!html.includes('Limits: none.'), 'banner shown on a run whose limited rows were limited');
});

// ---------------------------------------------------------------- 2. "verdicts are final" next to three pending verdicts

test('limits quick: progress tile does not call pending verdicts final', () => {
  const app = loadApp(INDEX);
  const s = summaryOf('reroute-limits-quick');          // truth_limited only: nothing can be judged
  const html = page(app, { id: 'reroute-limits-quick', kind: 'reroute' }, s);
  const pending = (html.match(/<span class="chip">pending<\/span>/g) || []).length;
  assert.equal(pending, 3, 'precondition: three pending verdicts');
  assert.ok(!html.includes('verdicts are final'), 'page says "complete: verdicts are final" while every verdict is pending');
  assert.ok(html.includes('3 verdicts pending'), 'progress tile says the verdicts are pending');
});

// ---------------------------------------------------------------- 3. limits footnote contradicts threshold 6

test('limits verdict list: footnote does not say every threshold is judged only on judged synthetic scenarios', () => {
  const app = loadApp(INDEX);
  const html = page(app, { id: 'reroute-limits-quick', kind: 'reroute' }, summaryOf('reroute-limits-quick'));
  // LOGBOOK 2026-11-17: threshold 6 (memory) is judged on every graph_limited row, unjudged and historical included.
  assert.ok(html.includes('every graph_limited row'), 'precondition: rule 6 wording');
  assert.ok(!/Judged on synthetic scenarios in the judged set[^<]*historical scenarios are reported apart and never pooled/.test(html),
    'footnote claims historical rows are never pooled, but threshold 6 pools every graph_limited row');
});

// ---------------------------------------------------------------- 4. plan map data cached forever

test('plan map: a map file published after the first visit is fetched on the next visit', async () => {
  let fetched = 0;
  const app = loadApp({ ...INDEX, reroute_map: null }, { fetch: url => { if (String(url).includes('reroute_map')) fetched++; else return Promise.reject(new Error('no index in tests')); return Promise.resolve({ ok: true, json: () => ({ points: {}, scenarios: {} }) }); } });
  const holder = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  const v = { querySelector: s => (s === '#pm-card' ? holder : null), contains: () => true };
  const rows = [0, 400, 800].map(l => ({ key: `S-L${l}-main`, scenario: 'S', route: 'J-1', kind: 'synthetic', trigger: 'late', arm: 'main', limit_m: l,
    status: 'ok', plans: { R0: { visit: [1], board_at: [[1, 1]], unserved: [], arrival_s: 10 }, R2: { visit: [1], board_at: [[1, 1]], unserved: [], arrival_s: 10 }, R3: { visit: [1], board_at: [[1, 1]], unserved: [], arrival_s: 10 } } }));
  Object.assign(app.ctx, { __v: v, __s: { pass: 'quality', thresholds: { judged_limit_m: 400 }, rows } });
  app.run("bindPlanMap(__v, { id: 'reroute-quality', kind: 'reroute' }, __s)");       // first visit: no map file yet
  // serve.py rebuilds the site; poll() reloads index.json, which now names the map file
  app.run("D.reroute_map = 'data/reroute_map.json'");
  app.run("bindPlanMap(__v, { id: 'reroute-quality', kind: 'reroute' }, __s)");       // second visit
  await new Promise(r => setTimeout(r, 0));
  assert.equal(fetched, 1, 'the map file is never fetched: planMapData stayed null from the first visit');
  assert.ok(!holder.innerHTML.includes('appears once the scenario file'), 'page still says the scenario file is not built');
});

// ---------------------------------------------------------------- 5. unescaped value in a map tooltip

test('plan map: stop tooltip escapes the student count from the map file', () => {
  const calls = [];
  const layer = (kind, pts, opts) => { const o = { kind, pts, opts, tip: null, bindTooltip(t) { o.tip = t; return o; }, addTo() { calls.push(o); return o; } }; return o; };
  const L = { polyline: (p, o) => layer('polyline', p, o), circle: (p, o) => layer('circle', [p], o), circleMarker: (p, o) => layer('marker', [p], o) };
  const app = loadApp(INDEX, { L });
  const md = { points: { '-1': [24.85, 67.26, 'Campus'], 0: [24.9, 67.0, 'Stop 0'], 1: [24.91, 67.01, 'Stop 1'] } };
  const sc = { closure: 'C', trigger: 'late', circles: [], closed_points: [], position: 0, remaining: [1], candidates: [], students: { 1: '<img src=x onerror=alert(1)>' } };
  const row = { plans: { R0: { visit: [1], board_at: [[1, 1]], unserved: [], arrival_s: 10 } } };
  Object.assign(app.ctx, { __md: md, __sc: sc, __row: row, __layer: { clearLayers() {} } });
  app.run("campusMarker = () => {}; drawPlanMap(__layer, __md, __sc, __row, 'all', () => '#000')");
  const tips = calls.map(c => c.tip).filter(Boolean);
  assert.ok(!tips.some(t => t.includes('<img')), `raw HTML reaches a Leaflet tooltip: ${tips.find(t => t.includes('<img'))}`);
});

// ---------------------------------------------------------------- 6. R3 median over the seeds that happened to finish

// Under the limited setup R3 stops at the 30 s cap (r3_done false). The chart then takes the median of
// only the seeds that finished, labelled "median over seeds", so a size where the slowest seed hit the cap
// is drawn faster than it is (here 1.5 CPU-s although the third seed ran past 3 CPU-s and never finished).
test('rerouting scaling: R3 point is not a median over only the seeds that finished', () => {
  const app = loadApp(INDEX);
  const row = (seed, cpu, done) => ({ key: `stops-n12-c1-s${seed}-limited`, part: 'stops', setup: 'limited', status: 'ok', n_stops: 12, per_stop: 1, seed,
    points: 24, r2_cpu_s: 0.05, r3_ran: true, r3_done: done, r3_cpu_s: cpu, r3_wall_s: cpu * 10, r2_minus_r3_s: done ? 0 : undefined, limits: 'systemd' });
  const four = (seed) => ({ ...row(seed, 0.1, true), key: `stops-n4-c1-s${seed}-limited`, n_stops: 4, points: 8 });
  const s = { pass: 'scale', meta: { limits: 'systemd', only: 'stops' }, thresholds: {}, verdict: {}, chips: [], runs_done: 6, runs_total: 6, runs_failed: 0,
    cells: [], per_route: {}, rows: [four(1), four(2), four(3), row(1, 1.0, true), row(2, 2.0, true), row(3, 3.0, false)] };
  const html = page(app, { id: 'reroute-scale', kind: 'reroute' }, s);
  const tip = (html.match(/<title>R3, 1 candidate per stop: 12 stops, ([^<]*)<\/title>/) || [])[1];
  assert.notEqual(tip, '1.5 CPU-s', 'chart shows the median of the 2 finished seeds as the median over seeds');
  assert.equal(tip, 'at least 2 CPU-s (1 of 3 seeds stopped at the cap)', 'median over every seed, marked as a lower bound');
  assert.ok(html.includes('lower bound too'), 'the caption explains the lower bound');
});
