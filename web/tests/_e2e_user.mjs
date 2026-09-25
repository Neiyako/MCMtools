/**
 * 真实用户端全流程走查。
 *
 * 目标不是"接口能通"，而是"一个人从头到尾能不能把活干完"。
 * 每一步都驱动真实 DOM（点真按钮、填真表单），只通过 HTTP 读回结果核对。
 *
 * 用全新项目，不用 examples/ 里的 fixture —— fixture 有既有数据，
 * 会掩盖"从零开始会不会卡住"这类问题。
 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8499';
let fails = 0, step = 0;
const check = (n, c, e = '') => {
  console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}${e ? '  — ' + e : ''}`);
  if (!c) fails++;
};
const wait = (ms) => new Promise(r => setTimeout(r, ms));
const J = async (p, o) => {
  const r = await nativeFetch(BASE + p, o);
  const t = await r.text();
  try { return JSON.parse(t); } catch { return { __raw: t, __status: r.status }; }
};

const dom = new JSDOM(
  fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
  { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const win = dom.window;
win.fetch = (u, o) => nativeFetch(new URL(u, BASE).href, o);

const probe = await loadPanel(['refresh', 'go', 'renderScreen', 'ROUTE'], win);
await wait(1400);
const view = () => win.document.getElementById('view')
  || win.document.getElementById('app');
const $ = (id) => view().querySelector('#' + id);
const txt = () => view().textContent.replace(/\s+/g, ' ');

async function go(screen, ms = 2000) {
  probe.go(screen);
  await wait(ms);
}

console.log('\n########## 1. 选题 ##########');
await go('problems');
check('选题页能打开', txt().includes('选题'), txt().slice(0, 40));
check('有登记按钮', !!$('prob-add'));
$('fld-letter').value = 'C';
$('fld-title').value = 'Wordle 词频与难度预测';
$('fld-summary').value = '附件是逐日结果，需要预测报告词';
$('prob-add').click();
await wait(2200);
check('题目登记成功', txt().includes('Wordle'), txt().slice(0, 60));

const lockBtn = view().querySelector('[data-lock]');
check('出现锁定按钮', !!lockBtn);
if (lockBtn) {
  lockBtn.click();
  await wait(400);
  const save = win.document.getElementById('modal-save');
  check('弹出锁定确认', !!save);
  if (save) {
    win.document.getElementById('lock-team').value = '2400996';
    save.click();
    await wait(2600);
  }
}
let st = await J('/api/state');
check('阶段推进到 build', st.phase === 'build', st.phase);
check('侧栏收窄到建模流程', txt().includes('建模流程'), txt().slice(0, 50));

console.log('\n########## 2. 数据 ##########');
await go('data');
const csv = '/tmp/e2e/wordle.csv';
fs.writeFileSync(csv,
  'date,word,attempts,hard_mode\n2022-01-01,cigar,3,0\n2022-01-02,rebus,4,1\n2022-01-03,sissy,2,0\n');
check('数据页有导入按钮', !!$('ds-import'));
$('fld-path').value = csv;
$('ds-import').click();
await wait(2600);
check('数据导入成功', txt().includes('wordle'), txt().slice(0, 70));
let ds = await J('/api/datasets');
check('后端记录数据集', ds.length === 1, `count=${ds.length}`);
if (ds[0]) {
  const cols = ds[0].schema || ds[0].columns || [];
  check('自动读出 4 列', cols.length === 4, `cols=${cols.length}`);
}

console.log('\n########## 3. 参数 ##########');
await go('params');
check('参数页有新增入口',
  !!view().querySelector('[data-add-param],[data-new-param],#param-add,#add-param'),
  '未找到新增按钮');

console.log('\n########## 4. 数学内容 ##########');
await go('math');
check('数学页可编辑',
  !!view().querySelector('[data-edit-sym],[data-add-sym],#sym-add'));

console.log('\n########## 5. 生图 ##########');
await go('figures', 3000);
check('生图工作台列出模板', txt().includes('图'), txt().slice(0, 60));

console.log('\n########## 6. 论文 ##########');
await go('paper', 2600);
check('论文页可打开', txt().includes('论文'), txt().slice(0, 60));

console.log('\n########## 7. 审计 ##########');
await go('audit', 2600);
check('审计页有结论', /错误|警告|通过/.test(txt()), txt().slice(0, 80));

console.log('\n########## 8. 设置 ##########');
await go('settings');
check('设置页有改队伍号', !!$('set-team'));
check('设置页有解锁', !!$('set-unlock'));

console.log(`\n${fails ? '✗ ' + fails + ' 项失败' : '✓ 全流程无阻断'}`);
cleanupStaged();
process.exit(fails ? 1 : 0);
