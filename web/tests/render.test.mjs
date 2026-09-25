// Render EVERY screen in a real DOM against the LIVE server.
// This is the test that matters: it executes the templates with real payloads
// and fails on any exception or empty render.
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;

// A real fetch against the live server.
window.fetch = (url, opts) => nativeFetch(new URL(url, BASE).href, opts);
window.setTimeout = setTimeout; window.clearTimeout = clearTimeout;
// <embed> is not implemented in jsdom; stub it so it does not throw.
window.HTMLCanvasElement && Object.defineProperty(window.HTMLCanvasElement.prototype, 'getContext', { value: () => null });

let errors = [];
window.addEventListener('error', e => errors.push('window error: ' + e.message));

const probe = await loadPanel(['renderScreen', 'go', 'refresh', 'SCREENS',
  'screenOverview', 'screenMath', 'screenParams', 'screenFigures', 'screenExperiments', 'screenResults',
  'screenPaper', 'screenAudit', 'screenSettings', 'screenData', 'screenProblems'], window);


// Let the module's own top-level code settle, then populate STATE the way the
// real boot sequence does (refresh() -> renderSidebar -> renderScreen).
await new Promise(r => setTimeout(r, 200));
await probe.refresh().catch(() => {});
await new Promise(r => setTimeout(r, 200));

const screens = ['overview', 'data', 'math', 'params', 'experiments', 'runs', 'figures', 'results', 'paper', 'audit', 'problems', 'settings'];
let fails = 0;

console.log('=== rendering every screen in a real DOM ===');
for (const s of screens) {
  const el = window.document.getElementById('content');
  el.innerHTML = '';
  let err = null;
  try {
    await probe[s === 'overview' ? 'screenOverview'
      : s === 'data' ? 'screenData'
      : s === 'figures' ? 'screenFigures'
      : s === 'params' ? 'screenParams'
      : s === 'math' ? 'screenMath'
      : s === 'experiments' ? 'screenExperiments'
      : s === 'results' ? 'screenResults'
      : s === 'paper' ? 'screenPaper'
      : s === 'audit' ? 'screenAudit'
      : s === 'problems' ? 'screenProblems'
      : 'screenSettings'](el);
  } catch (e) { err = e; }

  const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
  const nodes = el.querySelectorAll('*').length;
  const ok = !err && text.length > 20;
  if (!ok) fails++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${s.padEnd(12)} ${String(nodes).padStart(4)} nodes, ${String(text.length).padStart(5)} chars` +
    (err ? `  ERROR: ${err.message}` : ''));
  if (ok) console.log(`         "${text.slice(0, 88)}…"`);
}

// Spot-check that real data reached the DOM.
const el = window.document.getElementById('content');
await probe.screenResults(el);
const resHtml = el.innerHTML;
console.log('\n=== content assertions ===');
const assert = (n, c) => { console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}`); if (!c) fails++; };

assert('Results embeds the figure PDF endpoint', resHtml.includes('/api/figures/FIG-001/file'));
assert('Results shows the figure caption', resHtml.includes('Sensitivity of peak participation'));

await probe.screenPaper(el);
const paperHtml = el.innerHTML;
assert('Paper shows the page budget', paperHtml.includes('5') && paperHtml.includes('25'));
assert('Paper lists sections', paperHtml.includes('Introduction'));
assert('Paper 显示 AI 披露状态', /已启用|已停用|缺失/.test(paperHtml));
assert('Paper has a Build button',
  window.document.getElementById('topbar-actions').innerHTML.includes('build-btn'));

await probe.screenAudit(el);
const auditHtml = el.innerHTML;
assert('Audit 渲染出门禁结论', /可以提交|请勿提交/.test(auditHtml));
assert('Audit lists strict codes', auditHtml.includes('FIG_STALE'));

await probe.screenOverview(el);
const ovHtml = el.innerHTML;
assert('Overview 渲染流程步骤', ovHtml.includes('已锁定题目'));
assert('Overview 渲染待处理问题', ovHtml.includes('blocker-') || ovHtml.includes('没有待处理问题'));

await probe.screenSettings(el);
assert('Settings 显示运行模式', /开发模式|竞赛模式/.test(el.textContent));

console.log('\n=== navigation ===');
const nav = window.document.getElementById('nav');
console.log(`  sidebar items rendered: ${nav.querySelectorAll('.nav-item').length}`);
assert('sidebar built from phase', nav.querySelectorAll('.nav-item').length >= 8);

if (errors.length) { console.log('\nwindow errors:'); errors.forEach(e => console.log('  ' + e)); fails += errors.length; }
console.log(fails ? `\n${fails} FAILURE(S)` : '\nALL SCREENS RENDER');
process.exit(fails ? 1 : 0);

process.on('exit', cleanupStaged);

// ---------------------------------------------------------------- 覆盖层
// 曾经有一个真实的 bug：弹窗层 .modal-backdrop 设了 display:flex，把 HTML
// 的 hidden 属性盖掉了（两者特异度相同，作者样式在 UA 样式表之后），
// 结果一进页面就有一条白条挡在正中。这类 bug 渲染测试抓不到 ——
// 元素确实"渲染"了，只是不该显示。
//
// 所以单独检查：**带 display 的覆盖层必须被 [hidden] 规则压住。**
const panelCss = fs.readFileSync(new URL('../app.css', import.meta.url), 'utf8');
const panelHtml = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

assert('app.css 定义了 [hidden] 兜底规则',
  /\[hidden\]\s*\{[^}]*display:\s*none\s*!important/.test(panelCss));

// 找出所有"用 hidden 控制"且"自己设了 display"的覆盖层
const hiddenTags = [...panelHtml.matchAll(/<[^>]*\bhidden\b[^>]*>/g)].map(m => m[0]);
const risky = [];
for (const tag of hiddenTags) {
  const m = tag.match(/(?:id|class)="([^"]+)"/);
  if (!m) continue;
  for (const token of m[1].split(/\s+/)) {
    const rule = new RegExp(`\\.${token}\\s*\\{([^}]*)\\}`).exec(panelCss);
    if (rule && /display:\s*(?!none)/.test(rule[1])) risky.push(`.${token}`);
  }
}
assert('没有覆盖层能绕过 [hidden]（有兜底规则时必然成立）',
  risky.length === 0 || /\[hidden\]\s*\{[^}]*!important/.test(panelCss),
  risky.length ? `设了 display 的覆盖层: ${risky.join(', ')}` : '无');
