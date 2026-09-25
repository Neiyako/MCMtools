/**
 * DIY 生图页面的真实 DOM 测试。
 *
 * 这个功能的卖点是"点几下就出图"，所以测试必须真的去点、
 * 真的确认预览框里换成了新的 blob —— 只检查元素存在
 * 无法证明那条链路是通的。
 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import path from 'node:path';
import { loadPanel, WEB_DIR, nativeFetch, cleanupStaged } from './harness.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:8420';
let pass = 0, fail = 0;
const check = (name, ok, extra = '') => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`);
  ok ? pass++ : fail++;
};
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const dom = new JSDOM(fs.readFileSync(path.join(WEB_DIR, 'index.html'), 'utf8'),
  { url: BASE + '/#diy', runScripts: 'outside-only', pretendToBeVisual: true });
const win = dom.window;
win.fetch = (u, o) => nativeFetch(new URL(u, BASE).href, o);
const probe = await loadPanel(['renderScreen', 'go'], win);
const doc = win.document;
const root = () => doc.getElementById('view') || doc.getElementById('content');
const $ = (id) => root().querySelector('#' + id);

await wait(1200);
probe.go('diy');
await wait(2500);

check('自定图表页有图形类型下拉框', !!$('diy-chart'));
check('列出全部图形类型', $('diy-chart') && $('diy-chart').options.length === 27,
  $('diy-chart') ? $('diy-chart').options.length + ' 种' : '');
check('有配色下拉框', root().querySelectorAll('#diy-palette option').length === 6);
check('有「画出来」按钮', !!$('diy-draw'));
check('有「存成模板」按钮', !!$('diy-save'));
check('打开就自动画了一张', $('diy-frame') && !$('diy-frame').hidden);
check('预览是 PDF blob', ($('diy-frame')?.src || '').startsWith('blob:'));

// 切换图形类型要重新画
const before = $('diy-frame').src;
$('diy-chart').value = 'scatter';
$('diy-chart').dispatchEvent(new win.Event('change'));
await wait(1800);
check('切换图形后会重画', $('diy-frame').src !== before);
check('切换后没有报错', $('diy-err').hidden,
  $('diy-err').hidden ? '' : $('diy-err').textContent.slice(0, 50));

// 矩阵类
$('diy-matrix').value = '[[1,2,3],[4,5,6],[7,8,9]]';
$('diy-chart').value = 'heatmap';
$('diy-chart').dispatchEvent(new win.Event('change'));
await wait(1800);
check('热力图能画出来', $('diy-err').hidden,
  $('diy-err').hidden ? '' : $('diy-err').textContent.slice(0, 50));

// 坏输入要被拦住并说中文
$('diy-matrix').value = 'not-json';
$('diy-draw').click();
await wait(700);
check('坏矩阵被拦住', !$('diy-err').hidden);
check('错误信息是中文', /[\u4e00-\u9fff]/.test($('diy-err').textContent),
  $('diy-err').textContent.slice(0, 40));

// 数据长度不匹配
$('diy-matrix').value = '';
$('diy-chart').value = 'line';
$('diy-chart').dispatchEvent(new win.Event('change'));
await wait(1500);
$('diy-x').value = '1, 2, 3';
$('diy-y').value = '1, 2';
$('diy-draw').click();
await wait(900);
check('长度不一致被拦住', !$('diy-err').hidden);
check('说清了两边的数量',
  /\d/.test($('diy-err').textContent) && /[\u4e00-\u9fff]/.test($('diy-err').textContent),
  $('diy-err').textContent.slice(0, 46));

console.log(`\nDIY 测试${fail ? '失败 ' + fail + ' 项' : '全部通过'}`);
process.on('exit', cleanupStaged);
process.exit(fail ? 1 : 0);
