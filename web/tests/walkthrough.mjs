// 像用户一样把每个屏幕走一遍，检查：有没有东西挡在页面上、有没有报错、
// 内容是否真的渲染出来了。
//
// 这个脚本是"我自己先用一遍"的固化版本 —— 之前只验证了 API 和 HTML 源码，
// 结果漏掉了弹窗层常驻遮挡整个界面这种"能渲染但不该显示"的 bug。
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8420';
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
  { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;
const doc = window.document;

window.fetch = (u, o) => nativeFetch(new URL(u, BASE).href, o);

// 注入真实样式，才能算出 display 的级联结果
const style = doc.createElement('style');
style.textContent = fs.readFileSync(new URL('../app.css', import.meta.url), 'utf8');
doc.head.appendChild(style);
// jsdom 不带浏览器默认样式表，手工补上 [hidden] 的 UA 规则，
// 否则测不出"作者 display 盖掉 hidden"这个问题。
const ua = doc.createElement('style');
ua.textContent = '[hidden] { display: none; }';
doc.head.insertBefore(ua, style);

const p = await loadPanel(['refresh', 'go', 'SCREENS'], window);
await p.refresh();
await new Promise(r => setTimeout(r, 600));

/** 覆盖层（弹窗、提示条）是否正挡着页面。 */
function obstructions() {
  return ['modal', 'toast'].filter(id => {
    const el = doc.getElementById(id);
    if (!el) return false;
    if (!el.hasAttribute('hidden')) return true;
    // 即使有 hidden，也要确认它真的不显示（这正是那个 bug）
    return window.getComputedStyle(el).display !== 'none';
  });
}

const screens = ['overview', 'data', 'math', 'params', 'experiments', 'runs', 'figures', 'results',
                 'paper', 'audit', 'problems', 'settings'];

console.log('屏幕'.padEnd(13) + '遮挡'.padEnd(8) + '节点'.padStart(5) +
            '字符'.padStart(7) + '  标题');
console.log('─'.repeat(60));

let bad = 0;
for (const s of screens) {
  p.go(s);
  await new Promise(r => setTimeout(r, 950));
  const content = doc.getElementById('content');
  const block = obstructions();
  const txt = (content.textContent || '').replace(/\s+/g, ' ').trim();
  const ok = !block.length && txt.length > 10 && !/加载失败|连不上/.test(txt);
  if (!ok) bad++;
  console.log(
    s.padEnd(13),
    (block.length ? '❌' + block.join(',') : '✓无').padEnd(7),
    String(content.querySelectorAll('*').length).padStart(5),
    String(txt.length).padStart(6),
    '  ' + doc.getElementById('screen-title').textContent);
}

console.log('─'.repeat(60));
console.log(bad ? `❌ ${bad} 个屏幕有问题` : '✓ 全部屏幕正常，无遮挡');
process.on('exit', cleanupStaged);
process.on('uncaughtException', e => { cleanupStaged(); throw e; });
process.exit(bad ? 1 : 0);
