// Exercise the panel's pure logic against REAL API payloads.
// Rendering bugs hide in data-shape assumptions, so payloads come from the
// live app rather than being hand-written.
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';

// Payloads come from the live server, so the test binds to the real contract.
const realFetch = globalThis.fetch;
const get = async (p) => {
  const res = await realFetch(BASE + p);
  if (!res.ok) throw new Error(`${p} -> ${res.status}. Is the server running? (mcm serve)`);
  return res.json();
};
// Payloads for the assertions below. The module itself also talks to the
// server, through the jsdom window's fetch.
const state = await get('/api/state');
const figs = await get('/api/figures');
const exps = await get('/api/experiments');
const paper = await get('/api/paper');
const gate = await get('/api/audit/strict');
const mode = await get('/api/mode');


// 直接 import 真实模块。badgeFor 读的是模块内的 STATE，所以用一次真实的
// refresh() 把它填上（走真实服务器），而不是字符串替换注入一个假的。
const { JSDOM } = await import('jsdom');
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
  { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const win = dom.window;
win.fetch = (u, o) => realFetch(new URL(u, BASE).href, o);
const mod = await loadPanel(
  ['refresh', 'go', 'SCREENS', 'GROUPS', 'esc', 'badgeFor', 'findingLabel'],
  win,
);
// 真实的 STATE 由 refresh() 从 /api/state 装填。
await mod.refresh();

let fails = 0;
const check = (name, cond, extra = '') => {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`);
  if (!cond) fails++;
};

console.log('=== phase-driven navigation ===');
for (const ph of ['problem_selection', 'problem_locked', 'build', 'finalize']) {
  const visible = Object.keys(mod.SCREENS).filter(k => mod.SCREENS[k].phases.includes(ph));
  console.log(`  ${ph.padEnd(18)} -> ${visible.join(', ')}`);
}
check('problem_selection hides the build screens',
  !['math', 'params', 'experiments', 'results', 'paper'].some(k => mod.SCREENS[k].phases.includes('problem_selection')));
check('build hides Problems', !mod.SCREENS.problems.phases.includes('build'));
check('finalize keeps Paper and Audit',
  mod.SCREENS.paper.phases.includes('finalize') && mod.SCREENS.audit.phases.includes('finalize'));
check('every phase resolves to a non-empty sidebar',
  ['problem_selection', 'problem_locked', 'build', 'finalize']
    .every(ph => Object.keys(mod.SCREENS).filter(k => mod.SCREENS[k].phases.includes(ph)).length > 0));
check('no screen is orphaned from the sidebar',
  Object.keys(mod.SCREENS).every(k =>
    Object.values(mod.SCREENS).some(v => v.phases.length > 0) &&
    mod.GROUPS.some(([, keys]) => keys.includes(k))));
check('every group is non-empty',
  mod.GROUPS.every(([, keys]) => keys.some(k => mod.SCREENS[k])));
check('every screen belongs to exactly one group',
  Object.keys(mod.SCREENS).every(k => mod.GROUPS.filter(([, keys]) => keys.includes(k)).length === 1));

console.log('\n=== escaping (the panel renders API strings as HTML) ===');
check('script tag neutralised', !mod.esc('<script>alert(1)</script>').includes('<script'));
check('attribute break-out neutralised', !mod.esc('" onload="x').includes('"'));
check('quotes escaped', mod.esc(`"x'`) === '&quot;x&#39;');
check('null renders empty', mod.esc(null) === '');
check('undefined renders empty', mod.esc(undefined) === '');

console.log('\n=== badgeFor against the real /api/state payload ===');
const b = (k) => mod.badgeFor(k);
// The demo project currently has no stale artifacts, so an EMPTY badge is the
// correct output. The populated cases are covered exhaustively in
// badges.test.mjs, which drives badgeFor across a state matrix.
const staleNow = state.counts.stale_artifacts;
check('results badge matches the stale count',
  staleNow ? b('results').includes(`${staleNow} stale`) : b('results') === '',
  `stale=${staleNow} -> ${JSON.stringify(b('results'))}`);
// 页数不能写死：它取决于样例项目**当前有没有构建过 PDF**。
// 测试用的 fixtures 是 examples/demo_pcql，构建产物不入库，
// 所以这里可能没有页数 —— 那不是 bug，是"还没编译"。
// 真正要保证的是：有页数时徽标显示 pages/budget，没有时不显示。
const pagesNow = state.counts.pages;
const budgetNow = state.counts.page_budget;
if (pagesNow != null) {
  check('paper badge shows pages/budget',
    b('paper').includes(`${pagesNow}/${budgetNow}`),
    `state=${pagesNow}/${budgetNow} -> ${JSON.stringify(b('paper'))}`);
} else {
  check('paper badge hidden until a PDF is built', b('paper') === '',
    `未构建时 -> ${JSON.stringify(b('paper'))}`);
}
check('experiments badge hidden when nothing failed', b('experiments') === '');
check('audit badge hidden when no errors', b('audit') === '');
check('unknown key returns empty', b('nope') === '');

console.log('\n=== payload shape assumptions ===');
check('state.counts.experiments is an object', typeof state.counts.experiments === 'object');
check('every step has key/label/status/detail',
  state.steps.every(s => s.key && s.label && s.status && 'detail' in s));
check('step statuses are from the known set',
  state.steps.every(s => ['done', 'partial', 'todo'].includes(s.status)));
check('every blocker has code/severity/message/action',
  state.blockers.every(b => b.code && b.severity && b.message && b.action));
check('blocker severity is error|warning',
  state.blockers.every(b => ['error', 'warning'].includes(b.severity)));
check('counts.pages is numeric or null',
  state.counts.pages === null || typeof state.counts.pages === 'number');

check('figure.bindings is a list', Array.isArray(figs[0].bindings));
check('figure.file is a string (used for the embed URL)', typeof figs[0].file === 'string');
check('figure.referenced_in is a list', Array.isArray(figs[0].referenced_in));

check('experiment.varied is a list', Array.isArray(exps[0].varied));
check('experiment.held_fixed is a list', Array.isArray(exps[0].held_fixed));
check('experiment.status is a string', typeof exps[0].status === 'string');

check('paper.sections is a list', Array.isArray(paper.sections));
check('every section has kind (used for the report_on_ai lookup)',
  paper.sections.every(s => 'kind' in s && 'enabled' in s && 'title' in s));
check('paper.ai_usage present with ai_used', typeof paper.ai_usage.ai_used === 'boolean');

check('gate.ready_to_submit is boolean', typeof gate.ready_to_submit === 'boolean');
check('gate.strict_codes is a non-empty list', Array.isArray(gate.strict_codes) && gate.strict_codes.length > 0);
check('gate.errors and promoted_warnings are lists',
  Array.isArray(gate.errors) && Array.isArray(gate.promoted_warnings));

check('mode.project_mode is a string', typeof mode.project_mode === 'string');
check('mode.blocked_outbound is a list', Array.isArray(mode.blocked_outbound));

console.log(fails ? `\n${fails} FAILURE(S)` : '\nall panel logic checks passed');
process.exit(fails ? 1 : 0);

process.on('exit', cleanupStaged);
