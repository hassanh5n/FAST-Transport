// The quality page's plan map: scenario picker, legend, arrivals table and what is drawn on the map.
// Loads hub/web/app.js in node:vm with a tiny DOM stub and a stub of the map library (Leaflet's L) that
// records what would be drawn. Rows and map data are small fakes in the formats run_reroute.py and
// build_site.py write; one test also renders the real reroute-quality-quick summary (rows without plans).
//   node --test "research/hub/tests/*.test.mjs"      (from the repository root)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const HUB = join(dirname(fileURLToPath(import.meta.url)), '..');
const RESULTS = join(HUB, '..', 'results');
const plain = x => JSON.parse(JSON.stringify(x));     // arrays made inside the vm context, compared here
const APP = readFileSync(join(HUB, 'web', 'app.js'), 'utf-8');

// A stand-in for Leaflet: every layer it makes is recorded in calls, with its kind, points and options.
function fakeLeaflet(calls) {
  const layer = (kind, pts, opts) => {
    const o = { kind, pts, opts, tip: null, bindTooltip(t) { o.tip = t; return o; }, addTo() { calls.push(o); return o; } };
    return o;
  };
  return {
    polyline: (pts, opts) => layer('polyline', pts, opts), circle: (pt, opts) => layer('circle', [pt], opts),
    circleMarker: (pt, opts) => layer('marker', [pt], opts),
  };
}

function loadApp(index, calls = []) {
  const el = () => ({ innerHTML: '', textContent: '', hidden: true, querySelector: () => null, querySelectorAll: () => [], closest: () => null });
  const els = new Map();
  const get = k => { if (!els.has(k)) els.set(k, el()); return els.get(k); };
  const ctx = {
    console, URL, Blob: class {}, setTimeout, setInterval: () => 0, L: fakeLeaflet(calls),
    document: { querySelector: s => get(s), getElementById: id => get('#' + id), documentElement: {}, activeElement: null },
    window: { addEventListener() {}, scrollY: 0, scrollTo() {} },
    location: { hash: '' }, navigator: {}, getComputedStyle: () => ({ getPropertyValue: () => '' }),
    fetch: () => Promise.reject(new Error('no network in tests')),
  };
  vm.createContext(ctx);
  vm.runInContext(APP, ctx);
  ctx.__index = index;
  vm.runInContext('D = __index; D.stopsByName = {};', ctx);
  return { run: code => vm.runInContext(code, ctx), ctx, calls };
}

const INDEX = { dataset: { campus: { name: 'Campus', lat: 24.85, lng: 67.26 }, stops: [] }, runs: [], experiments: [], reroute_map: 'data/reroute_map.json' };
const E = { id: 'reroute-quality', kind: 'reroute' };

// Main rows as run_reroute.quality_rows writes them, with the toy's numbers (stop 2 walks to stop 1 at 400 and 800 m).
function mainRows(scenario, route = 'Jadoon-R-1') {
  const r0 = { visit: [1, 2], board_at: [[1, 1], [2, 2]], unserved: [], arrival_s: 1350 };
  const walk = { visit: [1], board_at: [[1, 1], [2, 1]], unserved: [], arrival_s: 940 };
  return [0, 400, 800].map(lim => ({
    key: `${scenario}-L${lim}-main`, scenario, route, kind: 'synthetic', trigger: 'late', arm: 'main', limit_m: lim, status: 'ok',
    r0_delay_s: 400, r2_delay_s: lim ? -10 : 400, r3_delay_s: lim ? -10 : 400, r0_walkers: 0, r2_walkers: lim ? 2 : 0, r3_walkers: lim ? 2 : 0,
    baseline_arrival_s: 950, plans: { R0: r0, R2: lim ? walk : r0, R3: lim ? walk : r0 } }));
}
const control = s => ({ key: `${s}-L400-control`, scenario: s, arm: 'control', limit_m: 400, status: 'ok' });
const SUMMARY = { pass: 'quality', thresholds: { judged_limit_m: 400 }, rows: [...mainRows('T-L1-late', 'T-T'), control('T-L1-late'), ...mainRows('Jadoon-R-1-L2-late')] };

// Map data as build_site.reroute_map_data publishes it: only the frozen file's scenarios, never the toy's.
const MD = {
  version: 'reroute-v1',
  points: { '-1': [24.85, 67.26, 'Campus'], 0: [24.9, 67.0, 'Stop 0'], 1: [24.91, 67.01, 'Stop 1'], 2: [24.92, 67.02, 'Stop 2'], 5: [24.95, 67.05, 'Stop 5'] },
  scenarios: { 'Jadoon-R-1-L2-late': { closure: 'Jadoon-R-1-L2', route: 'Jadoon-R-1', kind: 'synthetic', trigger: 'late',
    circles: [[24.915, 67.015, 200]], closed_points: [2], position: 0, remaining: [1, 2], candidates: [5], route_order: [0, 1, 2], students: { 1: 3, 2: 4 } } },
};

function card(app, summary, md, pick) {
  Object.assign(app.ctx, { __s: summary, __md: md, __pick: pick, __e: E });
  return app.run('planMapCard(__e, __s, __md, __pick)');
}

test('picker, legend and arrivals table for a scenario the map data has', () => {
  const app = loadApp(INDEX);
  const html = card(app, SUMMARY, MD, null);
  assert.equal((html.match(/<option /g) || []).length, 2, 'one option per scenario with plans');
  assert.ok(html.includes('<option value="Jadoon-R-1-L2-late" selected>'), 'first scenario picked');
  assert.ok(html.includes('Jadoon-R-1-L2-late (Jadoon-R-1, synthetic, late)'));
  for (const l of [0, 400, 800]) assert.ok(html.includes(`data-l="${l}"`), `limit ${l}`);
  assert.ok(html.includes('<button data-l="400" class="on">'), 'judged limit chosen first');
  for (const m of ['R0: patched published route', 'R2: greedy', 'R3: exact']) assert.ok(html.includes(m), m);
  for (const k of ['students walking to a boarding point', 'closure', 'bus at the trigger', 'remaining stop', 'campus']) assert.ok(html.includes(k), k);
  assert.ok(html.includes('<table id="pm-table"') && html.includes('data-table="pm-table"'), 'table with export buttons');
  assert.ok(html.includes('<td>1,350</td>') && html.includes('<td>940</td>'), 'arrivals of R0 and R2/R3');
  assert.ok(html.includes('<td>400</td>') && html.includes('<td>-10</td>'), 'delays');
  assert.ok(html.includes('1 stop, 2 students'), 'walkers');
  assert.ok(html.includes('<div id="pm-map" class="map">'), 'map slot');
  assert.ok(!/NaN|undefined|Infinity/.test(html));
});

test('a toy scenario, a missing map file and rows without plans each say why there is no map', () => {
  const app = loadApp(INDEX);
  const toy = card(app, SUMMARY, MD, { exp: E.id, scenario: 'T-L1-late', limit: 800 });
  assert.ok(toy.includes('<option value="T-L1-late" selected>') && toy.includes('<button data-l="800" class="on">'));
  assert.ok(toy.includes('T-L1-late is not in the scenario file') && toy.includes('no coordinates'));
  assert.ok(!toy.includes('id="pm-map"') && toy.includes('<table id="pm-table"'), 'table still shown, no map');

  const noFile = loadApp({ ...INDEX, reroute_map: null });
  const none = card(noFile, SUMMARY, null, null);
  assert.ok(none.includes('The map appears once the scenario file (data/scenarios_reroute_v1.json) is built'));
  assert.ok(!none.includes('id="pm-map"'));
  assert.ok(card(app, SUMMARY, undefined, null).includes('Loading the map'), 'while the map file is fetched');

  const old = card(app, { ...SUMMARY, rows: SUMMARY.rows.map(({ plans, ...r }) => r) }, MD, null);
  assert.ok(old.includes('Rerun the pass') && !old.includes('<table') && !old.includes('<select'));
});

test('drawn on the map: closure, R0, R2 and R3 in visit order to campus, walkers dashed, stops and the bus', () => {
  const app = loadApp(INDEX);
  Object.assign(app.ctx, { __md: MD, __row: SUMMARY.rows.find(r => r.key === 'Jadoon-R-1-L2-late-L400-main') });
  const pts = app.run("drawPlanMap({ clearLayers() {} }, __md, __md.scenarios['Jadoon-R-1-L2-late'], __row, 'all', n => n)");
  const lines = app.calls.filter(c => c.kind === 'polyline');
  const paths = lines.filter(c => !c.opts.dashArray), walks = lines.filter(c => c.opts.dashArray);
  assert.equal(paths.length, 3, 'one path per method');
  assert.deepEqual(paths.map(c => c.opts.color), ['--c2', '--c3', '--c1'], 'R0, R2, R3 colours as in the chart');
  assert.deepEqual(plain(paths[0].pts), [[24.9, 67.0], [24.91, 67.01], [24.92, 67.02], [24.85, 67.26]], 'R0: bus, stop 1, stop 2, campus');
  assert.deepEqual(plain(paths[2].pts), [[24.9, 67.0], [24.91, 67.01], [24.85, 67.26]], 'R3 skips stop 2');
  assert.equal(walks.length, 2, 'R2 and R3 each walk stop 2 to stop 1');
  assert.deepEqual(plain(walks[0].pts), [[24.92, 67.02], [24.91, 67.01]]);
  assert.ok(walks[0].tip.includes('Stop 2 walk to Stop 1'));
  assert.equal(app.calls.filter(c => c.kind === 'circle').length, 1, 'closure circle');
  assert.equal(app.calls.find(c => c.kind === 'circle').opts.radius, 200);
  const markers = app.calls.filter(c => c.kind === 'marker');
  assert.ok(markers.some(c => c.tip.startsWith('Bus at Stop 0')), 'bus start');
  assert.ok(markers.some(c => c.tip.includes('Stop 2: 4 students, inside the closure')), 'remaining stop, closed');
  assert.ok(markers.some(c => c.tip === 'Stop 1: 3 students'), 'remaining stop, open');
  assert.ok(markers.some(c => c.tip.includes('Stop 5: boarding point')), 'candidate point');
  assert.ok(markers.some(c => c.tip === 'Campus'), 'campus');
  assert.ok(pts.length > 0, 'points to fit the view to');

  app.calls.length = 0;
  app.run("drawPlanMap({ clearLayers() {} }, __md, __md.scenarios['Jadoon-R-1-L2-late'], __row, 'R3', n => n)");
  assert.equal(app.calls.filter(c => c.kind === 'polyline').length, 2, 'only R3: its path and its walker');
});

test('values from rows are escaped, and bindPlanMap fills the card with no map file', () => {
  const app = loadApp({ ...INDEX, reroute_map: null });
  const bad = '<img src=x onerror=alert(1)>';
  const html = card(app, { ...SUMMARY, rows: mainRows(bad, bad) }, MD, null);
  assert.ok(!html.includes('<img') && html.includes('&lt;img src=x onerror=alert(1)&gt;'));

  const holder = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  app.ctx.__v = { querySelector: s => (s === '#pm-card' ? holder : null), contains: () => true };
  app.ctx.__s = SUMMARY;
  app.run('planMapData = undefined; bindPlanMap(__v, __e, __s)');
  assert.ok(holder.innerHTML.includes('<select id="pm-scen">') && holder.innerHTML.includes('data/scenarios_reroute_v1.json'));
});

test('the real quality page includes the plan map card', () => {
  const app = loadApp(INDEX);
  app.ctx.__s = JSON.parse(readFileSync(join(RESULTS, 'reroute-quality-quick', 'summary.json'), 'utf-8'));
  const html = app.run("qualityExperiment({ id: 'reroute-quality-quick', kind: 'reroute' }, __s, { done: 15, total: 15 })");
  assert.ok(html.includes('id="pm-card"') && html.includes('Plans on a map'));
  const hasPlans = __s => __s.rows.some(r => r.plans);
  if (!hasPlans(app.ctx.__s)) assert.ok(html.includes('Rerun the pass'), 'rows from before plans were stored');
  assert.ok(!/NaN|undefined|Infinity/.test(html));
});
