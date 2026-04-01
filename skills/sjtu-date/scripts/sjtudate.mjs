#!/usr/bin/env node
/**
 * CampusDate CLI — 校园恋爱匹配平台 API 客户端
 * (升级自 SJTU Date，支持 trycampusdate.com)
 * 
 * Usage:
 *   node sjtudate.mjs login <email> <password>
 *   node sjtudate.mjs profile
 *   node sjtudate.mjs update-profile '<json>'
 *   node sjtudate.mjs match
 *   node sjtudate.mjs match-history
 *   node sjtudate.mjs round-status
 *   node sjtudate.mjs join-round <roundId>
 *   node sjtudate.mjs leave-round
 *   node sjtudate.mjs shoot <email> [note]
 *   node sjtudate.mjs shoot-received
 *   node sjtudate.mjs stats
 *   node sjtudate.mjs survey
 *   node sjtudate.mjs submit-survey '<json>'
 *   node sjtudate.mjs get-answers
 *   node sjtudate.mjs email-prefs
 *   node sjtudate.mjs time
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONFIG_DIR = path.join(process.env.HOME, '.openclaw/skills-data/sjtu-date');
const TOKEN_FILE = path.join(CONFIG_DIR, 'token.json');
const BASE_URL = 'https://trycampusdate.com/api';
const SCHOOL_CODE = 'sjtu';

// ─── helpers ───

function loadToken() {
  try {
    const data = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf8'));
    return data.token;
  } catch {
    return null;
  }
}

function saveToken(token, email) {
  fs.mkdirSync(CONFIG_DIR, { recursive: true });
  fs.writeFileSync(TOKEN_FILE, JSON.stringify({
    token, email,
    saved_at: new Date().toISOString(),
    base_url: BASE_URL,
    school_code: SCHOOL_CODE
  }), 'utf8');
}

async function api(endpoint, options = {}) {
  const token = loadToken();
  const headers = {
    'Content-Type': 'application/json',
    'X-School-Code': SCHOOL_CODE,
    ...(options.headers || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${BASE_URL}${endpoint}`;
  const resp = await fetch(url, {
    ...options,
    headers,
  });

  if (resp.status === 401) {
    console.error('❌ 登录已过期，请重新登录: node sjtudate.mjs login <email> <password>');
    process.exit(1);
  }

  const text = await resp.text();
  try {
    return { status: resp.status, data: JSON.parse(text) };
  } catch {
    return { status: resp.status, data: text };
  }
}

// ─── commands ───

async function login(email, password) {
  console.log(`🔐 登录 ${email}...`);
  const { status, data } = await api('/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  
  const inner = data.data || data;
  if ((status === 200 || data.code === 200) && inner.token) {
    saveToken(inner.token, email);
    console.log('✅ 登录成功！Token 已保存');
    if (inner.nickname) console.log(`   昵称: ${inner.nickname}`);
    if (inner.email) console.log(`   邮箱: ${inner.email}`);
    if (inner.dept) console.log(`   院系: ${inner.dept}`);
    if (inner.grade) console.log(`   年级: ${inner.grade}`);
    if (inner.avatar) console.log(`   头像: ${inner.avatar}`);
    if (inner.userId) console.log(`   用户ID: ${inner.userId}`);
    console.log(`   问卷: ${inner.surveyDone ? '已填' : '未填'}`);
    return inner;
  } else {
    console.error(`❌ 登录失败 (${status}):`, JSON.stringify(data));
    process.exit(1);
  }
}

async function profile() {
  const { status, data } = await api('/user/profile');
  if (status === 200) {
    console.log('👤 个人资料:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取资料失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function updateProfile(fieldsJson) {
  let fields;
  try { fields = JSON.parse(fieldsJson); } catch { console.error('❌ JSON 解析失败'); process.exit(1); }
  const { status, data } = await api('/user/profile', {
    method: 'PUT',
    body: JSON.stringify(fields),
  });
  if (status === 200 || (data && data.code === 200)) {
    console.log('✅ 资料更新成功！');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 更新失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function match() {
  const { status, data } = await api('/rounds/latest-result');
  if (status === 200) {
    console.log('💘 最新匹配结果:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取匹配失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function matchHistory() {
  const { status, data } = await api('/rounds/match-history');
  if (status === 200) {
    console.log('📜 匹配历史:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取历史失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function roundStatus() {
  const { status, data } = await api('/rounds/status');
  if (status === 200) {
    console.log('🔄 当前轮次状态:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取状态失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function joinRound(roundId) {
  console.log(`🎯 加入第 ${roundId} 轮配对...`);
  const { status, data } = await api(`/rounds/${roundId}/join`, { method: 'POST' });
  if (status === 200 || (data && data.code === 200)) {
    console.log('✅ 已加入当前轮次！');
  } else {
    console.error(`❌ 加入失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function leaveRound() {
  const { status, data } = await api('/rounds/leave', { method: 'DELETE' });
  if (status === 200 || (data && data.code === 200)) {
    console.log('✅ 已退出当前轮次');
  } else {
    console.error(`❌ 退出失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function shoot(targetEmail, note) {
  const { status, data } = await api('/shoot', {
    method: 'POST',
    body: JSON.stringify({ targetEmail, note: note || '' }),
  });
  if (status === 200 || (data && data.code === 200)) {
    console.log('💘 心动发送成功！');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 发送心动失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function shootReceived() {
  const { status, data } = await api('/shoot/received');
  if (status === 200) {
    console.log('💝 收到的心动:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取心动失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function stats() {
  const { status, data } = await api('/stats');
  if (status === 200) {
    console.log('📊 平台统计:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取统计失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function survey() {
  const { status, data } = await api('/survey');
  if (status === 200) {
    console.log('📋 问卷信息:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取问卷失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function submitSurvey(answersJson) {
  let answers;
  try { answers = JSON.parse(answersJson); } catch { console.error('❌ JSON 解析失败'); process.exit(1); }
  console.log(`📋 提交问卷（${answers.length} 道题）...`);
  const { status, data } = await api('/answers', {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
  if (status === 200 || (data && data.code === 200)) {
    console.log('✅ 问卷提交成功！');
  } else {
    console.error(`❌ 提交失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function getAnswers() {
  const { status, data } = await api('/answers');
  if (status === 200) {
    console.log(JSON.stringify(data.data || data, null, 2));
  } else {
    console.error(`❌ 获取答案失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function emailPreferences() {
  const { status, data } = await api('/email-preferences');
  if (status === 200) {
    console.log('📧 邮件偏好设置:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取邮件设置失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function time() {
  const { status, data } = await api('/time');
  if (status === 200) {
    console.log('⏰ 服务器时间:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取时间失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

// ─── main ───

const [,, cmd, ...args] = process.argv;

const commands = {
  login: () => login(args[0], args[1]),
  profile: () => profile(),
  'update-profile': () => updateProfile(args[0]),
  match: () => match(),
  'match-history': () => matchHistory(),
  'round-status': () => roundStatus(),
  'join-round': () => joinRound(args[0]),
  'leave-round': () => leaveRound(),
  'shoot-received': () => shootReceived(),
  shoot: () => shoot(args[0], args[1]),
  stats: () => stats(),
  survey: () => survey(),
  'submit-survey': () => submitSurvey(args[0]),
  'get-answers': () => getAnswers(),
  'email-prefs': () => emailPreferences(),
  time: () => time(),
};

if (!cmd || !commands[cmd]) {
  console.log(`CampusDate CLI — 校园恋爱匹配平台 (trycampusdate.com)

Usage:
  node sjtudate.mjs <command> [args]

Commands:
  login <email> <password>     登录并保存 token
  profile                      查看个人资料
  update-profile '<json>'      更新资料（nickname/avatar/dept/grade/contactType/contactValue）
  match                        查看最新匹配结果
  match-history                查看历史匹配记录
  round-status                 查看当前轮次状态
  join-round <roundId>         加入指定轮次
  leave-round                  退出当前轮次
  shoot <email> [note]         给对方发送心动
  shoot-received               查看收到的心动
  stats                        平台统计数据
  survey                       查看问卷信息
  submit-survey '<json>'       提交问卷答案（JSON数组）
  get-answers                  获取当前问卷答案
  email-prefs                  邮件偏好设置
  time                         服务器时间`);
  process.exit(0);
}

commands[cmd]().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});
