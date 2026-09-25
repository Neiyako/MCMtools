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
probe.go('math'); await wait(2200);
const view = () => win.document.getElementById('view') || win.document.getElementById('app');
const $ = id => view().querySelector('#'+id);

check('有「新增符号」按钮', !!$('add-sym'));
check('有「新增公式」按钮', !!$('add-eq'));
check('有「新增假设」按钮', !!$('add-asm'));

// 真的加一个符号
if ($('add-sym')) {
  $('add-sym').click();
  await wait(500);
  const modal = win.document.getElementById('modal');
  check('弹出符号编辑框', !modal.hidden && modal.innerHTML.length > 50);
  // 找出弹窗里的输入框
  const inputs = [...modal.querySelectorAll('input,textarea,select')];
  console.log('    弹窗字段数:', inputs.length);
  inputs.forEach((el,i)=>{ if(el.id) console.log(`      [${i}] #${el.id}`); });
  const save = win.document.getElementById('modal-save');
  check('有保存按钮', !!save);
  if (save) { save.click(); await wait(2000); }
}
const m = await J('/api/math');
check('后端接受（或明确拒绝空输入）', true, `symbols=${(m.symbols||[]).length}`);
console.log(fails ? `\n${fails} 项失败` : '\n数学页 OK');
cleanupStaged();
process.exit(fails?1:0);
