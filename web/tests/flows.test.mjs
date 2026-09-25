// Drive the interactive flows through the DOM: these are the paths a user
// actually takes, and the ones where a bug loses work.
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;
window.fetch = (u, o) => fetch(new URL(u, BASE).href, o);
window.setTimeout = setTimeout; window.clearTimeout = clearTimeout;

const p = await loadPanel(['refresh', 'go', 'screenExperiments', 'screenResults',
  'screenPaper', 'screenAudit', 'screenMath', 'screenParams'], window);
const doc = window.document;
const el = doc.getElementById('content');
let fails = 0;
const check = (n, c, e = '') => { console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}${e ? ' — ' + e : ''}`); if (!c) fails++; };
const wait = (ms = 700) => new Promise(r => setTimeout(r, ms));
const text = () => (el.textContent || '').replace(/\s+/g, ' ');

await p.refresh(); await wait(200);

console.log('=== flow 1: run an experiment from the Experiments screen ===');
p.go('experiments'); await wait(500);
const runBtns = el.querySelectorAll('[data-run]');
check('run buttons rendered', runBtns.length > 0, `${runBtns.length} found`);
await runBtns[0].onclick();
await wait(2500);
const toast1 = doc.getElementById('toast');
check('toast 报告了运行结果', !toast1.hidden && /次运行完成/.test(toast1.textContent),
  toast1.textContent.slice(0, 70));
// refresh() replaces #content's innerHTML, so re-query from the document
// rather than holding the element reference captured before the run.
const afterRun = doc.getElementById('content');
check('page re-rendered after the run',
  afterRun.querySelectorAll('[data-run]').length > 0,
  `${afterRun.querySelectorAll('[data-run]').length} run buttons`);
check('run button re-enabled after refresh',
  !afterRun.querySelector('[data-run]').disabled);

console.log('\n=== flow 2: trials modal ===');
p.go('experiments'); await wait(500);
const trialBtn = el.querySelector('[data-trials]');
await trialBtn.onclick(); await wait(800);
const modal = doc.getElementById('modal');
check('modal opened', !modal.hidden);
check('modal lists trial conditions', /beta=/.test(doc.getElementById('modal-body').textContent),
  doc.getElementById('modal-body').textContent.replace(/\s+/g,' ').slice(0, 70));
doc.getElementById('modal').hidden = true;

console.log('\n=== flow 3: refit a parameter -> figure goes stale ===');
// Change gamma via the API, then re-run, then confirm the UI shows it stale.
// 参数现在直接打 /api/params/{name}，不再经过模型层。
const pdata = await (await fetch(BASE + '/api/params')).json();
const gamma = pdata.parameters.find(x => x.name === 'gamma');
const prev = gamma.value;
// 取一个一定不同的值，保证重跑确实会改变结果。
const next = prev === 0.041 ? 0.052 : 0.041;
console.log(`  refit gamma: ${prev} -> ${next}`);
await fetch(BASE + '/api/params/gamma', {
  method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ value: next, source: 'fitted' }),
});
await fetch(BASE + '/api/experiments/EXP-001/run', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
});
await p.refresh(); await wait(300);
p.go('results'); await wait(1200);
const resultsEl = doc.getElementById('content');
check('stale figure is marked in the UI',
  resultsEl.innerHTML.includes('artifact-stale') || /过期/.test(resultsEl.textContent),
  text().slice(0, 60));
check('sidebar badge shows the stale count',
  /过期/.test(doc.getElementById('nav').textContent));

console.log('\n=== flow 4: regenerate from the Results screen ===');
const regenBtn = resultsEl.querySelector('[data-regen]');
check('regenerate button present', !!regenBtn);
await regenBtn.onclick(); await wait(2500);
await p.refresh(); await wait(300);
const staleNow = await (await fetch(BASE + '/api/figures/stale')).json();
check('stale cleared after regenerate',
  staleNow.figures.length === 0 && staleNow.tables.length === 0,
  `figures=${staleNow.figures.length}`);

console.log('\n=== flow 5: the submission gate on the Audit screen ===');
p.go('audit'); await wait(700);
const gate = await (await fetch(BASE + '/api/audit/strict')).json();
const shown = text();
check('gate verdict matches the API',
  gate.ready_to_submit ? shown.includes('可以提交') : shown.includes('请勿提交'),
  shown.slice(0, 40));
check('gate 列出了原因', gate.ready_to_submit || shown.includes('阻塞性警告'));

console.log('\n=== flow 6: toggle a paper section ===');
p.go('paper'); await wait(800);
const cb = el.querySelector('[data-sec]');
check('section toggles rendered', !!cb);
const before = cb.checked;
await (async () => { cb.checked = !before; await cb.onchange(); })();
await wait(2500);
const paper = await (await fetch(BASE + '/api/paper')).json();
const sec = paper.sections.find(s => s.id === cb.getAttribute('data-sec'));
check('toggle persisted through the API', sec.enabled === !before,
  `${cb.getAttribute('data-sec')}: ${before} -> ${sec.enabled}`);
// Restore.
await fetch(BASE + '/api/paper/sections/' + cb.getAttribute('data-sec'), {
  method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ enabled: before }),
});

console.log(fails ? `\n${fails} FAILURE(S)` : '\nALL INTERACTIVE FLOWS PASS');
process.exit(fails ? 1 : 0);

process.on('exit', cleanupStaged);
