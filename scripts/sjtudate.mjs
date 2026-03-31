#!/usr/bin/env node
/**
 * SJTU Date CLI — 交大校园匹配平台 API 客户端
 * 
 * Usage:
 *   node sjtudate.mjs login <email> <password>
 *   node sjtudate.mjs profile
 *   node sjtudate.mjs match
 *   node sjtudate.mjs match-history
 *   node sjtudate.mjs round-status
 *   node sjtudate.mjs shoot-received
 *   node sjtudate.mjs stats
 *   node sjtudate.mjs survey
 *   node sjtudate.mjs dashboard
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONFIG_DIR = path.join(process.env.HOME, '.openclaw/skills-data/sjtu-date');
const TOKEN_FILE = path.join(CONFIG_DIR, 'token.json');
const BASE_URL = 'https://sjtudate.com/api';

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
  fs.writeFileSync(TOKEN_FILE, JSON.stringify({ token, email, saved_at: new Date().toISOString() }), 'utf8');
}

async function api(endpoint, options = {}) {
  const token = loadToken();
  const headers = {
    'Content-Type': 'application/json',
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
  
  // API 返回 { code, message, data: { token, ... } }
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

async function dashboard() {
  const { status, data } = await api('/dashboard');
  if (status === 200) {
    console.log('🏠 Dashboard:');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 获取 Dashboard 失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function shoot(targetEmail) {
  const { status, data } = await api('/shoot', {
    method: 'POST',
    body: JSON.stringify({ target_email: targetEmail }),
  });
  if (status === 200) {
    console.log('💘 心动发送成功！');
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.error(`❌ 发送心动失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

async function emailPreferences() {
  const { status, data } = await api('/settings/email');
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

async function submitSurvey(answersJson) {
  let answers;
  try {
    answers = JSON.parse(answersJson);
  } catch {
    console.error('❌ JSON 解析失败，请检查格式');
    process.exit(1);
  }
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
    const answers = data.data || data;
    console.log(JSON.stringify(answers, null, 2));
  } else {
    console.error(`❌ 获取答案失败 (${status}):`, JSON.stringify(data));
  }
  return data;
}

const commands = {
  login: () => login(args[0], args[1]),
  profile: () => profile(),
  match: () => match(),
  'match-history': () => matchHistory(),
  'round-status': () => roundStatus(),
  'shoot-received': () => shootReceived(),
  shoot: () => shoot(args[0]),
  stats: () => stats(),
  survey: () => survey(),
  dashboard: () => dashboard(),
  'email-prefs': () => emailPreferences(),
  time: () => time(),
  'submit-survey': () => submitSurvey(args[0]),
  'get-answers': () => getAnswers(),
};

if (!cmd || !commands[cmd]) {
  console.log(`SJTU Date CLI — 交大校园匹配平台

Usage:
  node sjtudate.mjs <command> [args]

Commands:
  login <email> <password>  登录并保存 token
  profile                   查看个人资料
  match                     查看最新匹配结果
  match-history             查看历史匹配记录
  round-status              查看当前轮次状态
  shoot-received            查看收到的心动
  shoot <email>             给对方发送心动
  stats                     平台统计数据
  survey                    查看问卷信息
  dashboard                 查看 Dashboard
  email-prefs               邮件偏好设置
  time                      服务器时间
  submit-survey '<json>'    提交问卷答案（JSON数组）
  get-answers               获取当前问卷答案`);
  process.exit(0);
}

commands[cmd]().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});
