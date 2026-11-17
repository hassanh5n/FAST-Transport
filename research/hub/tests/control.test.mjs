// Run & publish view: where jobs run (WSL or this PC) and which experiments are greyed out without WSL.
// Loads hub/web/app.js in node:vm with a tiny DOM stub and the real data/index.json from build_site.py.
//   node --test research/hub/tests/
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

function buildIndex() {
  const venv = join(RESEARCH, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const py = existsSync(venv) ? venv : 'python';
  const out = mkdtempSync(join(tmpdir(), 'hub-site-'));
  const r = spawnSync(py, [join(HUB, 'build_site.py'), '--out', out], { cwd: RESEARCH, encoding: 'utf-8' });
  assert.equal(r.status, 0, r.stderr);
  const index = JSON.parse(readFileSync(join(out, 'data', 'index.json'), 'utf-8'));
  rmSync(out, { recursive: true, force: true });
  return index;
}

function loadApp() {
  const els = new Map();
  const el = () => ({ innerHTML: '', textContent: '', hidden: true, disabled: false, onclick: null,
    querySelectorAll: () => [], closest: () => null, focus() {} });
  const document = { querySelector: s => { if (!els.has(s)) els.set(s, el()); return els.get(s); }, activeElement: null,
    getElementById: () => null };
  const ctx = vm.createContext({
    document, window: { addEventListener() {}, scrollY: 0, scrollTo() {} }, location: { hash: '' },
    fetch: () => Promise.reject(new Error('no server in tests')), alert() {}, confirm: () => false,
    setInterval() {}, console,
  });
  vm.runInContext(readFileSync(join(HUB, 'web', 'app.js'), 'utf-8'), ctx, { filename: 'app.js' });
  return { ctx, els, run: code => vm.runInContext(code, ctx) };
}

const INDEX = buildIndex();
const ENV = {
  native: { checked_at: '2026-11-18T10:00:00+00:00', wsl: false, venv: true, ortools: '9.15.6755', limits: null, runner: 'native' },
  wsl: { checked_at: '2026-11-18T10:00:00+00:00', wsl: true, venv: true, ortools: '9.15.6755', limits: true, runner: 'wsl' },
};

function render(env, job = { state: 'idle' }, extra = {}) {
  const app = loadApp();
  app.ctx.__index = INDEX;
  app.ctx.__status = { local: true, env, job, git: { changes: 0, ahead: 0 }, schedule: {}, wsl_busy: false, ...extra };
  app.run(`D = __index; LOCAL = true; STATUS = __status; PAGE = 'control'; viewControl(document.querySelector('#view'));`);
  return app;
}

// One experiment's block in the jobs list, from its title to the next block.
function block(html, title) {
  const i = html.indexOf(`<strong>${title}</strong>`);
  assert.ok(i >= 0, `no block for ${title}`);
  const j = html.indexOf('<div class="item"', i);
  return html.slice(html.lastIndexOf('<div class="item"', i), j < 0 ? undefined : j);
}

test('without WSL the page says jobs run on this PC and greys out the needs-linux experiments', () => {
  const { els } = render(ENV.native);
  assert.match(els.get('#where').textContent, /run on this PC \(no WSL\)/);
  assert.match(els.get('#env').innerHTML, /research\/\.venv/);
  const jobs = els.get('#jobs').innerHTML;
  const linux = INDEX.experiments.filter(e => e.needs === 'linux');
  assert.ok(linux.length >= 4);
  for (const e of linux) {
    const b = block(jobs, e.title);
    assert.match(b, /opacity:\.65/);
    assert.match(b, /needs WSL/);
    assert.match(b, new RegExp(`data-start="${e.id}" disabled`));
    assert.match(b, new RegExp(`data-sched="${e.id}" disabled`));
  }
  const b = block(jobs, INDEX.experiments.find(e => e.id === 'optimizer-scale-quick').title);
  assert.doesNotMatch(b, /needs WSL|disabled/);
});

test('with WSL nothing is greyed out and the text is the WSL one', () => {
  const { els } = render(ENV.wsl);
  assert.match(els.get('#where').textContent, /runs in WSL/);
  const jobs = els.get('#jobs').innerHTML;
  assert.doesNotMatch(jobs, /<span class="chip">needs WSL<\/span>|opacity:\.65|disabled/);
  assert.match(els.get('#env').innerHTML, /~\/fc-research-venv/);
});

test('without WSL and without research/.venv the Install button shows', () => {
  const { els } = render({ ...ENV.native, venv: false, ortools: null, message: 'not set up' });
  assert.match(els.get('#env').innerHTML, /id="inst"/);
  assert.doesNotMatch(render(ENV.native).els.get('#env').innerHTML, /id="inst"/);
});

test('the strip names this PC for a run started outside the hub', () => {
  const app = render(ENV.native, { state: 'idle' }, { wsl_busy: true });
  app.run('renderStrip()');
  assert.match(app.els.get('#strip').innerHTML, /running on this PC/);
  const w = render(ENV.wsl, { state: 'idle' }, { wsl_busy: true });
  w.run('renderStrip()');
  assert.match(w.els.get('#strip').innerHTML, /running in WSL/);
});

test('a running native job shows its log with the runner line', () => {
  const job = { state: 'running', experiment: 'optimizer-scale-quick', title: 'Optimizer scaling pipeline test',
    started_at: '2026-11-18T10:00:00+00:00', log_tail: ['Runs on this PC (no WSL): python.exe -u run_scale.py <x>'], runner: 'native' };
  const { els } = render(ENV.native, job);
  assert.match(els.get('#jobs').innerHTML, /Runs on this PC \(no WSL\): python\.exe -u run_scale\.py &lt;x&gt;/);
});
