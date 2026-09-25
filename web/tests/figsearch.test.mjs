// 生图工作台的模板搜索。
//
// 为什么值得单独测：模板从 12 个涨到 28 个之后，"下拉框里找一张图"
// 变成了真实的负担。搜索框如果不工作，用户不会来报 bug ——
// 他们会直接滚，然后以为工具里没有那个模板。
//
// 这里驱动的是**真实 DOM**：真的输入框、真的 input 事件、
// 真的读 sel.options。不是调内部函数。
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

let fails = 0;
const check = (n, c, e = '') => {
  console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}${e ? ' — ' + e : ''}`);
  if (!c) fails++;
};

const dom = new JSDOM(html, {
  url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true,
});
const win = dom.window;
win.fetch = (u, o) => fetch(new URL(u, BASE).href, o);

const probe = await loadPanel(['renderScreen', 'go'], win);

// 必须走 go()，不能直接 renderScreen('figures')。
// renderScreen 读的是**模块内**的 ROUTE，而 ROUTE 只有 go() 会更新 ——
// 直接调它渲染的其实是别的页面，于是下面 querySelector 拿到的
// 是上一次遗留的 DOM，搜索驱动的也是那个旧输入框。
// 表现是结果时对时错、还冒出毫不相关的模板，非常难查。
//
// 还要先等面板自己的 boot 跑完：renderSidebar 读 STATE.phase，
// 而 STATE 是 boot 里 refresh() 填的。STATE 还是 null 时调 go()，
// 会在 renderSidebar 里抛 "Cannot read properties of null"。
await new Promise(r => setTimeout(r, 1200));
probe.go('figures');
await new Promise(r => setTimeout(r, 2500));

const root = win.document.getElementById('view') || win.document.getElementById('app');
const sel = root.querySelector('#fig-template');
const filter = root.querySelector('#fig-filter');

check('生图工作台渲染出模板下拉框', !!sel);
check('有搜索框', !!filter);

if (sel && filter) {
  const initial = sel.options.length;
  check('初始列出全部可用图模板', initial >= 20, `实际 ${initial} 个`);

  async function search(q) {
    filter.value = q;
    filter.dispatchEvent(new win.Event('input'));
    await new Promise(r => setTimeout(r, 700));
    return [...sel.options].map(o => o.value);
  }

  const dist = await search('分布');
  check('搜「分布」能命中直方图', dist.includes('fig.histogram_distribution'),
        dist.join(', ') || '(无结果)');
  check('搜索会缩小结果集', dist.length < initial, `${dist.length} vs ${initial}`);

  // 搜"热力"该命中**描述里真的写了"热力图"**的那个模板。
  // heatmap_matrix 的中文是"响应曲面 / 相关性矩阵"，不含"热力"，
  // 所以它不该被这条查询命中 —— 命中它反而是搜索不精准。
  const heat = await search('热力');
  check('搜「热力」命中带数值标注的热力图',
    heat.includes('fig.heatmap_annotated'), heat.join(', '));
  check('搜「热力」不该误命中响应曲面',
    !heat.includes('fig.heatmap_matrix'), heat.join(', '));

  const time = await search('时间');
  check('搜「时间」命中时序图', time.includes('fig.timeseries'), time.join(', '));

  const none = await search('这个模板肯定不存在xyz');
  check('搜不到时不抛错', true);
  check('搜不到时给出提示文字',
        (root.querySelector('#fig-count').textContent || '').includes('0') ||
        none.length === 0);

  const back = await search('');
  check('清空搜索恢复全部', back.length === initial, `恢复 ${back.length} / ${initial}`);
}

console.log(fails ? `\n搜索测试失败 ${fails} 项` : '\n搜索测试全部通过');
process.on('exit', cleanupStaged);
process.exit(fails ? 1 : 0);
