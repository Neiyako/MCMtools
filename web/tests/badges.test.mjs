// badgeFor 的状态矩阵测试。
//
// 徽标是唯一"必须随处可见"的信息：过期数量、失败的实验、页数超限，都不能只在
// 它所属的屏幕上看到。所以这里把每种状态组合都跑一遍，而不是只测一个正常值。
//
// STATE 是模块级变量，只有 refresh() 会写。测试通过模块导出的
// setStateForTest 注入状态 —— 不复制源码、不做字符串替换，
// 这样测的是真正会跑的那份代码。
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

let fails = 0;
const check = (n, c, e = '') => {
  console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}${e ? ' — ' + e : ''}`);
  if (!c) fails++;
};

/** 每个用例一份独立模块实例，因为 STATE 是模块级的。 */
async function withState(counts, blockers) {
  const dom = new JSDOM(html, {
    url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const win = dom.window;
  win.fetch = (u, o) => nativeFetch(new URL(u, BASE).href, o);
  const mod = await loadPanel(['badgeFor', 'setStateForTest'], win);
  mod.setStateForTest({
    phase: 'build',
    problem: { mode: 'development' },
    counts, steps: [], blockers: blockers || [],
  });
  return mod.badgeFor;
}

const base = { stale_artifacts: 0, experiments: { failed: 0 }, pages: 5, page_budget: 25 };

console.log('=== badgeFor 状态矩阵 ===');

let bf = await withState({ ...base, stale_artifacts: 2 });
check('过期 2 个 -> 警告徽标',
  bf('results').includes('2') && bf('results').includes('过期') && bf('results').includes('pill-warn'),
  bf('results').trim());

bf = await withState({ ...base, stale_artifacts: 0 });
check('过期 0 个 -> 无徽标', bf('results') === '');

bf = await withState({ ...base, experiments: { failed: 1 }, stale_artifacts: 0 });
check('失败 1 个 -> 警告徽标',
  bf('experiments').includes('1') && bf('experiments').includes('失败'),
  bf('experiments').trim());

bf = await withState({ ...base, experiments: { failed: 0 }, stale_artifacts: 0 });
check('失败 0 个 -> 无徽标', bf('experiments') === '');

bf = await withState({ ...base, pages: 30, page_budget: 25 });
check('页数超限 -> 错误徽标',
  bf('paper').includes('30/25') && bf('paper').includes('pill-err'), bf('paper').trim());

bf = await withState({ ...base, pages: 12, page_budget: 25 });
check('页数未超 -> 中性徽标',
  bf('paper').includes('12/25') && bf('paper').includes('pill-muted'), bf('paper').trim());

bf = await withState({ ...base, pages: null });
check('页数为 null -> 不显示页数徽标', bf('paper') === '', `got ${JSON.stringify(bf('paper'))}`);

bf = await withState(base, [{ code: 'X', severity: 'error', message: 'm', action: 'a' }]);
check('有错误 -> 审计显示错误数',
  bf('audit').includes('1') && bf('audit').includes('pill-err'), bf('audit').trim());

bf = await withState(base, [{ code: 'X', severity: 'warning', message: 'm', action: 'a' }]);
check('只有警告 -> 审计不显示徽标', bf('audit') === '');

bf = await withState(base, []);
check('无阻塞项 -> 审计不显示徽标', bf('audit') === '');

// 徽标必须是中文的：这是用户最先看到的信息之一。
const zh = await withState({ ...base, stale_artifacts: 3 });
check('徽标文案是中文', /[\u4e00-\u9fa5]/.test(zh('results')), zh('results').trim());

console.log(fails ? `\n${fails} 个失败` : '\n徽标全部通过');
process.on('exit', cleanupStaged);
process.exit(fails ? 1 : 0);
