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
const view = () => win.document.getElementById('view') || win.document.getElementById('app');
const txt = () => view().textContent.replace(/\s+/g,' ');
const $ = id => view().querySelector('#'+id);

console.log('\n### 参数页 ###');
probe.go('params'); await wait(2200);
const pbtns = [...view().querySelectorAll('button')].map(b=>b.id||b.getAttribute('data-add-param')||'').filter(Boolean);
console.log('  按钮:', pbtns.slice(0,6));
check('参数页有新增入口', pbtns.some(b=>/add|new|param/.test(b)), pbtns.join(','));

console.log('\n### 实验页 ###');
probe.go('experiments'); await wait(2200);
const ebtns = [...view().querySelectorAll('button')].map(b=>b.id||b.getAttribute('data-run')||'').filter(Boolean);
console.log('  按钮:', ebtns.slice(0,6));
check('实验页有交互', ebtns.length > 0, ebtns.join(','));

console.log('\n### 生图工作台 ###');
probe.go('figures'); await wait(3200);
const fbtns = [...view().querySelectorAll("button")].length;
console.log('  按钮数:', fbtns);
check('生图页能列出模板', txt().includes('图模板') || txt().includes('模板'), txt().slice(0,70));
const figs = await J('/api/figures/templates').catch(()=>null);
console.log('  模板数:', Array.isArray(figs) ? figs.length : JSON.stringify(figs).slice(0,60));
check('模板列表非空', Array.isArray(figs) && figs.length > 30, `${Array.isArray(figs)?figs.length:'?'}`);

console.log('\n### 自定图表 ###');
probe.go('diy'); await wait(2600);
check('自定图表页能打开', txt().includes('自定') || txt().includes('图型'), txt().slice(0,60));
const kinds = await J('/api/diy/kinds').catch(()=>null);
console.log('  图型数:', Array.isArray(kinds) ? kinds.length : JSON.stringify(kinds).slice(0,60));

console.log('\n### 参考文献 ###');
probe.go('references'); await wait(2200);
check('参考文献页能打开', txt().includes('文献'), txt().slice(0,60));

console.log('\n### 论文页 ###');
probe.go('paper'); await wait(2600);
const paperBtns = [...view().querySelectorAll('button')].map(b=>b.id).filter(Boolean);
console.log('  按钮:', paperBtns.slice(0,8));
check('论文页有构建入口', paperBtns.some(b=>/build|compile|render/i.test(b)), paperBtns.join(','));

console.log(fails ? `\n${fails} 项失败` : '\n其余页面 OK');
cleanupStaged();
process.exit(fails?1:0);
