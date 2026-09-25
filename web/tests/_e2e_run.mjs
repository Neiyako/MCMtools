import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';
const BASE = process.env.BASE || 'http://127.0.0.1:8499';
let fails = 0;
const check = (n,c,e='') => { console.log(`  ${c?'PASS':'FAIL'}  ${n}${e?'  — '+e:''}`); if(!c) fails++; };
const wait = ms => new Promise(r=>setTimeout(r,ms));
const J = async (p,o) => { const r = await nativeFetch(BASE+p,o); const t = await r.text();
  try { return JSON.parse(t); } catch { return {__raw:t.slice(0,200), __s:r.status}; } };

const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'),
  { url: BASE+'/', runScripts:'outside-only', pretendToBeVisual:true });
const win = dom.window;
win.fetch = (u,o) => nativeFetch(new URL(u,BASE).href, o);
const probe = await loadPanel(['refresh','go'], win);
await wait(1400);
const view = () => win.document.getElementById('view') || win.document.getElementById('app');
const $ = id => view().querySelector('#'+id);
const txt = () => view().textContent.replace(/\s+/g,' ');

// 把 entrypoint 补上：写一个真实可跑的脚本
const expDir = '/tmp/e2e_proj2/experiments/EXP-001';
fs.writeFileSync(expDir + '/run.py', `
def run(trial):
    w = trial.get("hard_mode_weight", 1.0)
    return {"score": round(1.0 / (1.0 + w), 4), "weight": w}
`);
const y = fs.readFileSync(expDir + '/experiment.yaml', 'utf8');
fs.writeFileSync(expDir + '/experiment.yaml',
  y.includes('entrypoint') ? y
    : y + '\nentrypoint: experiments/EXP-001/run.py:run\n');

console.log('### 运行实验 ###');
probe.go('experiments'); await wait(2600);
const runBtn = view().querySelector('[data-run]');
check('实验卡片有「运行」按钮', !!runBtn, txt().slice(0,70));
if (runBtn) {
  runBtn.click();
  await wait(6000);
}
const runs = await J('/api/runs');
const list = Array.isArray(runs) ? runs : (runs.runs || []);
check('产生了运行记录', list.length === 3, `runs=${list.length}`);
const atoms = await J('/api/results');
const alist = Array.isArray(atoms) ? atoms : (atoms.atoms || atoms.results || []);
check('产生了结果原子', (alist||[]).length > 0, `atoms=${(alist||[]).length}`);

console.log('\n### 运行记录页 ###');
probe.go('runs'); await wait(2400);
check('运行记录页能看到', txt().includes('RUN') || txt().includes('运行'), txt().slice(0,70));

console.log('\n### 论文页 ###');
probe.go('paper'); await wait(2600);
const buildBtn = $('build-btn');
check('论文页有构建按钮', !!buildBtn);
if (buildBtn) {
  buildBtn.click();
  await wait(8000);
  console.log('  构建后:', txt().slice(0, 120));
}
console.log(fails ? `\n${fails} 项失败` : '\n运行链路 OK');
cleanupStaged();
process.exit(fails?1:0);
