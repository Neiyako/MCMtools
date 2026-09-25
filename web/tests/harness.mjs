/**
 * 共享的测试加载器。
 *
 * 面板是原生 ES module（import './strings.js'），所以不能再用 window.eval
 * 把源码当普通脚本跑 —— import 语句在非模块上下文里是语法错误。
 *
 * 这里的做法：把 app.js 复制进 tests/ 并在复制时重写 import 路径指向
 * ../strings.js，然后用动态 import 加载它。这样测的是**真实的源码**，
 * 只有 import 说明符被改（因为复制品换了目录），没有任何逻辑被替换。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const TESTS_DIR = path.dirname(fileURLToPath(import.meta.url));
export const WEB_DIR = path.resolve(TESTS_DIR, '..');

// Node 原生的 fetch，在任何人覆盖 globalThis.fetch 之前抓住。
// 面板模块和测试都通过这里发真实请求，绕开一切拦截。
export const nativeFetch = globalThis.fetch;

let counter = 0;

/**
 * 清掉**其他进程**遗留的临时文件。
 *
 * cleanupStaged 只删自己 PID 的文件，所以被 Ctrl-C 或超时杀掉的那次运行
 * 会把 _staged_*.mjs 留在目录里 —— 实测攒了 91 个、4.6MB。
 * 每次 stageAppModule 顺手扫一遍，孤儿就不会累积。
 */
function sweepOrphanStaged() {
  const mine = `_staged_${process.pid}_`;
  for (const f of fs.readdirSync(TESTS_DIR)) {
    if (!f.startsWith('_staged_') || f.startsWith(mine)) continue;
    // 只删一天前的，避免误删另一个正在并发跑的测试进程的文件
    try {
      const p = path.join(TESTS_DIR, f);
      if (Date.now() - fs.statSync(p).mtimeMs > 24 * 3600 * 1000) fs.unlinkSync(p);
    } catch { /* 忽略 */ }
  }
}

/** 复制 app.js 到 tests/ 下并修正 import，返回临时文件路径。 */
export function stageAppModule() {
  sweepOrphanStaged();
  const src = fs.readFileSync(path.join(WEB_DIR, 'app.js'), 'utf8');
  // 复制品位于 tests/，所以 './strings.js' 要变成 '../strings.js'。
  const rewritten = src.replace(
    /from\s+'(\.\/[^']+)'/g,
    (m, spec) => `from '../${spec.slice(2)}'`,
  );
  const file = path.join(TESTS_DIR, `_staged_${process.pid}_${counter++}.mjs`);
  fs.writeFileSync(file, rewritten);
  return file;
}

/**
 * 加载 app.js，并把内部函数暴露到 globalThis.__probe 以便测试驱动。
 *
 * `names` 是要导出的函数名。做法是在源码的 boot 段前插入一行赋值 ——
 * 不修改任何被测试的逻辑。
 */
export async function loadPanel(names, window) {
  // app.js 用动态 import 加载，因此它跑在 **Node 的 realm** 里，而不是 jsdom 的。
  // 所以 document / location / fetch 等必须挂到 globalThis 上，否则模块顶层
  // 的 `$('#modal').onclick = ...` 会直接抛 ReferenceError。
  if (window) installDomGlobals(window);

  const file = stageAppModule();
  let src = fs.readFileSync(file, 'utf8');

  const expose = `globalThis.__probe = { ${names.join(', ')} };\n`;
  const bootMarker = '(async function boot() {';
  if (!src.includes(bootMarker)) {
    throw new Error('app.js 的 boot 标记没找到；加载器需要更新');
  }
  // 放在 boot 之前：那时所有函数声明都已提升，且 STATE 已可写。
  src = src.replace(
    /window\.addEventListener\('hashchange'/,
    `${expose}\nwindow.addEventListener('hashchange'`,
  );
  fs.writeFileSync(file, src);

  await import(`file://${file}?t=${Date.now()}`);
  return globalThis.__probe;
}

/**
 * 把 jsdom 的 window 装成全局，让模块顶层代码能跑。
 *
 * 只挂 app.js 真正会用到的那些，不是无脑展开整个 window ——
 * 展开会把 Node 自己的 console、process 覆盖掉，反而更难 debug。
 */
export function installDomGlobals(window) {
  // window 本身也要挂：app.js 直接在 window 上注册 hashchange 监听。
  globalThis.window = window;
  const names = [
    'document', 'location', 'navigator', 'HTMLElement', 'Node', 'Event',
    'CustomEvent', 'getComputedStyle', 'requestAnimationFrame',
    'cancelAnimationFrame', 'localStorage', 'history',
  ];
  for (const n of names) {
    if (n in window) {
      try { globalThis[n] = window[n]; } catch { /* 只读的跳过 */ }
    }
  }
  // fetch：模块内的 fetch 调用要走 jsdom 的 window.fetch（测试在那里接好了
  // 真实服务器）。**必须在覆盖 globalThis.fetch 之前抓住 Node 原生的 fetch**，
  // 否则 window.fetch 里调用的 fetch 就是 globalThis.fetch，直接无限递归。
  // 模块里的 fetch('/api/state') 要走真实服务器。一律用抓好的 nativeFetch，
  // 不经过 window.fetch，从根本上避免"自己调自己"的递归。
  globalThis.fetch = (url, opts) => {
    const abs = typeof url === 'string' && /^https?:\/\//.test(url)
      ? url
      : new URL(url, window.location.href).href;
    return nativeFetch(abs, opts);
  };
}

/** 删除本次进程产生的临时文件。 */
export function cleanupStaged() {
  for (const f of fs.readdirSync(TESTS_DIR)) {
    if (f.startsWith(`_staged_${process.pid}_`)) {
      try { fs.unlinkSync(path.join(TESTS_DIR, f)); } catch { /* 忽略 */ }
    }
  }
}
