/* MCMtools 面板。
 *
 * 不用框架、不用打包器，是刻意的。核心是 Python，API 已经是系统的完整描述；
 * 引入打包器意味着用户在比赛期间运行的工具是另一条他无法检查的工具链的产物。
 * 原生 ES module 由 Python 服务器直接提供。
 *
 * 唯一重要的设计规则：**每个屏幕都从 /api/state 读取阶段，侧栏由阶段构建。**
 * 一个会提供"在当前阶段根本用不了"的屏幕的界面，比一个把它藏起来的界面更糟。
 */

import { T, phaseLabel, findingLabel } from './strings.js';

// ---------------------------------------------------------------- 协议
// 架构文档 §14.2 的相位驱动导航。
// 阶段标识（build / finalize / …）保留英文：它们同时是 project.yaml 里的值。
const SCREENS = {
  overview:    { label: T.nav.overview,    phases: ['build', 'finalize'] },
  data:        { label: T.nav.data,        phases: ['build'] },
  figures:     { label: T.nav.figures,     phases: ['build'] },
  diy:         { label: T.nav.diy,         phases: ['build'] },
  references:  { label: T.nav.references,  phases: ['build'] },
  math:        { label: T.nav.math,        phases: ['build'] },
  params:      { label: T.nav.params,      phases: ['build'] },
  experiments: { label: T.nav.experiments, phases: ['build'] },
  runs:        { label: T.nav.runs,        phases: ['build'] },
  results:     { label: T.nav.results,     phases: ['build'] },
  paper:       { label: T.nav.paper,       phases: ['build', 'finalize'] },
  audit:       { label: T.nav.audit,       phases: ['build', 'finalize'] },
  problems:    { label: T.nav.problems,    phases: ['problem_selection', 'problem_locked'] },
  settings:    { label: T.nav.settings,    phases: ['problem_selection', 'problem_locked', 'build', 'finalize'] },
};

// 仅用于展示：屏幕属于侧栏哪一组。
const GROUPS = [
  [T.workflow,  ['overview']],
  [T.buildGroup, ['data', 'math', 'params', 'experiments', 'runs',
                'figures', 'diy', 'references', 'results', 'paper', 'audit']],
  [T.setupGroup, ['problems', 'settings']],
];

let STATE = null;   // 最近一次 /api/state 的返回
let ROUTE = 'overview';

// ---------------------------------------------------------------- 工具
const $ = (sel, root = document) => root.querySelector(sel);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }
  if (!res.ok) {
    const detail = body && (body.detail || body.message) || res.statusText;
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return body;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function toast(msg, kind = 'info', ms = 4000) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast toast-${kind}`;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, ms);
}

/** 重新拉取状态并重绘。任何修改之后都要调用 —— 一处改动可能影响总览上的阻塞项。 */
async function refresh() {
  STATE = await api('/api/state');
  renderSidebar();
  renderMode();
  await renderScreen();
}

// ---------------------------------------------------------------- 外框
function renderSidebar() {
  const phase = STATE.phase;
  const badge = $('#phase-badge');
  badge.textContent = phaseLabel(phase);
  badge.className = `phase-badge phase-${phase}`;

  const available = Object.keys(SCREENS).filter(k => SCREENS[k].phases.includes(phase));
  const nav = $('#nav');
  nav.innerHTML = GROUPS.map(([title, keys]) => {
    const shown = keys.filter(k => available.includes(k));
    if (!shown.length) return '';
    return `<div class="nav-group">
      <div class="nav-title">${esc(title)}</div>
      ${shown.map(k => {
        const counts = badgeFor(k);
        return `<a class="nav-item ${k === ROUTE ? 'active' : ''}" href="#${k}">
          <span>${esc(SCREENS[k].label)}</span>${counts}</a>`;
      }).join('')}
    </div>`;
  }).join('');

  nav.querySelectorAll('a').forEach(a => {
    a.onclick = (e) => { e.preventDefault(); go(a.getAttribute('href').slice(1)); };
  });
}

/** 右侧小徽标。过期数量或失败的实验必须随处可见，不能只在它所属的屏幕上显示。 */
function badgeFor(key) {
  if (!STATE) return '';
  const c = STATE.counts;
  if (key === 'results' && c.stale_artifacts) {
    return `<span class="pill pill-warn">${c.stale_artifacts} 个已过期</span>`;
  }
  if (key === 'experiments' && c.experiments.failed) {
    return `<span class="pill pill-warn">${c.experiments.failed} 个失败</span>`;
  }
  if (key === 'paper' && c.pages != null) {
    const over = c.pages > c.page_budget;
    return `<span class="pill ${over ? 'pill-err' : 'pill-muted'}">${c.pages}/${c.page_budget}</span>`;
  }
  if (key === 'audit') {
    const errs = STATE.blockers.filter(b => b.severity === 'error').length;
    if (errs) return `<span class="pill pill-err">${errs}</span>`;
  }
  return '';
}

function renderMode() {
  const p = STATE.problem || {};
  const el = $('#mode-indicator');
  const comp = p.mode === 'competition';
  el.innerHTML = `<span class="dot ${comp ? 'dot-comp' : 'dot-dev'}"></span>
    ${comp ? T.mode.competition : T.mode.development}`;
  el.title = comp ? T.mode.compHint : T.mode.devHint;
}

function setHeader(title, sub, actions = '') {
  $('#screen-title').textContent = title;
  $('#screen-sub').textContent = sub || '';
  $('#topbar-actions').innerHTML = actions;
}

function go(route) {
  if (!SCREENS[route]) route = 'overview';
  ROUTE = route;
  location.hash = route;
  renderSidebar();
  renderScreen();
}

// ---------------------------------------------------------------- 屏幕
async function renderScreen() {
  const fn = {
    overview: screenOverview,
    data: screenData,
    figures: screenFigures,
    diy: screenDiy,
    references: screenReferences,
    math: screenMath,
    params: screenParams,
    experiments: screenExperiments,
    runs: screenRuns,
    results: screenResults,
    paper: screenPaper,
    audit: screenAudit,
    problems: screenProblems,
    settings: screenSettings,
  }[ROUTE];
  const content = $('#content');
  content.innerHTML = `<div class="empty">${T.loading}</div>`;
  try {
    await fn(content);
  } catch (err) {
    content.innerHTML = `<div class="error-box">
      <strong>${T.loadFailed}</strong>
      <p>${esc(err.message)}</p></div>`;
  }
}

// -- 总览 -------------------------------------------------------------------
async function screenOverview(root) {
  const d = STATE;
  const c = d.counts;
  const p = d.problem || {};
  setHeader(
    T.overview.title,
    [p.id, p.team_number ? `${T.overview.team} ${p.team_number}` : null]
      .filter(Boolean).join(' · ') || T.overview.noProblem
  );

  const mark = { done: '✓', partial: '◐', todo: '○' };
  const steps = d.steps.map(s => `
    <div class="step step-${s.status}">
      <span class="step-mark">${mark[s.status] || '?'}</span>
      <span class="step-label">${esc(s.label)}</span>
      <span class="step-detail">${esc(s.detail)}</span>
    </div>`).join('');

  const errs = d.blockers.filter(b => b.severity === 'error').length;
  const warns = d.blockers.filter(b => b.severity === 'warning').length;

  const blockers = d.blockers.length
    ? d.blockers.map(b => `
      <div class="blocker blocker-${b.severity}">
        <div class="blocker-head">
          <code>${esc(b.code)}</code>
          ${b.target ? `<span class="muted">${esc(b.target)}</span>` : ''}
        </div>
        <p>${esc(b.message)}</p>
        <p class="action">→ ${esc(b.action)}</p>
      </div>`).join('')
    : `<div class="ok-box">${T.overview.noBlockers}</div>`;

  root.innerHTML = `
    <div class="grid grid-2">
      <div class="card">
        <h2>${T.overview.workflowCard}</h2>
        <div class="steps">${steps}</div>
      </div>
      <div class="card">
        <h2>${T.overview.blockersCard}
          <span class="muted">${T.overview.blockerCount(errs, warns)}</span>
        </h2>
        ${blockers}
      </div>
    </div>
    <div class="grid grid-4">
      ${statCard(T.overview.statSymbols, `${c.symbols} ${T.overview.unitSymbols}`,
                 c.params_unresolved ? `${c.params_unresolved} 个参数未解析` : '',
                 c.params_unresolved > 0)}
      ${statCard(T.overview.statExperiments, `${c.experiments.done}/${c.experiments.total}`,
                 c.experiments.failed ? T.overview.failedBadge(c.experiments.failed) : '',
                 c.experiments.failed > 0)}
      ${statCard(T.overview.statParams, `${c.params} ${T.overview.unitParams}`)}
      ${statCard(T.overview.statAtoms, `${c.result_atoms} ${T.overview.unitAtoms}`)}
      ${statCard(T.overview.statArtifacts, `${c.figures} 张图 · ${c.tables} 个表`,
                 c.stale_artifacts ? T.overview.staleBadge(c.stale_artifacts) : '',
                 c.stale_artifacts > 0)}
    </div>`;
}

function statCard(label, value, note = '', warn = false) {
  return `<div class="card stat ${warn ? 'stat-warn' : ''}">
    <div class="stat-value">${esc(value)}</div>
    <div class="stat-label">${esc(label)}</div>
    ${note ? `<div class="stat-note">${esc(note)}</div>` : ''}
  </div>`;
}

// -- 数据 -------------------------------------------------------------------
async function screenData(root) {
  setHeader(T.data.title, T.data.sub);
  await paintData(root);
}

/** 数据集页。
 *
 * 空状态以前让用户去命令行导入数据，而那条命令根本不存在，
 * 也没有任何别的入口。照着提示做只会得到 "invalid choice"。
 * 现在这一页自己就能导入。
 */
async function paintData(root) {
  const rows = await api('/api/datasets');

  const body = rows.length ? `<table class="data">
    <thead><tr>
      <th>${T.data.colId}</th><th>${T.data.colName}</th>
      <th>${T.data.colStage}</th><th>${T.data.colRows}</th>
      <th>${T.data.colCols}</th><th>${T.data.colSource}</th><th></th>
    </tr></thead>
    <tbody>${rows.map(d => {
      const cols = (d.schema || d.columns || []);
      return `<tr>
        <td class="mono">${esc(d.dataset_id || d.id)}</td>
        <td>${esc(d.name || '—')}</td>
        <td><span class="tag">${esc(stageLabel(d.stage))}</span></td>
        <td>${(d.files || [])[0] && (d.files || [])[0].rows != null
              ? (d.files || [])[0].rows : '—'}</td>
        <td>${cols.length || '—'}</td>
        <td class="small muted">${esc(datasetSourceLabel(d.source))}</td>
        <td class="row-actions">
          <button class="btn btn-mini btn-danger" data-del-ds="${
            esc(d.dataset_id || d.id)}">${T.math.remove}</button>
        </td>
      </tr>`;
    }).join('')}</tbody></table>` : `<div class="empty">
      <p>${T.data.empty}</p>
      <p class="muted small">${T.data.emptyHint}</p></div>`;

  root.innerHTML = `
    <div class="card">
      <h2>${T.data.card} <span class="muted">（${rows.length}）</span></h2>
      ${body}
    </div>

    <div class="card">
      <h2>${T.data.importTitle}</h2>
      <div class="muted small">${T.data.importHint}</div>
      <div id="ds-form">${fieldEditor(DATASET_FIELDS, {})}</div>
      <div class="btn-row">
        <button class="btn btn-primary" id="ds-import">${T.data.importBtn}</button>
      </div>
      <div id="ds-msg" class="small" hidden></div>
    </div>`;

  const msg = (text, ok) => {
    const el = root.querySelector('#ds-msg');
    el.hidden = false;
    el.className = ok ? 'success-box small' : 'error-box small';
    el.textContent = text;
  };

  root.querySelector('#ds-import').onclick = async () => {
    root.querySelector('#ds-msg').hidden = true;
    const v = readFields(DATASET_FIELDS);
    if (!String(v.path || '').trim()) { msg(T.data.needPath, false); return; }
    try {
      const r = await api('/api/datasets/import', {
        method: 'POST', body: JSON.stringify(v),
      });
      msg(T.data.imported(r.rows, (r.columns || []).length), true);
      await paintData(root);
    } catch (e) {
      msg(`${T.data.importFailed}${e.message || e}`, false);
    }
  };

  root.querySelectorAll('[data-del-ds]').forEach(b => {
    b.onclick = () => confirmDelete(T.math.remove, async () => {
      try {
        await api(`/api/datasets/${encodeURIComponent(
          b.getAttribute('data-del-ds'))}`, { method: 'DELETE' });
        await paintData(root);
      } catch (e) {
        msg(`${T.data.delFailed}${e.message || e}`, false);
      }
    });
  });
}

const DATASET_FIELDS = [
  { key: 'path', label: T.data.fPath, required: true,
    placeholder: '/path/to/data.csv', hint: T.data.fPathHint },
  { key: 'name', label: T.data.fName, placeholder: T.data.fNamePh },
  { key: 'kind', label: T.data.fKind, type: 'select', options: [
    { value: 'competition_provided', label: T.data.kComp },
    { value: 'external', label: T.data.kExt },
    { value: 'derived', label: T.data.kDer },
    { value: 'simulated', label: T.data.kSim },
  ], hint: T.data.fKindHint },
];

function stageLabel(s) {
  return ({ raw: T.data.stRaw, staged: T.data.stStaged, cleaned: T.data.stCleaned,
            processed: T.data.stProcessed, features: T.data.stFeatures })[s] || s || '—';
}

function datasetSourceLabel(src) {
  if (!src) return '—';
  return ({ competition_provided: T.data.kComp, external: T.data.kExt,
            derived: T.data.kDer, simulated: T.data.kSim })[src.kind] || src.kind;
}

// -- 数学内容 ---------------------------------------------------------------
async function screenMath(root) {
  setHeader(T.math.title, T.math.sub);
  await paintMath(root);
}

const SYMBOL_ROLES = ['state', 'parameter', 'derived', 'variable', 'index',
                      'constant', 'unknown'];
const EQ_ROLES = ['governing', 'definition', 'constraint', 'objective',
                  'transformation', 'metric', 'calibration', 'unknown'];
const ASSUME_SCOPES = ['model', 'paper', 'section', 'unknown'];

const SYMBOL_FIELDS = [
  { key: 'glyph', label: '符号', required: true, placeholder: '例如 beta',
    hint: '论文里出现的写法。同一个符号只能有一个含义 —— 重复定义会被审计报错。' },
  { key: 'meaning', label: '含义', required: true, type: 'textarea', rows: 2,
    placeholder: '例如 Transmission rate per active player per day',
    hint: '会直接生成到论文的符号表里，所以要写成英文的完整表述。' },
  { key: 'role', label: '类别', type: 'select', options: SYMBOL_ROLES },
  { key: 'unit', label: '单位', placeholder: '例如 /day，没有就留空' },
  { key: 'domain', label: '取值范围', placeholder: '例如 > 0' },
];

const EQ_FIELDS = [
  { key: 'id', label: '编号 ID', required: true, placeholder: 'eq:one',
    hint: '正文里用 \\eqref{eq:one} 引用它。' },
  { key: 'latex', label: 'LaTeX 公式', required: true, type: 'textarea', rows: 3,
    placeholder: '\\frac{dP}{dt} = -\\beta \\frac{P(C+L)}{N}',
    hint: '不要写 \begin{equation} 和 \\label —— 编号和标签由系统加。' },
  { key: 'number', label: '公式序号', placeholder: '例如 (1)，留空则自动编号' },
  { key: 'role', label: '作用', type: 'select', options: EQ_ROLES },
];

const ASSUME_FIELDS = [
  { key: 'id', label: '编号 ID', required: true, placeholder: 'ASM-001' },
  { key: 'text', label: '假设内容', required: true, type: 'textarea', rows: 2,
    placeholder: '例如 The population is well mixed on each day.',
    hint: '写成英文的完整句子，会进论文正文。' },
  { key: 'justification', label: '理由', type: 'textarea', rows: 2,
    placeholder: '例如 Contact rates are high enough that spatial structure washes out within a day.',
    hint: '只写"假设参数恒定"是没写完 —— 要说明为什么可以这么假设。' },
  { key: 'label', label: '简称', placeholder: '例如 Well-mixed' },
  { key: 'scope', label: '适用范围', type: 'select', options: ASSUME_SCOPES },
];

async function paintMath(root) {
  const m = await api('/api/math');
  const dups = m.duplicate_glyphs || [];
  const dupEq = m.duplicate_equation_numbers || [];

  // 重复定义是硬伤，放最前面 —— 一进页面就该看见。
  const problems = [];
  if (dups.length) {
    problems.push(`<div class="error-box">
      <b>${T.math.dupTitle}：${dups.map(esc).join('、')}</b>
      <div class="small">${T.math.dupHint}</div>
    </div>`);
  }
  if (dupEq.length) {
    problems.push(`<div class="error-box">
      <b>${T.math.dupEqTitle}：${dupEq.map(esc).join('、')}</b>
      <div class="small">${T.math.dupEqHint}</div>
    </div>`);
  }

  const row = (cells, actions) => `<tr>${cells.join('')}${
    actions ? `<td class="row-actions">${actions}</td>` : ''}</tr>`;

  const symRows = (m.symbols || []).map(x => row([
    `<td><code>${esc(x.glyph)}</code></td>`,
    `<td><span class="tag">${esc(roleLabel(x.role))}</span></td>`,
    `<td>${esc(x.meaning)}</td>`,
    `<td>${esc(x.unit || '—')}</td>`,
  ], `<button class="btn btn-mini" data-edit-sym="${esc(x.id)}">${
        T.math.edit}</button>
      <button class="btn btn-mini btn-danger" data-del-sym="${esc(x.id)}">${
        T.math.remove}</button>`));

  const eqRows = (m.equations || []).map(e => row([
    `<td class="num">${esc(e.number || '—')}</td>`,
    `<td><code>${esc(e.latex || '')}</code></td>`,
  ], `<button class="btn btn-mini" data-edit-eq="${esc(e.id)}">${
        T.math.edit}</button>
      <button class="btn btn-mini btn-danger" data-del-eq="${esc(e.id)}">${
        T.math.remove}</button>`));

  const asmRows = (m.assumptions || []).map(a => row([
    `<td>${esc(a.id)}</td>`,
    `<td>${esc(a.label || '—')}</td>`,
    `<td>${esc(a.text)}</td>`,
  ], `<button class="btn btn-mini" data-edit-asm="${esc(a.id)}">${
        T.math.edit}</button>`));

  const table = (cols, rows, cls) => rows
    ? `<table class="data ${cls || ''}"><thead><tr>${cols.map(c =>
        `<th>${c}</th>`).join('')}<th></th></tr></thead><tbody>${rows}</tbody></table>`
    : '';

  const hasAny = (m.symbols || []).length || (m.equations || []).length
              || (m.assumptions || []).length;

  root.innerHTML = problems.join('') + `
    <div class="grid grid-3">
      <div class="card"><h2>${T.math.symbols}</h2>
        <div class="big-num">${(m.symbols || []).length}</div></div>
      <div class="card"><h2>${T.math.equations}</h2>
        <div class="big-num">${(m.equations || []).length}</div>
        <div class="muted small">${T.math.numbered} ${m.summary.numbered_equations}</div></div>
      <div class="card"><h2>${T.math.assumptions}</h2>
        <div class="big-num">${(m.assumptions || []).length}</div></div>
    </div>

    ${!hasAny ? `<div class="card"><div class="empty">${T.math.empty}</div>
      <div class="muted small">${T.math.emptyHint}</div></div>` : ''}

    <div class="card">
      <h2>${T.math.symbols}
        <button class="btn btn-mini btn-primary" id="add-sym">${T.math.addSymbol}</button></h2>
      <div class="muted small">${T.math.symbolHint}</div>
      ${table([T.math.colGlyph, T.math.colRole, T.math.colMeaning, T.math.colUnit],
              symRows) || `<div class="empty">${T.math.empty}</div>`}
    </div>

    <div class="card">
      <h2>${T.math.equations}
        <button class="btn btn-mini btn-primary" id="add-eq">${T.math.addEquation}</button></h2>
      <div class="muted small">${T.math.equationHint}</div>
      ${eqRows ? table([T.math.colNumber, T.math.colLatex], eqRows)
               : `<div class="empty">${T.math.empty}</div>`}
    </div>

    <div class="card">
      <h2>${T.math.assumptions}
        <button class="btn btn-mini btn-primary" id="add-asm">${T.math.addAssumption}</button></h2>
      <div class="muted small">${T.math.assumeHint}</div>
      ${asmRows ? table(['ID', T.math.colShort, T.math.colAssumption], asmRows)
                : `<div class="empty">${T.math.empty}</div>`}
    </div>

    <div class="card">
      <h2>${T.math.notation}</h2>
      <div class="muted small">${T.math.notationHint}</div>
      <div class="kv"><div><span>${T.math.disclaimer}</span>
        <b>${esc((m.notation_table || {}).disclaimer || '—')}</b></div></div>
    </div>
  `;

  // -- 交互 --------------------------------------------------------------
  const repaint = () => paintMath(root);

  async function save(path, payload, okMsg) {
    try {
      await api(path, { method: 'PUT', body: JSON.stringify(payload) });
      $('#modal').hidden = true;
      toast(okMsg);
      await refresh();
      await repaint();
    } catch (e) {
      const box = $('#modal-error');
      if (box) box.textContent = `保存失败：${e.message || e}`;
      else toast(`保存失败：${e.message || e}`, 'error');
    }
  }

  function formModal(title, fields, record, onSubmit, extra = '') {
    openModal(`<h2>${esc(title)}</h2>
      ${extra}
      ${fieldEditor(fields, record)}
      <div id="modal-error" class="error-box small" hidden></div>
      <div class="btn-row">
        <button class="btn btn-primary" id="modal-save">${T.math.save}</button>
        <button class="btn" id="modal-cancel">${T.cancel}</button>
      </div>`);
    $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
    $('#modal-save').onclick = async () => {
      const err = $('#modal-error');
      err.hidden = true;
      let values;
      try {
        values = readFields(fields);
      } catch (e) {
        err.textContent = e.message; err.hidden = false; return;
      }
      const bad = checkRequired(fields, values);
      if (bad) { err.textContent = bad; err.hidden = false; return; }
      await onSubmit(values);
    };
  }

  $('#add-sym').onclick = () => formModal(T.math.addSymbol, SYMBOL_FIELDS, null,
    v => save(`/api/math/symbols/${encodeURIComponent(v.glyph)}`, v,
              T.math.saved));
  $('#add-eq').onclick = () => formModal(T.math.addEquation, EQ_FIELDS, null,
    v => save(`/api/math/equations/${encodeURIComponent(v.id)}`, v,
              T.math.saved));
  $('#add-asm').onclick = () => formModal(T.math.addAssumption, ASSUME_FIELDS, null,
    v => save(`/api/math/assumptions/${encodeURIComponent(v.id)}`, v,
              T.math.saved));

  root.querySelectorAll('[data-edit-sym]').forEach(b => {
    b.onclick = () => {
      const id = b.getAttribute('data-edit-sym');
      const rec = (m.symbols || []).find(x => x.id === id);
      formModal(`${T.math.edit}：${rec.glyph}`, SYMBOL_FIELDS, rec,
        v => save(`/api/math/symbols/${encodeURIComponent(rec.glyph)}`, v,
                  T.math.saved));
    };
  });
  root.querySelectorAll('[data-edit-eq]').forEach(b => {
    b.onclick = () => {
      const id = b.getAttribute('data-edit-eq');
      const rec = (m.equations || []).find(x => x.id === id);
      formModal(`${T.math.edit}：${rec.number || rec.id}`, EQ_FIELDS, rec,
        v => save(`/api/math/equations/${encodeURIComponent(rec.id)}`, v,
                  T.math.saved));
    };
  });
  root.querySelectorAll('[data-edit-asm]').forEach(b => {
    b.onclick = () => {
      const id = b.getAttribute('data-edit-asm');
      const rec = (m.assumptions || []).find(x => x.id === id);
      formModal(`${T.math.edit}：${rec.id}`, ASSUME_FIELDS, rec,
        v => save(`/api/math/assumptions/${encodeURIComponent(rec.id)}`, v,
                  T.math.saved));
    };
  });

  root.querySelectorAll('[data-del-sym]').forEach(b => {
    b.onclick = () => confirmDelete(
      T.math.remove, async () => {
        await api(`/api/math/symbols/${encodeURIComponent(
          b.getAttribute('data-del-sym'))}`, { method: 'DELETE' });
        await repaint();
      });
  });
  root.querySelectorAll('[data-del-eq]').forEach(b => {
    b.onclick = () => confirmDelete(
      T.math.remove, async () => {
        await api(`/api/math/equations/${encodeURIComponent(
          b.getAttribute('data-del-eq'))}`, { method: 'DELETE' });
        await repaint();
      });
  });
}

/** 删除前确认。误删一个符号会连带符号表出问题，值得多问一句。 */
function confirmDelete(verb, fn) {
  openModal(`<h2>${esc(verb)}</h2>
    <div class="muted">${T.confirmDelete}</div>
    <div class="btn-row">
      <button class="btn btn-danger" id="modal-save">${T.math.remove}</button>
      <button class="btn" id="modal-cancel">${T.cancel}</button>
    </div>`);
  $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
  $('#modal-save').onclick = async () => {
    $('#modal').hidden = true;
    await fn();
  };
}

function roleLabel(role) {
  return (T.math.roles || {})[role] || role || 'unknown';
}

// -- 参数 -------------------------------------------------------------------
const PARAM_SOURCES = ['literature', 'dataset', 'fitted', 'assumed',
                       'derived', 'semi_educated_guess', 'unknown'];

const PARAM_FIELDS = [
  { key: 'name', label: '参数名', required: true, placeholder: '例如 beta',
    hint: '代码里用这个名字取参数。改名字不会自动改代码，慎改。' },
  { key: 'value', label: '取值', type: 'number',
    placeholder: '留空表示还没定',
    hint: '留空的参数在审计里会被报出来 —— 这是好事，说明它确实还没定。' },
  { key: 'unit', label: '单位', placeholder: '例如 /day' },
  { key: 'source', label: '来源', type: 'select', options: PARAM_SOURCES,
    hint: '没交代来源的参数在 --strict 下会阻塞提交。' },
  { key: 'source_ref', label: '来源说明', placeholder: '例如 2023 C/2307166 表 1',
    hint: '文献参数写哪篇，拟合参数写哪个实验。' },
  { key: 'fitted_by', label: '拟合自', placeholder: '例如 EXP-001' },
  { key: 'confidence', label: '置信度', type: 'number', placeholder: '0 到 1' },
];

async function screenParams(root) {
  setHeader(T.params.title, T.params.sub);
  await paintParams(root);
}

async function paintParams(root) {
  const d = await api('/api/params');
  const list = d.parameters || [];

  const unresolved = list.filter(p => p.value === null || p.value === undefined);
  const unknown = list.filter(p => (p.source || 'unknown') === 'unknown');

  const problems = [];
  if (unresolved.length) {
    problems.push(`<div class="error-box">
      <b>${T.params.unresolved}：${unresolved.map(p => esc(p.name)).join('、')}</b>
      <div class="small">${T.params.unresolvedHint}</div>
    </div>`);
  }
  if (unknown.length) {
    problems.push(`<div class="warn-box">
      <b>${T.params.noProvenance}：${unknown.map(p => esc(p.name)).join('、')}</b>
      <div class="small">${T.params.noProvenanceHint}</div>
    </div>`);
  }

  // 来源分布：一眼看出还有多少数没交代出处。
  const counts = d.summary.by_source || {};
  const tags = Object.entries(counts).map(([k, v]) =>
    `<span class="tag ${k === 'unknown' ? 'tag-warn' : ''}">${
      esc(sourceLabel(k))} ${v}</span>`
  ).join('');

  const rows = list.map(p => `<tr>
    <td><code>${esc(p.name)}</code></td>
    <td class="num">${p.value === null || p.value === undefined
      ? '—' : esc(String(p.value))}</td>
    <td>${esc(p.unit || '—')}</td>
    <td><span class="tag ${(p.source || 'unknown') === 'unknown'
      ? 'tag-warn' : ''}">${esc(sourceLabel(p.source))}</span></td>
    <td class="muted">${esc(p.source_ref
      || (p.fitted_by ? T.params.fittedBy + p.fitted_by : '—'))}</td>
    <td class="row-actions">
      <button class="btn btn-mini" data-edit-param="${esc(p.name)}">${
        T.math.edit}</button>
      <button class="btn btn-mini btn-danger" data-del-param="${esc(p.name)}">${
        T.math.remove}</button>
    </td>
  </tr>`).join('');

  root.innerHTML = problems.join('') + `
    <div class="card">
      <h2>${T.params.bySource}</h2>
      <div class="tags">${tags || `<span class="muted">${T.params.empty}</span>`}</div>
      <div class="muted small">${T.params.sourceHint}</div>
    </div>
    <div class="card">
      <h2>${T.params.title}
        <button class="btn btn-mini btn-primary" id="add-param">${
          T.params.addParam}</button></h2>
      ${!list.length ? `<div class="empty">${T.params.empty}</div>
        <div class="muted small">${T.params.emptyHint}</div>` : `
      <table class="data">
        <thead><tr>
          <th>${T.params.colName}</th><th>${T.params.colValue}</th>
          <th>${T.params.colUnit}</th><th>${T.params.colSource}</th>
          <th>${T.params.colRef}</th><th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`}
    </div>
  `;

  const repaint = () => paintParams(root);

  function paramModal(record, isNew) {
    const fields = isNew ? PARAM_FIELDS
      : PARAM_FIELDS.filter(f => f.key !== 'name');   // 名字是主键，不让改
    openModal(`<h2>${isNew ? T.params.addParam : T.math.edit + '：' + record.name}</h2>
      ${!isNew ? `<div class="muted small">${T.params.renameHint}</div>` : ''}
      ${fieldEditor(fields, record)}
      <div id="modal-error" class="error-box small" hidden></div>
      <div class="btn-row">
        <button class="btn btn-primary" id="modal-save">${T.math.save}</button>
        <button class="btn" id="modal-cancel">${T.cancel}</button>
      </div>`);
    $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
    $('#modal-save').onclick = async () => {
      const err = $('#modal-error');
      err.hidden = true;
      let values;
      try { values = readFields(fields); }
      catch (e) { err.textContent = e.message; err.hidden = false; return; }
      const bad = checkRequired(fields, values);
      if (bad) { err.textContent = bad; err.hidden = false; return; }
      if (!isNew) values.name = record.name;
      try {
        await api(`/api/params/${encodeURIComponent(values.name)}`, {
          method: 'PUT', body: JSON.stringify(values),
        });
        $('#modal').hidden = true;
        toast(T.math.saved);
        await refresh();
        await repaint();
      } catch (e) {
        err.textContent = `${T.params.saveFailed}${e.message || e}`;
        err.hidden = false;
      }
    };
  }

  $('#add-param').onclick = () => paramModal(null, true);
  root.querySelectorAll('[data-edit-param]').forEach(b => {
    b.onclick = () => {
      const rec = list.find(x => x.name === b.getAttribute('data-edit-param'));
      paramModal(rec, false);
    };
  });
  root.querySelectorAll('[data-del-param]').forEach(b => {
    b.onclick = () => confirmDelete(T.math.remove, async () => {
      await api(`/api/params/${encodeURIComponent(
        b.getAttribute('data-del-param'))}`, { method: 'DELETE' });
      await repaint();
    });
  });
}

/** 参数来源的中文名。用户看到 "semi_educated_guess" 不知道是什么。 */
function sourceLabel(src) {
  return (T.params.sources || {})[src] || src || '未标注';
}

// -- 实验 -------------------------------------------------------------------
async function screenExperiments(root) {
  setHeader(T.experiments.title, T.experiments.sub);
  await paintExperiments(root);
}

/** 实验页。
 *
 * 空状态以前只有一句"还没有定义实验" —— 没有任何新建入口，后端也
 * 只有"运行"没有"创建"。新用户因此永远跑不出第一个结果，整条
 * 结果追踪链在这里断掉。现在能新建了。
 */
async function paintExperiments(root) {
  const exps = await api('/api/experiments');
  if (!exps.length) {
    root.innerHTML = `
      <div class="card">
        <h2>${T.experiments.card}</h2>
        <div class="empty">
          <p>${T.experiments.empty}</p>
          <p class="muted small">${T.experiments.emptyHint}</p>
        </div>
      </div>
      <div class="card">
        <h2>${T.experiments.newTitle}</h2>
        <div class="muted small">${T.experiments.newHint}</div>
        <div id="exp-form">${fieldEditor(EXPERIMENT_FIELDS, {})}</div>
        <div id="exp-varies"></div>
        <div class="btn-row">
          <button class="btn btn-mini" id="exp-add-vary">${
            T.experiments.addVary}</button>
          <button class="btn btn-primary" id="exp-create">${
            T.experiments.createBtn}</button>
        </div>
        <div id="exp-msg" class="small" hidden></div>
      </div>`;
    await wireExperimentForm(root);
    return;
  }

  const withRuns = await Promise.all(exps.map(async e => ({
    e, runs: await api(`/api/experiments/${e.id}/runs`),
  })));

  const cards = withRuns.map(({ e, runs }) => {
    const failed = runs.filter(r => r.status === 'failed');
    const statusClass = e.status === 'failed' ? 'bad'
      : e.status === 'completed' ? 'good' : 'muted';
    const varied = (e.varied || []).map(v => {
      const vals = v.values ? v.values : (v.range ? `[${v.range.join(', ')}]` : '?');
      return `${esc(v.name)} ∈ ${esc(JSON.stringify(vals))}`;
    }).join(' · ');

    return `<div class="card">
      <h2>${esc(e.id)} <span class="pill pill-${statusClass}">${esc(e.status)}</span></h2>
      <p class="sub">${esc(e.label || '')}</p>
      <div class="kv">
        <div><span>${T.experiments.kind}</span><b>${esc(e.kind)}</b></div>
        <div><span>${T.experiments.runs}</span><b>${runs.length}</b></div>
        <div><span>${T.experiments.model}</span><b>${esc(e.model_id || '—')}</b></div>
      </div>
      <div class="small"><b>${T.experiments.varied}：</b>${varied || '—'}</div>
      <div class="small"><b>${T.experiments.heldFixed}：</b>${(e.held_fixed || []).join('、') || '—'}</div>
      ${failed.length ? `<div class="warn-inline">
        ${T.experiments.failedRuns(failed.length)}</div>` : ''}
      <div class="row-actions">
        <button data-run="${esc(e.id)}">${T.experiments.run}</button>
        <button data-trials="${esc(e.id)}" class="ghost">${T.experiments.trials}</button>
      </div>
    </div>`;
  });
  root.innerHTML = `<div class="grid grid-3">${cards.join('')}</div>`;

  root.querySelectorAll('[data-run]').forEach(b => b.onclick = async () => {
    const id = b.getAttribute('data-run');
    b.disabled = true; b.textContent = T.experiments.running;
    try {
      const res = await api(`/api/experiments/${id}/run`, {
        method: 'POST', body: JSON.stringify({}),
      });
      const stale = (res.stale.figures.length + res.stale.tables.length);
      toast(T.experiments.runDone(id, res.runs.length, res.changed_atoms.length, stale),
            stale ? 'warn' : 'ok');
      await refresh();
    } catch (err) {
      toast(T.experiments.runFailed(err.message), 'err', 8000);
      b.disabled = false; b.textContent = T.experiments.run;
    }
  });

  root.querySelectorAll('[data-trials]').forEach(b => b.onclick = async () => {
    const id = b.getAttribute('data-trials');
    const trials = await api(`/api/experiments/${id}/trials`);
    openModal(`<h2>${esc(T.experiments.trialsTitle(id, trials.length))}</h2>
      <p class="muted">${T.experiments.trialsHint}</p>
      <ol class="trials">${trials.map(t =>
        `<li><code>${esc(t.condition)}</code></li>`).join('')}</ol>`);
  });
}

/** 实验类型。与后端 ExperimentKind 保持一致。 */
const EXPERIMENT_KINDS = [
  { value: 'sensitivity_oat', key: 'kOat' },
  { value: 'sensitivity_grid', key: 'kGrid' },
  { value: 'model_comparison', key: 'kCompare' },
  { value: 'robustness_noise', key: 'kNoise' },
  { value: 'monte_carlo', key: 'kMonte' },
  { value: 'cross_validation', key: 'kCV' },
  { value: 'optimization_run', key: 'kOptim' },
  { value: 'convergence_study', key: 'kConverge' },
  { value: 'simulation', key: 'kSim' },
  { value: 'train_test', key: 'kTrainTest' },
  { value: 'scenario', key: 'kScenario' },
  { value: 'backtest', key: 'kBacktest' },
  { value: 'error_analysis', key: 'kError' },
  { value: 'other', key: 'kOther' },
];

function experimentFields() {
  return [
    { key: 'label', label: T.experiments.fLabel, hint: T.experiments.fLabelHint },
    { key: 'kind', label: T.experiments.fKind, type: 'select',
      options: EXPERIMENT_KINDS.map(k => ({ value: k.value, label: T.experiments[k.key] })),
      hint: T.experiments.fKindHint },
    { key: 'dataset_id', label: T.experiments.fDataset, hint: T.experiments.fDatasetHint },
    { key: 'entrypoint', label: T.experiments.fEntry, placeholder: 'experiments/EXP-001/run.py:run',
      hint: T.experiments.fEntryHint },
    { key: 'motivation', label: T.experiments.fWhy, type: 'textarea', rows: 2,
      hint: T.experiments.fWhyHint },
  ];
}

/** 变动参数编辑器。
 *
 * 这是让"敏感性分析"真的成为敏感性分析的东西：不写变动轴，
 * 实验就只会跑一次，出图时也没有横轴可画。
 */
function varyRowHtml(idx) {
  return `<div class="vary-row" data-vary="${idx}">
    <input class="input" data-v-name placeholder="${T.experiments.vNamePh}">
    <input class="input" data-v-values placeholder="${T.experiments.vValuesPh}">
    <input class="input" data-v-unit placeholder="${T.experiments.vUnitPh}">
    <button class="btn btn-mini btn-danger" data-v-del="${idx}">${
      T.math.remove}</button>
  </div>`;
}

async function wireExperimentForm(root) {
  const box = root.querySelector('#exp-varies');
  const fieldList = experimentFields();
  box.innerHTML = `<div class="muted small" style="margin-top:12px">${
    T.experiments.varyTitle}</div>
    <div class="muted small">${T.experiments.varyHint}</div>
    <div id="vary-rows">${varyRowHtml(0)}</div>`;
  let n = 1;

  const msg = (t, ok) => {
    const el = root.querySelector('#exp-msg');
    el.hidden = false;
    el.className = ok ? 'success-box small' : 'error-box small';
    el.textContent = t;
  };
  const bindDel = () => {
    box.querySelectorAll('[data-v-del]').forEach(b => {
      b.onclick = () => {
        const rows = box.querySelectorAll('.vary-row');
        if (rows.length <= 1) {
          rows[0].querySelectorAll('input').forEach(i => { i.value = ''; });
          return;
        }
        b.closest('.vary-row').remove();
      };
    });
  };
  bindDel();

  root.querySelector('#exp-add-vary').onclick = () => {
    box.querySelector('#vary-rows').insertAdjacentHTML('beforeend', varyRowHtml(n++));
    bindDel();
  };

  root.querySelector('#exp-create').onclick = async () => {
    root.querySelector('#exp-msg').hidden = true;
    const v = readFields(fieldList);
    // 变动参数：填了名字才算，空行直接跳过
    const varied = [...box.querySelectorAll('.vary-row')].map(r => {
      const name = r.querySelector('[data-v-name]').value.trim();
      const rawVals = r.querySelector('[data-v-values]').value.trim();
      const unit = r.querySelector('[data-v-unit]').value.trim();
      if (!name) return null;
      const values = rawVals
        ? rawVals.split(/[,，\s]+/).filter(Boolean).map(x => {
            const num = Number(x);
            return Number.isFinite(num) && x !== '' ? num : x;
          })
        : null;
      return { name, values, unit: unit || null };
    }).filter(Boolean);

    if (varied.some(x => !x.values || !x.values.length)) {
      msg(T.experiments.varyNeedValues, false);
      return;
    }
    try {
      await api('/api/experiments', {
        method: 'POST', body: JSON.stringify({ ...v, varied }),
      });
      msg(T.experiments.created, true);
      await paintExperiments(root);
    } catch (e) {
      msg(`${T.experiments.createFailed}${e.message || e}`, false);
    }
  };
}

// -- 生图工作台 -------------------------------------------------------------
// 流程刻意做成"先填数、再预览"：图的输入是数据，不是先绑进论文再看。
// 预览是服务端渲染的真实 PDF，不是示意图 —— 所见即所得。
/** DIY 生图：不写代码，点选就能拼出一张自定义图。
 *
 * 为什么不做"贴代码执行"：比赛期间用户是建模的人不是程序员，
 * 贴进来的代码报错他自己没法调，而且等于开了个任意代码执行的口子。
 * 所以把"图长什么样"拆成图形类型 + 数据 + 样式三组正交选项，
 * 服务端按规格组装 —— 覆盖了绝大多数"模板库里没有我想要的图"的情况。
 */
async function screenDiy(root) {
  setHeader(T.diy.title, T.diy.sub);

  let opts;
  try {
    opts = await api('/api/diy/options');
  } catch (e) {
    root.innerHTML = `<div class="error-box">${esc(T.diy.loadFailed)}</div>`;
    return;
  }

  // 面板状态。每次都从这份对象生成规格，输入框只改它。
  const st = {
    chart: 'line',
    title: '', xlabel: '', ylabel: '', caption: '',
    palette: '学术蓝',
    width_in: 6.4, height_in: 4.0,
    grid: true, legend: true, show_values: true,
    x: '1, 2, 3, 4, 5, 6',
    y: '10, 32, 58, 74, 61, 30',
    errors: '',
    labels: '',
    seriesText: '',
    hlines: '', vlines: '',
    matrixText: '',
    multi: false,
  };

  const parseNums = (txt) => (txt || '').split(/[\s,，]+/).filter(Boolean)
    .map(v => Number(v)).filter(v => !Number.isNaN(v));

  const chartLabel = (v) => (opts.chart_types.find(c => c.value === v) || {}).label || v;

  root.innerHTML = `
    ${!opts.has_cjk_font ? `<div class="warn-box">${esc(T.diy.noFont)}</div>` : ''}
    <div class="diy-layout">
      <div class="card diy-form">
        <h2>${T.diy.appearance}</h2>
        <div class="field"><label>${T.diy.chartType}</label>
          <select id="diy-chart" class="select">
            ${opts.chart_types.map(c =>
              `<option value="${esc(c.value)}">${esc(c.label)}</option>`).join('')}
          </select></div>
        <div class="field"><label>${T.diy.palette}</label>
          <select id="diy-palette" class="select">
            ${opts.palettes.map(p =>
              `<option value="${esc(p.value)}">${esc(p.value)}</option>`).join('')}
          </select></div>
        <div class="field"><label>${T.diy.titleLabel}</label>
          <input id="diy-title" class="input" placeholder="${esc(T.diy.titlePh)}"></div>
        <div class="field-row">
          <div class="field"><label>${T.diy.xlabel}</label>
            <input id="diy-xlabel" class="input" placeholder="天数"></div>
          <div class="field"><label>${T.diy.ylabel}</label>
            <input id="diy-ylabel" class="input" placeholder="人数"></div>
        </div>
        <div class="field-row">
          <div class="field"><label>${T.diy.width}</label>
            <input id="diy-w" type="number" step="0.1" class="input" value="6.4"></div>
          <div class="field"><label>${T.diy.height}</label>
            <input id="diy-h" type="number" step="0.1" class="input" value="4.0"></div>
        </div>
        <div class="field"><label class="inline">
          <input type="checkbox" id="diy-grid" checked> ${T.diy.grid}</label></div>
        <div class="field"><label class="inline">
          <input type="checkbox" id="diy-legend" checked> ${T.diy.legend}</label></div>
        <div class="field"><label class="inline">
          <input type="checkbox" id="diy-values" checked> ${T.diy.showValues}</label></div>
      </div>

      <div class="card diy-form">
        <h2>${T.diy.dataSection}</h2>
        <div class="field"><label class="inline">
          <input type="checkbox" id="diy-multi"> ${T.diy.multiMode}</label>
          <div class="muted small">${T.diy.multiHint}</div></div>

        <div id="diy-simple">
          <div class="field"><label>${T.diy.yLabel}</label>
            <textarea id="diy-y" class="input code-area" rows="3">${st.y}</textarea>
            <div class="muted small">${T.diy.yHint}</div></div>
          <div class="field"><label>${T.diy.xLabel}</label>
            <input id="diy-x" class="input" value="${st.x}">
            <div class="muted small">${T.diy.xHint}</div></div>
        </div>

        <div id="diy-advanced" hidden>
          <div class="field"><label>${T.diy.seriesLabel}</label>
            <textarea id="diy-series" class="input code-area" rows="7"
              spellcheck="false">${esc(diySeriesSample())}</textarea>
            <div class="muted small">${T.diy.seriesHint}</div></div>
        </div>

        <div class="field"><label>${T.diy.labelsLabel}</label>
          <input id="diy-labels" class="input" placeholder="甲, 乙, 丙">
          <div class="muted small">${T.diy.labelsHint}</div></div>
        <div class="field"><label>${T.diy.errorsLabel}</label>
          <input id="diy-errors" class="input" placeholder="1, 2, 1.5, 2">
          <div class="muted small">${T.diy.errorsHint}</div></div>
        <div class="field"><label>${T.diy.matrixLabel}</label>
          <textarea id="diy-matrix" class="input code-area" rows="3"
            spellcheck="false" placeholder="[[1,2,3],[4,5,6]]"></textarea>
          <div class="muted small">${T.diy.matrixHint}</div></div>
        <div class="field-row">
          <div class="field"><label>${T.diy.hlines}</label>
            <input id="diy-hlines" class="input" placeholder="50"></div>
          <div class="field"><label>${T.diy.vlines}</label>
            <input id="diy-vlines" class="input" placeholder="3"></div>
        </div>
        <div class="field"><label>${T.diy.captionLabel}</label>
          <input id="diy-caption" class="input" placeholder="${esc(T.diy.captionPh)}"></div>

        <div class="btn-row">
          <button class="btn btn-primary" id="diy-draw">${T.diy.draw}</button>
          <button class="btn" id="diy-save">${T.diy.saveAsTemplate}</button>
        </div>
        <div id="diy-err" class="error-box small" hidden></div>
      </div>

      <div class="card diy-preview">
        <h2>${T.diy.preview}</h2>
        <div id="diy-hint" class="muted small">${esc(T.diy.drawFirst)}</div>
        <iframe id="diy-frame" class="fig-frame" hidden></iframe>
      </div>
    </div>
  `;

  function diySeriesSample() {
    return JSON.stringify([
      { name: '方案A', y: [10, 32, 58, 74] },
      { name: '方案B', y: [8, 24, 41, 55] },
    ], null, 2);
  }

  const $d = (id) => root.querySelector('#diy-' + id);

  function buildSpec() {
    const chart = $d('chart').value;
    const spec = {
      chart,
      title: $d('title').value.trim(),
      xlabel: $d('xlabel').value.trim(),
      ylabel: $d('ylabel').value.trim(),
      palette: $d('palette').value,
      width_in: Number($d('w').value) || 6.4,
      height_in: Number($d('h').value) || 4.0,
      grid: $d('grid').checked,
      legend: $d('legend').checked,
      show_values: $d('values').checked,
      hlines: parseNums($d('hlines').value),
      vlines: parseNums($d('vlines').value),
    };
    const labels = ($d('labels').value || '').split(/[,，]/).map(x => x.trim())
      .filter(Boolean);
    if (labels.length) spec.labels = labels;

    const matrixTxt = $d('matrix').value.trim();
    if (matrixTxt) {
      try {
        spec.matrix = JSON.parse(matrixTxt);
        spec.z = spec.matrix;
      } catch (e) {
        throw new Error(T.diy.badMatrix);
      }
    }

    const isMatrix = ['heatmap', 'contour', 'surface'].includes(chart);

    if (st.multi && !isMatrix) {
      try {
        spec.series = JSON.parse($d('series').value);
      } catch (e) {
        throw new Error(T.diy.badSeries);
      }
      if (!Array.isArray(spec.series) || !spec.series.length) {
        throw new Error(T.diy.badSeries);
      }
    } else if (!isMatrix) {
      // 分类图和柱状图用 values，其他用 y
      const categorical = ['bar', 'barh', 'pie', 'donut', 'pareto',
                           'waterfall', 'box', 'violin', 'hist'];
      const ys = parseNums($d('y').value);
      if (categorical.includes(chart)) {
        spec.values = ys;
        // 单序列图也要走 series，服务端按第一组取
        spec.series = [{ name: '序列 1', y: ys }];
      } else {
        spec.y = ys;
        const xs = parseNums($d('x').value);
        if (xs.length) spec.x = xs;
      }
      const errs = parseNums($d('errors').value);
      if (errs.length && spec.series) spec.series[0].errors = errs;
      else if (errs.length) spec.errors = errs;
    } else {
      const errs = parseNums($d('errors').value);
      if (errs.length) spec.errors = errs;
    }

    spec.caption = $d('caption').value.trim();
    return spec;
  }

  /** 重画。规格错误直接把中文原因显示出来，不让它变成一次失败的请求。 */
  async function draw() {
    const err = $d('err');
    err.hidden = true;
    let spec;
    try {
      spec = buildSpec();
    } catch (e) {
      err.textContent = e.message; err.hidden = false; return;
    }
    try {
      const res = await fetch('/api/diy/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec, meta: { caption: spec.caption } }),
      });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { msg = (await res.json()).detail || msg; } catch (e) { /* 保持原样 */ }
        err.textContent = msg; err.hidden = false; return;
      }
      const blob = await res.blob();
      const frame = $d('frame');
      frame.src = URL.createObjectURL(blob);
      frame.hidden = false;
      $d('hint').hidden = true;
    } catch (e) {
      err.textContent = `${T.diy.drawFailed}${e.message || e}`;
      err.hidden = false;
    }
  }

  $d('draw').onclick = draw;
  $d('chart').onchange = () => { st.chart = $d('chart').value; draw(); };
  $d('multi').onchange = () => {
    st.multi = $d('multi').checked;
    $d('simple').hidden = st.multi;
    $d('advanced').hidden = !st.multi;
    draw();
  };

  $d('save').onclick = async () => {
    const err = $d('err');
    const name = prompt(T.diy.askName, 'peak_curve');
    if (!name) return;
    let spec;
    try { spec = buildSpec(); }
    catch (e) { err.textContent = e.message; err.hidden = false; return; }
    try {
      const r = await api('/api/diy/save', {
        method: 'POST',
        body: JSON.stringify({ name, spec, meta: { caption: spec.caption } }),
      });
      toast(T.diy.savedAs(r.saved));
    } catch (e) {
      err.textContent = `${T.diy.saveFailed}${e.message || e}`;
      err.hidden = false;
    }
  };

  await draw();
}

/** 参考文献页：粘贴 BibTeX 导入、交叉核对、导出。
 *
 * 为什么重点是"粘贴"而不是"逐条填表"：现实里没人手写 BibTeX ——
 * 都是从期刊页或 Google Scholar 复制一段贴进来。让人一个个填
 * key/title/authors 字段，等于逼他做机器该做的事。
 *
 * 核对是这一页的真正价值：引了但没条目（编译成 [?]）、
 * 有条目但没引（语料 707/707 都引过）—— 这两类错人眼很难查。
 */
async function screenReferences(root) {
  setHeader(T.refs.title, T.refs.sub);
  await paintRefs(root);
}

async function paintRefs(root) {
  const d = await api('/api/references');
  const list = d.references || [];
  const cc = d.cross_check || {};

  const problems = [];
  if ((cc.missing_entry || []).length) {
    problems.push(`<div class="error-box">
      <b>${T.refs.missingEntry}：${cc.missing_entry.map(esc).join('、')}</b>
      <div class="small">${T.refs.missingEntryHint}</div>
    </div>`);
  }
  if ((cc.uncited || []).length) {
    problems.push(`<div class="warn-box">
      <b>${T.refs.uncited}：${cc.uncited.map(esc).join('、')}</b>
      <div class="small">${T.refs.uncitedHint}</div>
    </div>`);
  }
  if ((d.problems || []).length) {
    problems.push(`<div class="warn-box">
      <b>${T.refs.entryProblems}</b>
      <ul class="tight">${d.problems.map(p => `<li>${esc(p)}</li>`).join('')}</ul>
    </div>`);
  }

  const rows = list.map(r => `<tr>
    <td><code>${esc(r.key)}</code></td>
    <td>${esc(r.title || '—')}</td>
    <td>${esc((r.authors || []).join('; ') || '—')}</td>
    <td class="num">${esc(String(r.year || '—'))}</td>
    <td>${esc(r.venue || '—')}</td>
    <td>${r.ai_generated
      ? `<span class="tag tag-warn">${T.refs.aiTag}</span>` : ''}</td>
    <td class="row-actions">
      <button class="btn btn-mini" data-edit-ref="${esc(r.key)}">${
        T.math.edit}</button>
      <button class="btn btn-mini btn-danger" data-del-ref="${esc(r.key)}">${
        T.math.remove}</button>
    </td>
  </tr>`).join('');

  root.innerHTML = problems.join('') + `
    <div class="card">
      <h2>${T.refs.importTitle}</h2>
      <div class="muted small">${T.refs.importHint}</div>
      <textarea id="ref-paste" class="input code-area" rows="9"
        spellcheck="false" placeholder="${esc(T.refs.pastePh)}"></textarea>
      <div class="btn-row">
        <button class="btn btn-primary" id="ref-import">${T.refs.importBtn}</button>
        <button class="btn" id="ref-sample">${T.refs.fillSample}</button>
        <button class="btn" id="ref-export">${T.refs.exportBtn}</button>
      </div>
      <div id="ref-msg" class="small" hidden></div>
    </div>

    <div class="card">
      <h2>${T.refs.listTitle}
        <span class="muted">（${list.length}）</span></h2>
      ${list.length ? `<table class="data">
        <thead><tr>
          <th>${T.refs.colKey}</th><th>${T.refs.colTitle}</th>
          <th>${T.refs.colAuthors}</th><th>${T.refs.colYear}</th>
          <th>${T.refs.colVenue}</th><th></th><th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<div class="empty">${T.refs.empty}</div>
        <div class="muted small">${T.refs.emptyHint}</div>`}
    </div>

    <div class="card">
      <h2>${T.refs.rulesTitle}</h2>
      <ol class="tight">${(d.guidance.rules || []).map(r =>
        `<li>${esc(r)}</li>`).join('')}</ol>
    </div>
  `;

  const repaint = () => paintRefs(root);
  const msg = (text, kind) => {
    const el = root.querySelector('#ref-msg');
    el.hidden = false;
    el.className = kind === 'error' ? 'error-box small' : 'success-box small';
    el.textContent = text;
  };

  root.querySelector('#ref-import').onclick = async () => {
    const raw = root.querySelector('#ref-paste').value;
    if (!raw.trim()) { msg(T.refs.nothingPasted, 'error'); return; }
    try {
      const r = await api('/api/references/import', {
        method: 'POST', body: JSON.stringify({ bibtex: raw }),
      });
      let text = T.refs.imported(r.added.length, r.replaced.length);
      if ((r.warnings || []).length) {
        text += ' ' + T.refs.warnPrefix + r.warnings.join('；');
      }
      msg(text);
      await refresh();
      await repaint();
    } catch (e) {
      msg(`${T.refs.importFailed}${e.message || e}`, 'error');
    }
  };

  root.querySelector('#ref-sample').onclick = () => {
    root.querySelector('#ref-paste').value = d.guidance.starter;
    msg(T.refs.sampleFilled);
  };

  root.querySelector('#ref-export').onclick = () => {
    // 导出走浏览器下载，不占页面状态
    window.open('/api/references/export', '_blank');
  };

  root.querySelectorAll('[data-edit-ref]').forEach(b => {
    b.onclick = () => {
      const key = b.getAttribute('data-edit-ref');
      const rec = list.find(x => x.key === key) || {};
      editRefModal(rec, repaint);
    };
  });
  root.querySelectorAll('[data-del-ref]').forEach(b => {
    b.onclick = () => confirmDelete(T.math.remove, async () => {
      await api(`/api/references/${encodeURIComponent(
        b.getAttribute('data-del-ref'))}`, { method: 'DELETE' });
      await repaint();
    });
  });
}

function editRefModal(rec, repaint) {
  const fields = [
    { key: 'key', label: '引用键', required: true,
      hint: '正文里用 \\cite{这个键} 引用。改了它正文也要跟着改。' },
    { key: 'title', label: '标题', required: true },
    { key: 'authors', label: '作者', type: 'textarea', rows: 2,
      hint: '每行一个，或用 and 分隔。BibTeX 用 and，不是逗号。' },
    { key: 'year', label: '年份', type: 'number' },
    { key: 'venue', label: '期刊 / 会议 / 出版方' },
    { key: 'url', label: '链接' },
    { key: 'ai_generated', label: '这是 AI 工具（须在参考文献中声明）',
      type: 'bool',
      hint: 'COMAP 要求：只在正文或致谢里提一句不算，必须列进参考文献。' },
  ];
  // authors 是数组，编辑框里转成多行文本
  const shown = { ...rec, authors: (rec.authors || []).join('\n') };
  openModal(`<h2>${esc(T.math.edit)}：${esc(rec.key)}</h2>
    ${fieldEditor(fields, shown)}
    <div id="modal-error" class="error-box small" hidden></div>
    <div class="btn-row">
      <button class="btn btn-primary" id="modal-save">${T.math.save}</button>
      <button class="btn" id="modal-cancel">${T.cancel}</button>
    </div>`);
  $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
  $('#modal-save').onclick = async () => {
    const err = $('#modal-error');
    err.hidden = true;
    let v;
    try { v = readFields(fields); }
    catch (e) { err.textContent = e.message; err.hidden = false; return; }
    const bad = checkRequired(fields, v);
    if (bad) { err.textContent = bad; err.hidden = false; return; }
    v.authors = String(v.authors || '').split(/\n| and /)
      .map(x => x.trim()).filter(Boolean);
    try {
      await api(`/api/references/${encodeURIComponent(rec.key)}`, {
        method: 'PUT', body: JSON.stringify(v),
      });
      $('#modal').hidden = true;
      toast(T.math.saved);
      await repaint();
    } catch (e) {
      err.textContent = `${T.refs.saveFailed}${e.message || e}`;
      err.hidden = false;
    }
  };
}

async function screenFigures(root) {
  setHeader(T.figures.title, T.figures.sub);

  let templates = await api('/api/templates?kind=figure');
  const drawioOnes = new Set(['fig.flowchart', 'fig.model_structure']);
  const usable = templates.filter(t => t.has_code);

  // 示例数据不再写死在这里。模板到 28 个之后，手写的 12 份会让
  // 剩下 16 个点"填入示例数据"只得到 {} —— 用户面对空文本框，
  // 既不知道要填哪些键，也不知道形状。实测里这就是最直接的抱怨。
  // 现在由 /api/templates/<id> 按模板声明生成，新模板自动就有。
  const sampleCache = {};
  async function sampleOf(tid) {
    if (sampleCache[tid]) return sampleCache[tid];
    try {
      sampleCache[tid] = await api(`/api/templates/${encodeURIComponent(tid)}`);
    } catch (e) {
      sampleCache[tid] = { sample: {}, snippet: '' };
    }
    return sampleCache[tid];
  }

  const state = { current: usable[0] ? usable[0].template_id : null };

  const optionHtml = list => list.map(t =>
    `<option value="${esc(t.template_id)}">${esc(t.template_id)} — ${
      esc((t.purpose || '').slice(0, 40))}</option>`).join('');

  root.innerHTML = `
    <div class="card">
      <h2>${T.figures.pickTemplate}</h2>
      <div class="muted small">共 ${usable.length} ${T.figures.count}${
        usable.length < templates.length
          ? `（另有 ${templates.length - usable.length} 个只有说明、没有绘制代码）` : ''}</div>
      <div class="field">
        <label>${T.figures.filterLabel}</label>
        <input id="fig-filter" class="input" placeholder="${T.figures.filterHint}">
      </div>
      <select id="fig-template" class="select">${optionHtml(usable)}</select>
      <div id="fig-meta" class="muted small"></div>
      <div id="fig-count" class="muted small"></div>
    </div>

    <div class="card">
      <h2>${T.figures.pickData}</h2>
      <div class="muted small">${T.figures.dataHint}</div>
      <div class="field">
        <label>${T.figures.captionHint}</label>
        <input id="fig-caption" class="input" placeholder="例如：峰值人数随 beta 的变化">
      </div>
      <textarea id="fig-data" class="input code-area" rows="10" spellcheck="false"></textarea>
      <div id="fig-snippet"></div>
      <div class="btn-row">
        <button class="btn" id="fig-sample">${T.figures.sample}</button>
        <button class="btn btn-primary" id="fig-run">${T.figures.preview}</button>
      </div>
      <div id="fig-error"></div>
    </div>

    <div class="card">
      <h2>${T.figures.previewTitle}</h2>
      <div id="fig-out" class="muted small">—</div>
    </div>
  `;

  const sel = root.querySelector('#fig-template');
  const ta = root.querySelector('#fig-data');
  const metaEl = root.querySelector('#fig-meta');
  const errEl = root.querySelector('#fig-error');
  const outEl = root.querySelector('#fig-out');
  const filterEl = root.querySelector('#fig-filter');
  const countEl = root.querySelector('#fig-count');

  // 模板到 28 个之后，下拉框滚起来很累；而且界面是中文、模板名是英文，
  // 用户想找"画分布的图"时根本不知道该输什么。
  //
  // 所以搜索**发给服务端**：中文→英文关键词的映射表在注册表里，
  // 前端只负责传词和显示结果。曾经在前端做过一版本地过滤，结果是
  // 搜中文永远零命中 —— 因为服务端返回的字段里一个中文字都没有。
  let searchSeq = 0;
  async function applyFilter(q) {
    const needle = (q || '').trim();
    const seq = ++searchSeq;
    let hits = usable;
    if (needle) {
      try {
        const found = await api(
          `/api/templates?kind=figure&q=${encodeURIComponent(needle)}`);
        hits = found.filter(t => t.has_code);
      } catch (err) {
        // 搜索失败不能让整屏挂掉：退回全量列表，用户还能手动滚
        hits = usable;
      }
    }
    // 慢请求回来时如果用户已经改了词，丢弃这次结果，否则列表会跳回去
    if (seq !== searchSeq) return;

    sel.innerHTML = optionHtml(hits);
    countEl.textContent = needle
      ? T.figures.filterHits.replace('{n}', hits.length).replace('{q}', needle)
      : '';
    if (hits.length) {
      // 搜完自动选第一个，省一次点击；搜不到就保持原选择不动
      state.current = hits[0].template_id;
      sel.value = state.current;
      showMeta(state.current);
      fillSample(state.current);
    }
  }
  if (filterEl) {
    let debounce = null;
    filterEl.addEventListener('input', () => {
      clearTimeout(debounce);
      // 防抖：每敲一个字就发请求既卡又浪费，250ms 足够
      debounce = setTimeout(() => applyFilter(filterEl.value), 250);
    });
  }

  function showMeta(tid) {
    const t = usable.find(x => x.template_id === tid);
    if (!t) return;
    const req = (t.inputs || []).filter(i => !i.optional).map(i => i.name);
    const opt = (t.inputs || []).filter(i => i.optional).map(i => i.name);
    const isDrawio = drawioOnes.has(tid);
    metaEl.innerHTML = `
      <div><b>${T.figures.purpose}</b>：${esc(t.purpose || '—')}
        <span class="tag">${isDrawio ? T.figures.backendDrawio : T.figures.backendPlot}</span></div>
      ${t.observed_in ? `<div><b>${T.figures.evidence}</b>：${esc(t.observed_in)}</div>` : ''}
      <div><b>${T.figures.inputs}</b>：
        ${req.map(n => `<code class="req">${esc(n)}</code>`).join(' ') || '无'}
        ${opt.length ? `<span class="muted">（${T.figures.optional}：${
          opt.map(esc).join('、')}）</span>` : ''}
      </div>`;
  }

  async function fillSample(tid) {
    const info = await sampleOf(tid);
    ta.value = JSON.stringify(info.sample || {}, null, 2);
    const hint = root.querySelector('#fig-snippet');
    if (hint) {
      hint.innerHTML = info.snippet
        ? `<div class="muted small">${T.figures.keysHint}</div>` +
          `<pre class="code-block">${esc(info.snippet)}</pre>`
        : '';
    }
  }

  sel.onchange = () => {
    state.current = sel.value; showMeta(sel.value); fillSample(sel.value);
  };
  root.querySelector('#fig-sample').onclick = () => fillSample(state.current);

  root.querySelector('#fig-run').onclick = async () => {
    errEl.innerHTML = '';
    let data;
    try {
      data = ta.value.trim() ? JSON.parse(ta.value) : {};
    } catch (e) {
      // JSON 写错是最常见的失误，直接指出来，别让它变成一次失败的请求。
      errEl.innerHTML = `<div class="error-box">JSON 格式有误：${esc(e.message)}</div>`;
      return;
    }
    const isDrawio = drawioOnes.has(state.current);
    const meta = { caption: root.querySelector('#fig-caption').value || '' };
    outEl.innerHTML = `<span class="muted">${T.figures.rendering}</span>`;
    try {
      const res = await fetch('/api/templates/' + state.current + '/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data, meta, backend: isDrawio ? 'drawio' : 'matplotlib' }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        errEl.innerHTML = `<div class="error-box"><b>${T.figures.renderFail}</b>：
          ${esc(d.detail || res.status)}</div>`;
        outEl.innerHTML = '—';
        return;
      }
      if (isDrawio) {
        // drawio 返回可编辑源文件：给下载链接，并提示可以在 drawio 里改。
        const text = await res.text();
        const blob = new Blob([text], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        outEl.innerHTML = `<a class="btn" download="${state.current.split('.').pop()}.drawio"
          href="${url}">${T.figures.exportDrawio}</a>
          <pre class="code-block">${esc(text.slice(0, 600))}</pre>`;
      } else {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        outEl.innerHTML = `<embed class="fig-preview" type="application/pdf" src="${url}">
          <div class="btn-row"><a class="btn" download="preview.pdf" href="${url}">${
            T.figures.export}</a></div>`;
      }
    } catch (e) {
      errEl.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
      outEl.innerHTML = '—';
    }
  };

  showMeta(state.current);
  fillSample(state.current);
}

// -- 结果 -------------------------------------------------------------------
async function screenResults(root) {
  const stale = await api('/api/figures/stale');
  const figs = await api('/api/figures');
  const tabs = await api('/api/tables');
  const staleIds = new Set([...stale.figures, ...stale.tables].map(a => a.id));

  setHeader(T.results.title, T.results.sub,
    staleIds.size
      ? `<button id="regen-all" class="primary">${T.results.regenerateAll(staleIds.size)}</button>`
      : '');

  const statusPill = (isStale, status) =>
    `<span class="pill pill-${isStale ? 'bad' : 'good'}">${esc(status || (isStale ? 'stale' : 'ok'))}</span>`;

  const figCards = figs.map(f => {
    const isStale = staleIds.has(f.id) || f.status === 'stale';
    const bound = (f.bindings || []).length;
    return `<div class="card artifact ${isStale ? 'artifact-stale' : ''}">
      <h2>${esc(f.id)} ${statusPill(isStale, f.status)}</h2>
      <p class="sub">${esc(f.caption || '')}</p>
      <div class="preview">${f.file
        ? `<embed src="/api/figures/${encodeURIComponent(f.id)}/file#toolbar=0&navpanes=0"
             type="application/pdf">`
        : `<div class="empty small">${T.results.notGenerated}</div>`}</div>
      <div class="kv">
        <div><span>${T.results.template}</span><b>${esc(f.template_id)}</b></div>
        <div><span>${T.results.boundAtoms}</span><b>${bound}</b></div>
      </div>
      <div class="small muted">${T.results.citedIn}：${
        (f.referenced_in || []).join('、') || T.results.citedNowhere}</div>
      <div class="row-actions">
        <button data-regen="${esc(f.id)}" class="ghost">${T.results.regenerate}</button>
      </div>
    </div>`;
  }).join('');

  const tabCards = tabs.map(t => {
    const isStale = staleIds.has(t.id) || t.status === 'stale';
    const bound = t.columns ? t.columns.flatMap(c => c.atom_ids || []).length : 0;
    return `<div class="card artifact ${isStale ? 'artifact-stale' : ''}">
      <h2>${esc(t.id)} ${statusPill(isStale, t.status)}</h2>
      <p class="sub">${esc(t.caption || '')}</p>
      <div class="kv">
        <div><span>${T.results.template}</span><b>${esc(t.template_id || '—')}</b></div>
        <div><span>${T.results.boundAtoms}</span><b>${bound}</b></div>
      </div>
      <div class="row-actions">
        <button data-tsrc="${esc(t.id)}" class="ghost">${T.results.showLatex}</button>
      </div>
    </div>`;
  }).join('');

  root.innerHTML = `<h2 class="section-h">${T.results.figures}（${figs.length}）</h2>
    <div class="grid grid-3">${figCards || `<div class="empty">${T.none_yet}</div>`}</div>
    <h2 class="section-h">${T.results.tables}（${tabs.length}）</h2>
    <div class="grid grid-3">${tabCards || `<div class="empty">${T.none_yet}</div>`}</div>`;

  const regen = async (id) => {
    try {
      const res = await api(`/api/figures/${id}/regenerate`, {
        method: 'POST', body: JSON.stringify({ only_stale: true }),
      });
      toast(res.regenerated.length ? T.results.regenOk(id) : T.results.regenSkip(id), 'ok');
      await refresh();
    } catch (err) { toast(T.results.regenFailed(err.message), 'err', 8000); }
  };
  root.querySelectorAll('[data-regen]').forEach(b =>
    b.onclick = () => regen(b.getAttribute('data-regen')));
  if ($('#regen-all')) $('#regen-all').onclick = async () => {
    for (const id of staleIds) await regen(id);
  };
  root.querySelectorAll('[data-tsrc]').forEach(b => b.onclick = async () => {
    const r = await api(`/api/tables/${b.getAttribute('data-tsrc')}/source`);
    openModal(`<h2>${esc(r.table_id)}</h2>
      ${r.source ? `<pre class="code">${esc(r.source)}</pre>`
                 : `<p class="muted">${esc(r.note || T.results.latexNote)}</p>`}`);
  });
}

// -- 论文 -------------------------------------------------------------------
async function screenPaper(root) {
  const paper = await api('/api/paper');
  const budget = await api('/api/paper/budget');
  const pct = budget.pages != null && budget.budget
    ? Math.min(100, Math.round(100 * budget.pages / budget.budget)) : 0;
  const over = budget.pages != null && budget.pages > budget.budget;

  setHeader(T.papers.title, T.papers.sub,
    `<button id="build-btn" class="primary">${T.papers.build}</button>`);

  const sections = (paper.sections || []).map(s => `
    <div class="row ${s.enabled ? '' : 'row-off'}">
      <span class="mono">${esc(s.id)}</span>
      <span class="grow">${esc(s.title)}</span>
      <span class="muted small">${esc(s.kind)}</span>
      <label class="switch">
        <input type="checkbox" data-sec="${esc(s.id)}" ${s.enabled ? 'checked' : ''}>
        <span>${s.enabled ? '开' : '关'}</span>
      </label>
    </div>`).join('');

  const ai = paper.ai_usage || {};
  const aiSection = (paper.sections || []).find(s => s.kind === 'report_on_ai');
  const enabledCount = (paper.sections || []).filter(s => s.enabled).length;

  root.innerHTML = `
    <div class="grid grid-2">
      <div class="card">
        <h2>${T.papers.budget}</h2>
        <div class="budget ${over ? 'budget-over' : ''}">
          <div class="budget-num">${budget.pages ?? '—'}<span>/${budget.budget} ${T.papers.pages}</span></div>
          <div class="budget-bar"><i style="width:${pct}%"></i></div>
          <div class="muted small">${over
            ? T.papers.over(budget.pages - budget.budget)
            : T.papers.remaining(budget.remaining ?? '—')}</div>
        </div>
        <p class="muted small">${T.papers.budgetHint}</p>
      </div>
      <div class="card">
        <h2>${T.papers.aiCard}</h2>
        <div class="kv">
          <div><span>${T.papers.aiUsed}</span><b>${ai.ai_used ? T.papers.aiYes : T.papers.aiNo}</b></div>
          <div><span>${T.papers.aiEntries}</span><b>${(ai.entries || []).length}</b></div>
          <div><span>${T.papers.aiSection}</span>
            <b class="${aiSection && aiSection.enabled ? '' : 'bad'}">
              ${aiSection ? (aiSection.enabled ? T.papers.aiEnabled : T.papers.aiDisabled)
                          : T.papers.aiMissing}</b></div>
        </div>
        ${(ai.entries || []).map(e => `<div class="small muted">
          ${esc(e.tool)} ${esc(e.version || '')} — ${esc(e.phase)}${e.in_report ? '' : T.papers.aiNotInReport}
        </div>`).join('')}
      </div>
    </div>
    <div class="card">
      <h2>${T.papers.sections} <span class="muted">${T.papers.sectionsEnabled(enabledCount)}</span></h2>
      <p class="muted small">${T.papers.sectionsHint}</p>
      ${sections}
    </div>`;

  $('#build-btn').onclick = async () => {
    const b = $('#build-btn');
    b.disabled = true; b.textContent = T.papers.building;
    try {
      const res = await api('/api/paper/build', { method: 'POST' });
      toast(res.ok ? T.papers.buildOk(res.pages ?? '?') : T.papers.buildFailed,
            res.ok ? 'ok' : 'err', 7000);
      await refresh();
    } catch (err) {
      toast(T.papers.buildError(err.message), 'err', 8000);
      b.disabled = false; b.textContent = T.papers.build;
    }
  };

  root.querySelectorAll('[data-sec]').forEach(cb => cb.onchange = async () => {
    const id = cb.getAttribute('data-sec');
    try {
      await api(`/api/paper/sections/${encodeURIComponent(id)}`, {
        method: 'PUT', body: JSON.stringify({ enabled: cb.checked }),
      });
      toast(`${id} 已${cb.checked ? '启用' : '停用'}`, 'ok');
      await refresh();
    } catch (err) { toast(err.message, 'err'); cb.checked = !cb.checked; }
  });
}

// -- 审计 -------------------------------------------------------------------
async function screenAudit(root) {
  const gate = await api('/api/audit/strict');
  const ready = gate.ready_to_submit;
  setHeader(T.audit.title, T.audit.sub,
    `<button id="reaudit" class="ghost">${T.audit.rerun}</button>`);

  const list = (items, cls) => items.length
    ? items.map(f => `<div class="finding finding-${cls}">
        <div class="finding-head"><code>${esc(f.code)}</code>
          ${f.target ? `<span class="muted">${esc(f.target)}</span>` : ''}</div>
        <p>${esc(f.message)}</p>
        ${T.finding[f.code] ? `<p class="muted small">${esc(findingLabel(f.code))}</p>` : ''}
      </div>`).join('')
    : `<div class="muted small">${T.audit.noneFound}</div>`;

  root.innerHTML = `
    <div class="gate ${ready ? 'gate-ok' : 'gate-bad'}">
      <div class="gate-icon">${ready ? '✓' : '✗'}</div>
      <div>
        <div class="gate-title">${ready ? T.audit.ready : T.audit.notReady}</div>
        <div class="muted small">${ready
          ? T.audit.readyHint
          : T.audit.notReadyHint(gate.errors.length, gate.promoted_warnings.length)}</div>
      </div>
    </div>
    <div class="grid grid-2">
      <div class="card"><h2>${T.audit.errors}</h2>${list(gate.errors, 'err')}</div>
      <div class="card"><h2>${T.audit.blocking}
        <span class="muted">${T.audit.blockingHint}</span></h2>
        ${list(gate.promoted_warnings, 'warn')}</div>
    </div>
    <div class="card">
      <h2>${T.audit.strictCodes}</h2>
      <p class="muted small">${T.audit.strictHint}</p>
      <div class="tags">${gate.strict_codes.map(c => `<span class="tag mono">${esc(c)}</span>`).join('')}</div>
    </div>`;

  $('#reaudit').onclick = async () => { await refresh(); toast(T.audit.rerunDone, 'ok'); };
}

// -- 选题 -------------------------------------------------------------------
/** 选题页：登记候选题目，然后锁定一道。
 *
 * 这一页以前是个死胡同 —— 只显示"有没有锁定"，既列不出题目、
 * 也没法新建或锁定。用户第一步就卡住，而后端其实早就有
 * POST /api/project/lock。缺的纯粹是界面。
 */
async function screenProblems(root) {
  setHeader(T.problems.title, T.problems.sub);
  await paintProblems(root);
}

async function paintProblems(root) {
  const d = await api('/api/problems');
  const list = Array.isArray(d) ? d : (d.problems || []);
  const locked = (STATE.problem || {}).id;

  const rows = list.map(p => {
    const isLocked = p.id === locked;
    return `<tr class="${isLocked ? 'row-locked' : ''}">
      <td><b>${esc(p.letter || '—')}</b></td>
      <td>${esc(p.title || '—')}</td>
      <td>${esc(p.summary || '—')}</td>
      <td>${isLocked
        ? `<span class="tag tag-good">${T.problems.lockedTag}</span>`
        : `<span class="muted">${statusLabel(p.status)}</span>`}</td>
      <td class="row-actions">
        ${isLocked ? '' :
          `<button class="btn btn-mini btn-primary" data-lock="${esc(p.id)}">${
            T.problems.lockBtn}</button>`}
        <button class="btn btn-mini" data-edit-prob="${esc(p.id)}">${
          T.math.edit}</button>
        ${isLocked ? '' :
          `<button class="btn btn-mini btn-danger" data-del-prob="${esc(p.id)}">${
            T.math.remove}</button>`}
      </td>
    </tr>`;
  }).join('');

  root.innerHTML = `
    <div class="card">
      <h2>${T.problems.card}</h2>
      <p class="muted">${T.problems.hint}</p>
      <div class="row"><span class="grow">${T.problems.locked}</span>
        <b>${esc(locked || T.problems.noneLocked)}</b></div>
      ${locked ? `<div class="ok-box small">${T.problems.lockedHint}</div>` : ''}
    </div>

    <div class="card">
      <h2>${T.problems.listTitle}
        <span class="muted">（${list.length}）</span></h2>
      ${list.length ? `<table class="data">
        <thead><tr>
          <th>${T.problems.colLetter}</th><th>${T.problems.colTitle}</th>
          <th>${T.problems.colNote}</th><th>${T.problems.colStatus}</th>
          <th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<div class="empty">${T.problems.empty}</div>`}
    </div>

    <div class="card">
      <h2>${T.problems.addTitle}</h2>
      <div class="muted small">${T.problems.addHint}</div>
      <div id="prob-form">${fieldEditor(PROBLEM_FIELDS, {})}</div>
      <div class="btn-row">
        <button class="btn btn-primary" id="prob-add">${T.problems.addBtn}</button>
      </div>
      <div id="prob-msg" class="small" hidden></div>
    </div>
  `;

  const repaint = async () => {
    // 锁定会改 phase，必须整体刷新，否则侧栏还停在旧阶段
    await refresh();
    await paintProblems(root);
  };
  const msg = (text, kind) => {
    const el = root.querySelector('#prob-msg');
    el.hidden = false;
    el.className = kind === 'error' ? 'error-box small' : 'success-box small';
    el.textContent = text;
  };

  root.querySelector('#prob-add').onclick = async () => {
    const err = root.querySelector('#prob-msg');
    err.hidden = true;
    let v;
    try { v = readFields(PROBLEM_FIELDS); }
    catch (e) { msg(e.message, 'error'); return; }
    if (!String(v.letter || '').trim() && !String(v.title || '').trim()) {
      msg(T.problems.needOne, 'error');
      return;
    }
    try {
      await api('/api/problems', {
        method: 'POST', body: JSON.stringify(v),
      });
      msg(T.problems.added);
      await repaint();
    } catch (e) {
      msg(`${T.problems.addFailed}${e.message || e}`, 'error');
    }
  };

  root.querySelectorAll('[data-lock]').forEach(b => {
    b.onclick = () => lockProblemModal(b.getAttribute('data-lock'), repaint);
  });
  root.querySelectorAll('[data-edit-prob]').forEach(b => {
    b.onclick = () => {
      const rec = list.find(x => x.id === b.getAttribute('data-edit-prob')) || {};
      editProblemModal(rec, repaint);
    };
  });
  root.querySelectorAll('[data-del-prob]').forEach(b => {
    b.onclick = () => confirmDelete(T.math.remove, async () => {
      try {
        await api(`/api/problems/${encodeURIComponent(
          b.getAttribute('data-del-prob'))}`, { method: 'DELETE' });
        await repaint();
      } catch (e) {
        msg(`${T.problems.delFailed}${e.message || e}`, 'error');
      }
    });
  });
}

/** 题目编辑字段。和新增共用，避免两处定义漂移。 */
const PROBLEM_FIELDS = [
  { key: 'letter', label: T.problems.colLetter, hint: T.problems.letterHint },
  { key: 'title', label: T.problems.colTitle },
  { key: 'summary', label: T.problems.colNote, type: 'textarea', rows: 2,
    hint: T.problems.noteHint },
];

function statusLabel(s) {
  return ({ candidate: T.problems.stCandidate, analysed: T.problems.stAnalysed,
            chosen: T.problems.stChosen, rejected: T.problems.stRejected })[s]
    || s || '—';
}

/** 锁定确认。锁定会收窄侧栏，是个不可忽略的动作，所以要确认。 */
function lockProblemModal(problemId, repaint) {
  openModal(`<h2>${T.problems.lockTitle}</h2>
    <p class="muted small">${T.problems.lockHint}</p>
    <div class="field">
      <label>${T.problems.colLetter}</label>
      <input class="input" value="${esc(problemId)}" disabled>
    </div>
    <div class="field">
      <label>${T.problems.teamNumber}</label>
      <input class="input" id="lock-team" placeholder="2400996"
        value="${esc((STATE.problem || {}).team_number || '')}">
      <div class="small muted">${T.problems.teamHint}</div>
    </div>
    <div id="modal-error" class="error-box small" hidden></div>
    <div class="btn-row">
      <button class="btn btn-primary" id="modal-save">${T.problems.lockBtn}</button>
      <button class="btn" id="modal-cancel">${T.cancel}</button>
    </div>`);
  $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
  $('#modal-save').onclick = async () => {
    const err = $('#modal-error');
    err.hidden = true;
    try {
      await api('/api/project/lock', {
        method: 'POST',
        body: JSON.stringify({
          problem_id: problemId,
          team_number: $('#lock-team').value.trim() || null,
        }),
      });
      $('#modal').hidden = true;
      toast(T.problems.locked2);
      await repaint();
    } catch (e) {
      err.textContent = `${T.problems.lockFailed}${e.message || e}`;
      err.hidden = false;
    }
  };
}

function editProblemModal(rec, repaint) {
  openModal(`<h2>${esc(T.math.edit)}：${esc(rec.id)}</h2>
    ${fieldEditor(PROBLEM_FIELDS, rec)}
    <div id="modal-error" class="error-box small" hidden></div>
    <div class="btn-row">
      <button class="btn btn-primary" id="modal-save">${T.math.save}</button>
      <button class="btn" id="modal-cancel">${T.cancel}</button>
    </div>`);
  $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
  $('#modal-save').onclick = async () => {
    const err = $('#modal-error');
    err.hidden = true;
    let v;
    try { v = readFields(PROBLEM_FIELDS); }
    catch (e) { err.textContent = e.message; err.hidden = false; return; }
    try {
      await api(`/api/problems/${encodeURIComponent(rec.id)}`, {
        method: 'PUT', body: JSON.stringify(v),
      });
      $('#modal').hidden = true;
      toast(T.math.saved);
      await repaint();
    } catch (e) {
      err.textContent = `${T.problems.saveFailed}${e.message || e}`;
      err.hidden = false;
    }
  };
}

// -- 设置 -------------------------------------------------------------------
async function screenSettings(root) {
  setHeader(T.settings.title, T.settings.sub);
  await paintSettings(root);
}

async function paintSettings(root) {
  const project = await api('/api/project');
  const mode = await api('/api/mode');

  root.innerHTML = `
    <div class="grid grid-2">
      <div class="card">
        <h2>${T.settings.project}</h2>
        <div class="kv">
          <div><span>${T.settings.projectId}</span><b>${esc(project.project_id)}</b></div>
          <div><span>${T.settings.phase}</span><b>${esc(phaseLabel(project.phase))}</b></div>
          <div><span>${T.settings.lockedProblem}</span><b>${esc(project.locked_problem_id || '—')}</b></div>
          <div><span>${T.settings.teamNumber}</span><b>${esc(project.team_control_number || '—')}</b></div>
        </div>
        <div class="btn-row">
          <button class="btn btn-mini" id="set-team">${T.settings.editTeam}</button>
          ${project.locked_problem_id
            ? `<button class="btn btn-mini btn-danger" id="set-unlock">${
                T.settings.unlock}</button>` : ''}
        </div>
      </div>
      <div class="card">
        <h2>${T.settings.runMode}</h2>
        <div class="kv">
          <div><span>${T.settings.mode}</span><b>${
            mode.project_mode === 'competition' ? T.mode.competition : T.mode.development}</b></div>
          <div><span>${T.settings.netGuard}</span>
            <b class="${mode.network_guard_installed ? 'good' : ''}">
              ${mode.network_guard_installed ? T.settings.installed : T.settings.notInstalled}</b></div>
          <div><span>${T.settings.blockedOutbound}</span><b>${mode.blocked_outbound.length}</b></div>
        </div>
        <p class="muted small">${T.settings.modeHint}</p>
        ${mode.blocked_outbound.length ? `<div class="warn-inline">
          ${mode.blocked_outbound.slice(-3).map(v =>
            `<div class="small mono">${esc(v.at)} ${esc(v.detail)}</div>`).join('')}
        </div>` : ''}
      </div>
    </div>`;

  // 队伍号：印在摘要页上，比赛期间可能后补或改动。
  // 没有入口的话，用户只能去手工编辑 project.yaml。
  const teamBtn = $('#set-team');
  if (teamBtn) {
    teamBtn.onclick = () => {
      openModal(`<h2>${T.settings.editTeam}</h2>
        <div class="field">
          <label>${T.settings.teamNumber}</label>
          <input class="input" id="team-input" value="${
            esc(project.team_control_number || '')}" placeholder="2400996">
          <div class="small muted">${T.settings.teamHint}</div>
        </div>
        <div id="modal-error" class="error-box small" hidden></div>
        <div class="btn-row">
          <button class="btn btn-primary" id="modal-save">${T.math.save}</button>
          <button class="btn" id="modal-cancel">${T.cancel}</button>
        </div>`);
      $('#modal-cancel').onclick = () => { $('#modal').hidden = true; };
      $('#modal-save').onclick = async () => {
        const err = $('#modal-error');
        err.hidden = true;
        try {
          await api('/api/project', {
            method: 'PUT',
            body: JSON.stringify({
              team_control_number: $('#team-input').value.trim(),
            }),
          });
          $('#modal').hidden = true;
          toast(T.math.saved);
          await refresh();
          await paintSettings(root);
        } catch (e) {
          err.textContent = `${T.settings.saveFailed}${e.message || e}`;
          err.hidden = false;
        }
      };
    };
  }

  // 解锁：锁错题、或想回头比较几道题时的退路
  const unlockBtn = $('#set-unlock');
  if (unlockBtn) {
    unlockBtn.onclick = () => confirmDelete(T.settings.unlock, async () => {
      try {
        await api('/api/project/unlock', { method: 'POST' });
        toast(T.settings.unlocked);
        await refresh();
        await paintSettings(root);
      } catch (e) {
        toast(`${T.settings.unlockFailed}${e.message || e}`);
      }
    });
  }
}

// ---------------------------------------------------------------- 弹窗
function openModal(html) {
  $('#modal-body').innerHTML = html;
  $('#modal').hidden = false;
}
$('#modal').onclick = (e) => { if (e.target.id === 'modal') $('#modal').hidden = true; };
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#modal').hidden = true; });

// -- 通用编辑弹窗 -----------------------------------------------------------
// 面板原来只有"看"没有"改"：数学内容和参数两页全是只读表格，
// 想改一个符号释义得去翻 math/math.yaml。这是实测里最直接的抱怨。
//
// 这里把"改一个记录"做成通用件：给字段定义，弹窗负责取值、校验、
// 提交、报错。各页只要声明自己的字段即可，不用各写一套表单。
//
// fields: [{ key, label, type, required, options, hint, rows, placeholder }]
// type: text | textarea | number | select | bool
function fieldEditor(fields, record, opts = {}) {
  const val = (f) => {
    const v = record ? record[f.key] : undefined;
    if (v === null || v === undefined) return f.default !== undefined ? f.default : '';
    return v;
  };
  return fields.map(f => {
    const v = val(f);
    const id = `fld-${f.key}`;
    const hint = f.hint ? `<div class="muted small">${esc(f.hint)}</div>` : '';
    const req = f.required ? ' <span class="req-mark">*</span>' : '';
    if (f.type === 'textarea') {
      return `<div class="field"><label>${esc(f.label)}${req}</label>
        <textarea id="${id}" class="input code-area" rows="${f.rows || 3}"
          spellcheck="false" placeholder="${esc(f.placeholder || '')}">${esc(v)}</textarea>
        ${hint}</div>`;
    }
    if (f.type === 'select') {
      const opts2 = (f.options || []).map(o => {
        const ov = typeof o === 'string' ? o : o.value;
        const ol = typeof o === 'string' ? o : o.label;
        return `<option value="${esc(ov)}"${String(ov) === String(v) ? ' selected' : ''}>${esc(ol)}</option>`;
      }).join('');
      return `<div class="field"><label>${esc(f.label)}${req}</label>
        <select id="${id}" class="select">${opts2}</select>${hint}</div>`;
    }
    if (f.type === 'bool') {
      return `<div class="field"><label class="inline">
        <input type="checkbox" id="${id}"${v ? ' checked' : ''}> ${esc(f.label)}</label>
        ${hint}</div>`;
    }
    const itype = f.type === 'number' ? 'number' : 'text';
    const step = f.type === 'number' ? ' step="any"' : '';
    return `<div class="field"><label>${esc(f.label)}${req}</label>
      <input id="${id}" type="${itype}"${step} class="input"
        value="${esc(v)}" placeholder="${esc(f.placeholder || '')}">${hint}</div>`;
  }).join('');
}

/** 从弹窗读回字段值。空字符串按"没填"处理，交给必填校验。 */
function readFields(fields) {
  const out = {};
  for (const f of fields) {
    const el = $(`#fld-${f.key}`);
    if (!el) continue;
    if (f.type === 'bool') { out[f.key] = !!el.checked; continue; }
    const raw = el.value;
    if (f.type === 'number') {
      // 用 number 输入框时浏览器会**吞掉**非数字：用户敲 "abc"，
      // el.value 直接变成空串。看起来像是"输入没了"，而不是"填错了"。
      // 所以查一下 validity.badInput —— 它能区分"空着"和"敲了非法字符"。
      if (el.validity && el.validity.badInput) {
        throw new Error(`「${f.label}」只能填数字，请重新输入。`);
      }
      if (raw === '') { out[f.key] = null; continue; }
      out[f.key] = Number(raw);
      if (Number.isNaN(out[f.key])) {
        throw new Error(`「${f.label}」要填数字，你填的是「${raw}」`);
      }
    } else {
      out[f.key] = raw.trim() === '' ? null : raw.trim();
    }
  }
  return out;
}

/** 校验必填，返回第一条错误。 */
function checkRequired(fields, values) {
  for (const f of fields) {
    if (!f.required) continue;
    const v = values[f.key];
    if (v === null || v === undefined || v === '') return `「${f.label}」不能为空`;
  }
  return null;
}

function tableCard(headers, rows) {
  return `<div class="card"><table class="data">
    <thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div>`;
}

/**
 * 仅供测试：注入一份 STATE。
 *
 * badgeFor 读模块内的 STATE，而 STATE 只有 refresh() 会写。要给每个状态组合
 * 写测试，就得能直接放一份进去 —— 否则测试只能靠字符串替换源码，
 * 那测的就不是真正会跑的代码了。生产代码不会调用它。
 */
// -- 运行记录 ---------------------------------------------------------------
//
// 这一页回答的是"这个数字是哪次运行算出来的、用的哪版代码"。
// 每次运行单独归档在 runs/<实验>/<运行号>/ 下，编号顺序即执行顺序。
async function screenRuns(root) {
  setHeader(T.runs.title, T.runs.sub);
  const [runs, summary] = await Promise.all([
    api('/api/runs'),
    api('/api/runs/summary'),
  ]);

  const stale = summary.stale_runs || [];
  const staleBox = stale.length ? `<div class="error-box">
      <strong>${T.runs.staleTitle}</strong>
      <p>${T.runs.staleHint}</p>
      <ul>${stale.map(x => `<li>${
        x.reason === 'script_missing'
          ? esc(T.runs.staleMissing(x.script))
          : esc(T.runs.staleScript(x.script))
      } · ${esc(x.experiment_id)} · ${T.runs.rerunHint}</li>`).join('')}</ul>
    </div>` : '';

  if (!runs.length) {
    root.innerHTML = staleBox + `<div class="empty">${T.runs.empty}</div>`;
    return;
  }

  // 按实验分组，保持左侧顺序
  const byExp = new Map();
  for (const r of runs) {
    if (!byExp.has(r.experiment_id)) byExp.set(r.experiment_id, []);
    byExp.get(r.experiment_id).push(r);
  }

  const sections = [...byExp.entries()].map(([expId, list]) => {
    const rows = list.map(r => {
      const ok = r.status === 'success';
      const params = Object.entries(r.resolved_parameters || {})
        .map(([k, v]) => `${esc(k)}=${esc(String(v))}`).join(', ');
      const arts = r.artifacts || [];
      const artCell = arts.length
        ? arts.map(a => `<code class="small">${esc(a)}</code>`).join('<br>')
        : `<span class="muted">${T.runs.artifactsNone}</span>`;
      const hash = (r.script && r.script.sha256)
        ? r.script.sha256.slice(0, 8) : '—';
      return `<tr>
        <td><code>${esc(r.run_id)}</code></td>
        <td><span class="pill pill-${ok ? 'good' : 'bad'}">${
          ok ? T.runs.statusOk : T.runs.statusFail}</span></td>
        <td class="small">${params || '—'}</td>
        <td class="small">${r.condition ? esc(r.condition) : '—'}</td>
        <td class="num">${r.atom_count != null ? r.atom_count : '—'}</td>
        <td class="num">${
          r.duration_seconds != null ? esc(String(r.duration_seconds)) + 's' : '—'}</td>
        <td>${artCell}</td>
        <td class="small"><code>${esc(r.script ? r.script.path : '—')}</code>
          <br><span class="muted">${esc(hash)}</span></td>
      </tr>`;
    }).join('');

    return `<div class="card">
      <h2>${esc(expId)} <span class="pill pill-muted">${
        T.runs.totalRuns(list.length)}</span></h2>
      <table class="tbl runs-tbl">
        <thead><tr>
          <th>${T.runs.colRun}</th><th>${T.runs.colStatus}</th>
          <th>${T.runs.colParams}</th><th>${T.runs.condition}</th>
          <th>${T.runs.colAtoms}</th><th>${T.runs.colDuration}</th>
          <th>${T.runs.colArtifacts}</th><th>${T.runs.script}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="small muted">${T.runs.dir}：<code>${
        esc(list[list.length - 1].dir || '')}</code></div>
    </div>`;
  }).join('');

  root.innerHTML = staleBox + sections;
}

export function setStateForTest(next) {
  STATE = next;
}

// ---------------------------------------------------------------- 启动
window.addEventListener('hashchange', () => go(location.hash.slice(1) || 'overview'));

(async function boot() {
  try {
    await refresh();
    go(location.hash.slice(1) || 'overview');
  } catch (err) {
    $('#content').innerHTML = `<div class="error-box">
      <strong>${T.apiDown}</strong>
      <p>${esc(err.message)}</p>
      <p class="muted">${T.apiDownHint} <code>./start</code></p></div>`;
  }
})();
