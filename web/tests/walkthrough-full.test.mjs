/**
 * 全流程走查：从空项目一直到出 PDF。
 *
 * 这是一次真实用户端测试固化下来的。为什么值得留：
 * 单独测每个页面都过，不代表连起来能干活 —— 实测就撞到过
 * "选题页没有锁定按钮"和"实验页没有新建入口"两个阻断，
 * 而后端接口一直是好的。用户卡住的地方在**页面的可达性**上，
 * 只有把整条路走一遍才看得见。
 *
 * 用全新项目，不用 examples/ 里的 fixture：fixture 有既有数据，
 * 会掩盖"从零开始会不会卡住"。
 *
 * 不注册进 run.mjs：它需要一个**空项目**，而 run.mjs 共用的
 * 服务器跑在 demo_pcql 上。单独跑：
 *
 *   ./start /tmp/某个空目录 --port 8499
 *   BASE=http://127.0.0.1:8499 node web/tests/walkthrough-full.test.mjs
 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';
const BASE = process.env.BASE || 'http://127.0.0.1:8499';
let fails = 0;
const check = (n,c,e='') => { console.log(`  ${c?'PASS':'FAIL'}  ${n}${e?'  — '+e:''}`); if(!c) fails++; };
const wait = ms => new Promise(r=>setTimeout(r,ms));
const J = async (p,o) => { const r = await nativeFetch(BASE+p,o); const t = await r.text();
  try { return JSON.parse(t); } catch { return {__raw:t.slice(0,150), __s:r.status}; } };
const post = (p,d) => J(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});

const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'),
  { url: BASE+'/', runScripts:'outside-only', pretendToBeVisual:true });
const win = dom.window;
win.fetch = (u,o) => nativeFetch(new URL(u,BASE).href, o);
const probe = await loadPanel(['refresh','go'], win);
await wait(1400);
const view = () => win.document.getElementById('view') || win.document.getElementById('app');
const $ = id => view().querySelector('#'+id);
const txt = () => view().textContent.replace(/\s+/g,' ');

console.log('=== 1. 选题 ===');
probe.go('problems'); await wait(2000);
$('fld-letter').value = 'C'; $('fld-title').value = 'Wordle';
$('prob-add').click(); await wait(2000);
// 已经锁过题目的项目（同一个项目跑第二遍）不会再有锁定按钮，
// 那不是失败，是"这步没必要做了"。所以只在还没锁时要求按钮存在。
const alreadyLocked = (await J('/api/state')).phase !== 'problem_selection';
const lockBtn = view().querySelector('[data-lock]');
if (!alreadyLocked) {
  check('列表里出现锁定按钮', !!lockBtn);
}
if (lockBtn) {
  lockBtn.click(); await wait(400);
  win.document.getElementById('modal-save').click(); await wait(2500);
}
check('锁定题目 → build', (await J('/api/state')).phase === 'build');

console.log('\n=== 2. 数据 ===');
probe.go('data'); await wait(2000);
fs.writeFileSync('/tmp/full/d.csv','date,n,hard\n2022-01-01,3,0\n2022-01-02,4,1\n');
$('fld-path').value = '/tmp/full/d.csv';
$('ds-import').click(); await wait(2500);
check('导入数据', (await J('/api/datasets')).length === 1);

console.log('\n=== 3. 数学 ===');
probe.go('math'); await wait(2000);
$('add-sym').click(); await wait(400);
win.document.getElementById('fld-glyph').value = 'N';
win.document.getElementById('fld-meaning').value = '总天数';
win.document.getElementById('modal-save').click(); await wait(2000);
check('加符号', ((await J('/api/math')).symbols||[]).length === 1);

console.log('\n=== 4. 参数 ===');
probe.go('params'); await wait(2000);
$('add-param').click(); await wait(400);
const pi = view().querySelector('#fld-name') || win.document.getElementById('modal').querySelector('#fld-name');
if (pi) { pi.value = 'beta'; win.document.getElementById('modal-save').click(); await wait(2000); }
check('参数页可用', !!$('add-param'));

console.log('\n=== 5. 实验（套模板）===');
probe.go('experiments'); await wait(2800);
$('fld-template_id').value = 'exp.sensitivity_oat';
$('fld-label').value = '权重敏感性';
view().querySelector('.vary-row [data-v-name]').value = 'w';
view().querySelector('.vary-row [data-v-values]').value = '0.1, 0.5';
$('exp-create').click(); await wait(2600);
// 按**标签**认自己刚建的那个，不按数量。
// 早先写的是 exps.length === 1，只在空项目上成立；项目里已有实验时
// 就误报失败 —— 而那跟"能不能建"没关系。
const exps = await J('/api/experiments');
const mine = exps.find(e => e.label === '权重敏感性');
check('建出实验', !!mine, `共 ${exps.length} 个，找到=${!!mine}`);
check('类型正确', mine?.kind === 'sensitivity_oat', mine?.kind);
check('变动参数存下来了', (mine?.varied || []).length === 1,
  JSON.stringify(mine?.varied));
check('展开 2 次试验',
  mine ? (await J(`/api/experiments/${mine.id}/trials`)).length === 2 : false);

console.log('\n=== 6. 论文 ===');
probe.go('paper'); await wait(2600);
check('论文页有构建', !!$('build-btn'));
$('build-btn').click(); await wait(9000);
check('构建后显示页数', /页/.test(txt()), txt().slice(0,90));

console.log('\n=== 7. 审计 ===');
probe.go('audit'); await wait(2600);
check('审计给出结论', /错误|警告|通过/.test(txt()));
// 审计结论要从**页面**读，不是从接口。
// 早先这里写的是 J('/api/audit')，那个路径其实是 POST，
// 返回 "Method Not Allowed" 却因为对象非空而判为通过 —— 一条假绿。
const auditBody = txt();
check('审计页列出了问题或明确说没问题',
  /个错误|个警告|没有发现问题|可以交给人审阅/.test(auditBody),
  auditBody.slice(-90));

console.log('\n=== 8. 设置/解锁 ===');
probe.go('settings'); await wait(2000);
check('有解锁按钮', !!$('set-unlock'));

console.log(fails ? `\n✗ ${fails} 项失败` : '\n✓ 全流程走通，无阻断');
cleanupStaged();
process.exit(fails?1:0);
