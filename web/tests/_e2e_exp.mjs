import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';
const BASE = process.env.BASE || 'http://127.0.0.1:8499';
let fails = 0;
const check = (n,c,e='') => { console.log(`  ${c?'PASS':'FAIL'}  ${n}${e?'  — '+e:''}`); if(!c) fails++; };
const wait = ms => new Promise(r=>setTimeout(r,ms));
const J = async (p,o) => JSON.parse(await (await nativeFetch(BASE+p,o)).text());

const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'),
  { url: BASE+'/', runScripts:'outside-only', pretendToBeVisual:true });
const win = dom.window;
win.fetch = (u,o) => nativeFetch(new URL(u,BASE).href, o);
const probe = await loadPanel(['refresh','go'], win);
await wait(1400);
probe.go('experiments'); await wait(2400);
const view = () => win.document.getElementById('view') || win.document.getElementById('app');
const $ = id => view().querySelector('#'+id);
const txt = () => view().textContent.replace(/\s+/g,' ');

check('空实验页给出可操作入口', !!$('exp-create'), txt().slice(0,60));
check('有变动参数按钮', !!$('exp-add-vary'));

// 填一个真实的敏感性实验
$('fld-label').value = '硬模式权重敏感性';
$('fld-kind').value = 'sensitivity_oat';
$('fld-motivation').value = '验证权重取值对预测精度的影响';
const row = view().querySelector('.vary-row');
row.querySelector('[data-v-name]').value = 'hard_mode_weight';
row.querySelector('[data-v-values]').value = '0.1, 0.5, 1.0';
$('exp-create').click();
await wait(2600);

const exps = await J('/api/experiments');
check('实验创建成功', exps.length === 1, `count=${exps.length}`);
if (exps[0]) {
  check('类型正确', exps[0].kind === 'sensitivity_oat', exps[0].kind);
  check('变动参数被解析', (exps[0].varied||[]).length === 1,
    JSON.stringify(exps[0].varied));
  check('取值解析成数字数组',
    JSON.stringify((exps[0].varied||[])[0]?.values) === '[0.1,0.5,1]',
    JSON.stringify((exps[0].varied||[])[0]?.values));
  const trials = await J(`/api/experiments/${exps[0].id}/trials`);
  check('展开成 3 次试验', trials.length === 3, `trials=${trials.length}`);
}

// 空取值应被拦下
const exps2 = await J('/api/experiments');
if (exps2.length === 0) {
  $('fld-label').value = 'x';
  view().querySelector('.vary-row [data-v-name]').value = 'a';
  $('exp-create').click(); await wait(1500);
  const m = $('exp-msg');
  check('变动参数缺取值会报错', m && !m.hidden, m ? m.textContent : '');
}
console.log(fails ? `\n${fails} 项失败` : '\n实验页 OK');
cleanupStaged();
process.exit(fails?1:0);
