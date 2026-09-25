import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { loadPanel, cleanupStaged, nativeFetch } from './harness.mjs';
const BASE = process.env.BASE || 'http://127.0.0.1:8499';
const dom = new JSDOM(fs.readFileSync(new URL('../index.html', import.meta.url),'utf8'),
  { url: BASE+'/', runScripts:'outside-only', pretendToBeVisual:true });
const win = dom.window;
win.fetch = (u,o) => nativeFetch(new URL(u,BASE).href, o);
win.addEventListener('error', e => console.log('  window error:', e.message));
const probe = await loadPanel(['refresh','go'], win);
await new Promise(r=>setTimeout(r,1400));
probe.go('experiments');
await new Promise(r=>setTimeout(r,2400));
const view = win.document.getElementById('view') || win.document.getElementById('app');
console.log('--- 页面内容 ---');
const eb = view.querySelector('.error-box');
console.log('错误框:', eb ? eb.textContent : '(无)');

cleanupStaged();
process.exit(0);
