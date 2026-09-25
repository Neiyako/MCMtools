// 选题页必须**真的能锁定题目**。
//
// 这一页曾经是个死胡同：只显示"有没有锁定"，既列不出题目、也没法
// 新建或锁定。后端一直有 POST /api/project/lock —— 缺的是界面。
// 用户第一步就卡死，而且页面看起来"正常渲染了"，所以只测渲染
// 是查不出来的。这里驱动真实 DOM，真的点按钮。
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8455';
let fails = 0;
const check = (n, c, e = '') => {
  console.log(`  ${c ? 'PASS' : 'FAIL'}  ${n}${e ? ' — ' + e : ''}`);
  if (!c) fails++;
};
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const dom = new JSDOM(
  fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'),
  { url: BASE + '/', runScripts: 'outside-only', pretendToBeVisual: true });
const win = dom.window;
win.fetch = (u, o) => nativeFetch(new URL(u, BASE).href, o);

const probe = await loadPanel(['refresh', 'go', 'renderScreen'], win);
await wait(1200);

// 先记下 fixture 的原状，测完还原
const projBefore = await (await nativeFetch(BASE + '/api/project')).json();
const original = {
  locked_problem_id: projBefore.locked_problem_id,
  team_number: projBefore.team_control_number,
};
let created = null;
probe.go('problems');
await wait(1800);

const root = win.document.getElementById('view')
  || win.document.getElementById('app');
const $ = (id) => root.querySelector('#' + id);

console.log('=== 选题页有可操作的入口 ===');
// 这一条是核心：页面必须提供"行动"，不能只是"展示"。
check('有登记题目的按钮', !!$('prob-add'));
check('有题号输入框', !!$('fld-letter'));
check('有标题输入框', !!$('fld-title'));

console.log('\n=== 登记一道题目 ===');
const id = 'PROB-ZZ' + Date.now().toString().slice(-4);
$('fld-letter').value = id.slice(-2);
$('fld-title').value = `面板测试题 ${id}`;
$('prob-add').click();
await wait(2200);
created = id;
check('登记后出现在列表里',
  root.textContent.includes(`面板测试题 ${id}`),
  root.textContent.replace(/\s+/g, ' ').slice(0, 50));

console.log('\n=== 能锁定 ===');
const lockBtn = root.querySelector('[data-lock]');
check('列表里出现锁定按钮', !!lockBtn);
if (lockBtn) {
  lockBtn.click();
  await wait(400);
  const save = win.document.getElementById('modal-save');
  check('弹出锁定确认框', !!save);
  if (save) {
    save.click();
    await wait(2500);
    const st = await (await nativeFetch(BASE + '/api/state')).json();
    check('锁定后 phase 变成 build', st.phase === 'build', st.phase);
    check('后端记住了锁定的题', !!st.problem.id, JSON.stringify(st.problem));
    check('页面显示已锁定', root.textContent.includes('已锁定'));
  }
}

// 收尾：把 fixture 还原。
// 这个项目被其他面板测试共用，改动了 phase 和锁定题号会影响它们 ——
// 实测会把 locked_problem_id 从 PROB-2023-C 改成测试用的题。
if (original.locked_problem_id) {
  await nativeFetch(BASE + '/api/project/lock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      problem_id: original.locked_problem_id,
      team_number: original.team_number,
    }),
  });
}
// 删掉所有由测试产生的题目。
// 只记 "最后一个 id" 是不够的：测试跑多次就会累积，
// 而且中途失败会漏掉前面建的。统一按前缀扫一遍更稳。
const after = await (await nativeFetch(BASE + '/api/problems')).json();
for (const pr of after) {
  if (String(pr.title || '').startsWith('面板测试题')) {
    await nativeFetch(BASE + '/api/problems/' + pr.id, { method: 'DELETE' });
  }
}

console.log('\n=== 设置页：承诺的入口要真的存在 ===');
// 选题页的提示说"之后也能在「设置」里改" —— 那就必须真能改。
// 说了却做不到，和没有入口一样糟。
probe.go('settings');
await wait(1800);
const sroot = win.document.getElementById('view')
  || win.document.getElementById('app');
check('设置页有「改队伍号」按钮', !!sroot.querySelector('#set-team'));
check('已锁定时有「解锁」按钮', !!sroot.querySelector('#set-unlock'));

const teamBefore = (await (await nativeFetch(BASE + '/api/project')).json())
  .team_control_number;
const teamBtn = sroot.querySelector('#set-team');
if (teamBtn) {
  teamBtn.click();
  await wait(400);
  const inp = win.document.getElementById('team-input');
  check('弹出队伍号编辑框', !!inp);
  if (inp) {
    inp.value = '8888888';
    win.document.getElementById('modal-save').click();
    await wait(2200);
    const after = await (await nativeFetch(BASE + '/api/project')).json();
    check('队伍号真的改了', after.team_control_number === '8888888',
      after.team_control_number);
    await nativeFetch(BASE + '/api/project', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_control_number: teamBefore }),
    });
  }
}

console.log(fails ? `\n选题测试失败 ${fails} 项` : '\n选题测试全部通过');
process.on('exit', cleanupStaged);
process.exit(fails ? 1 : 0);
