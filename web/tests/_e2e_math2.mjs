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

// 空输入提交：用户会得到什么？
$('add-sym').click(); await wait(400);
win.document.getElementById('modal-save').click();
await wait(1800);
const modal = win.document.getElementById('modal');
const errBox = modal.querySelector('#modal-error');
console.log('  空提交后：弹窗还开着?', !modal.hidden);
console.log('           有报错信息?', errBox && !errBox.hidden ? errBox.textContent.trim() : '（无）');

// 正常填一个
$('add-sym').click(); await wait(400);
win.document.getElementById('fld-glyph').value = 'N';
win.document.getElementById('fld-meaning').value = '总天数';
win.document.getElementById('fld-role').value = 'parameter';
win.document.getElementById('modal-save').click();
await wait(2000);
const m = await J('/api/math');
check('正常填写能存进去', (m.symbols||[]).length === 1, `count=${(m.symbols||[]).length}`);
if ((m.symbols||[])[0]) {
  const s = m.symbols[0];
  check('符号值正确', s.glyph === 'N', JSON.stringify(s.glyph));
  check('释义正确', s.meaning === '总天数', JSON.stringify(s.meaning));
  check('角色正确', s.role === 'parameter', JSON.stringify(s.role));
}
// 重复符号会被拒吗？
$('add-sym').click(); await wait(400);
win.document.getElementById('fld-glyph').value = 'N';
win.document.getElementById('fld-meaning').value = '重复的';
win.document.getElementById('modal-save').click();
await wait(1800);
const m2 = await J('/api/math');
const dup = m2.duplicate_glyphs || [];
check('重复符号被检出', dup.length > 0 || (m2.symbols||[]).length === 1,
  `dups=${JSON.stringify(dup)} count=${(m2.symbols||[]).length}`);

console.log(fails ? `\n${fails} 项失败` : '\n数学页编辑 OK');
cleanupStaged();
process.exit(fails?1:0);
