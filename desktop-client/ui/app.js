'use strict';

const $ = (id) => document.getElementById(id);
const output = $('output');
const modal = $('modal');

const state = {
  actions: [],
  open: {},        // channel -> 当前正在流式写入的 <pre>
  running: 0,
};

/* ── 事件入口：后端通过 evaluate_js 推送 ───────────────────── */
window.__onEvent = function (kind, p) {
  if (kind === 'start') return onStart(p);
  if (kind === 'chunk') return onChunk(p);
  if (kind === 'done') return onDone(p);
};

/* ── 输出区块 ──────────────────────────────────────────── */
function clearHint() {
  const hint = output.querySelector('.hint');
  if (hint) hint.remove();
}

function newEntry(channel, title) {
  clearHint();
  const wrap = document.createElement('div');
  wrap.className = 'entry';

  const head = document.createElement('div');
  head.className = 'entry-head';
  const tag = document.createElement('span');
  tag.className = 'tag ' + (channel === 'chat' ? 'tag-ask' : 'tag-act');
  tag.textContent = channel === 'chat' ? 'AI' : '脚本';
  const name = document.createElement('span');
  name.textContent = title;
  const time = document.createElement('span');
  time.className = 'entry-time';
  time.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  head.append(tag, name, time);

  const pre = document.createElement('pre');
  pre.className = 'body';

  wrap.append(head, pre);
  output.append(wrap);
  scrollToEnd();
  return pre;
}

function scrollToEnd() { output.scrollTop = output.scrollHeight; }

function onStart(p) {
  state.open[p.channel] = newEntry(p.channel, p.title);
  state.running += 1;
  syncControls();
}

function onChunk(p) {
  const pre = state.open[p.channel];
  if (!pre) return;
  pre.textContent += (pre.textContent ? '\n' : '') + p.line;
  scrollToEnd();
}

function onDone(p) {
  const pre = state.open[p.channel];
  delete state.open[p.channel];
  state.running = Math.max(0, state.running - 1);
  syncControls();

  if (pre) {
    const text = (p.text || '').trim();
    if (text) pre.textContent = text;
    if (!pre.textContent.trim()) {
      pre.textContent = p.ok ? '（无输出）' : '（执行失败，无输出）';
      pre.classList.add('empty');
    }
    pre.classList.add(p.ok ? 'ok' : 'err');
    scrollToEnd();
  } else if (!p.ok && p.text) {
    newEntry(p.channel, '错误').textContent = p.text;
  }
}

function syncControls() {
  const busy = state.running > 0;
  $('busy').classList.toggle('hidden', !busy);
  $('cancelBtn').disabled = !busy;
  $('askBtn').disabled = busy;
}

/* ── 侧栏 ──────────────────────────────────────────────── */
function renderSidebar(actions) {
  const bar = $('sidebar');
  bar.textContent = '';
  const groups = [];
  for (const a of actions) {
    let g = groups.find((x) => x.name === a.group);
    if (!g) { g = { name: a.group, items: [] }; groups.push(g); }
    g.items.push(a);
  }
  for (const g of groups) {
    const h = document.createElement('div');
    h.className = 'group-title';
    h.textContent = g.name;
    bar.append(h);
    for (const a of g.items) {
      const btn = document.createElement('button');
      btn.className = 'act';
      btn.textContent = a.label;
      const marks = [];
      if (a.dialog) marks.push(a.dialog === 'dir' ? '需选择文件夹' : '需选择文件');
      if (a.prompt) marks.push('需输入参数');
      btn.title = marks.length ? a.label + '（' + marks.join('、') + '）' : a.label;
      btn.addEventListener('click', () => fire(a));
      bar.append(btn);
    }
  }
}

async function fire(action) {
  if (state.running > 0) return;

  let path = '';
  if (action.dialog) {
    const picked = await window.pywebview.api.pick_path(action.id);
    if (!picked || picked.ok === false) {
      if (picked && picked.cancelled) return;   // 用户取消，不用报错
      if (picked && picked.error) showNotice('错误', picked.error);
      return;
    }
    path = picked.path;
  }

  let arg = '';
  if (action.prompt) {
    arg = await askParam(action.label, action.prompt, path);
    if (arg === null) return;
  }

  const res = await window.pywebview.api.run_action(action.id, arg, path);
  if (res && res.ok === false) showNotice('错误', res.error);
}

/* ── 参数弹窗 ──────────────────────────────────────────── */
let modalResolve = null;

function askParam(label, hint, path) {
  $('modalLabel').textContent = label + ' — ' + hint;
  $('modalInput').value = '';
  const note = path ? '已选择：' + path : '';
  $('modalPath').textContent = note;
  $('modalPath').classList.toggle('hidden', !note);
  modal.classList.remove('hidden');
  $('modalInput').focus();
  return new Promise((resolve) => { modalResolve = resolve; });
}

function closeModal(value) {
  modal.classList.add('hidden');
  const r = modalResolve;
  modalResolve = null;
  if (r) r(value);
}

$('modalOk').addEventListener('click', () => closeModal($('modalInput').value));
$('modalCancel').addEventListener('click', () => closeModal(null));
$('modalInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); closeModal($('modalInput').value); }
  if (e.key === 'Escape') closeModal(null);
});

/* ── 提示信息 ──────────────────────────────────────────── */
function showNotice(title, text) {
  const pre = newEntry('action', title);
  pre.textContent = text || '';
  pre.classList.add('err');
}

/* ── 提问 ──────────────────────────────────────────────── */
$('askForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('askInput');
  const text = input.value.trim();
  if (!text || state.running > 0) return;
  const res = await window.pywebview.api.ask(text);
  if (res && res.ok === false) { showNotice('无法提问', res.error); return; }
  input.value = '';
});

/* ── 顶栏按钮 ──────────────────────────────────────────── */
$('clearBtn').addEventListener('click', () => {
  output.textContent = '';
  const hint = document.createElement('div');
  hint.className = 'hint';
  hint.innerHTML = '<p>已清空。</p>';
  output.append(hint);
  state.open = {};
});

$('cancelBtn').addEventListener('click', () => window.pywebview.api.cancel());
$('openSkill').addEventListener('click', () => window.pywebview.api.open_dir('skill'));
$('openCourseware').addEventListener('click', () => window.pywebview.api.open_dir('courseware'));

/* ── Gateway 状态 ──────────────────────────────────────── */
function paintGateway(up) {
  const el = $('gw');
  el.className = 'gw ' + (up ? 'gw-up' : 'gw-down');
  $('gwText').textContent = up ? 'Gateway 在线' : 'Gateway 离线';
  el.title = up
    ? 'OpenClaw Gateway 运行中，可以问 AI'
    : 'OpenClaw Gateway 未运行，问 AI 不可用（脚本按钮不受影响）';
}

async function refreshGateway() {
  try {
    const h = await window.pywebview.api.gateway_health();
    paintGateway(!!(h && h.up));
  } catch (err) {
    paintGateway(false);
  }
}

/* ── 启动 ──────────────────────────────────────────────── */
async function init() {
  const boot = await window.pywebview.api.bootstrap();
  state.actions = boot.actions || [];
  renderSidebar(state.actions);
  paintGateway(!!(boot.gateway && boot.gateway.up));
  syncControls();
  setInterval(refreshGateway, 30000);
}

if (window.pywebview && window.pywebview.api) {
  init();
} else {
  window.addEventListener('pywebviewready', init);
}
