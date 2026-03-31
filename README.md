<div align="center">

# 🎓 openclaw-sjtu

**上海交通大学全能 AI 校园助手**

*基于 [OpenClaw](https://github.com/nicepkg/openclaw) 的交大校园 Skill 包*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey.svg)]()

覆盖作业追踪、课程评价、校园生活、学术工具等 **20 项功能**，专为交大学子打造。

</div>

---

## ✨ 功能总览

### 🔴 刚需级 — 每周都用

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 1 | **📋 DDL 追踪** | 未交作业一览 + 截止倒计时 | `scripts/canvas_api.py ddls` |
| 2 | **📊 DDL 全景** | 学期全部 DDL 状态、老师反馈、迟交记录 | `scripts/canvas_api.py ddls-all` |
| 3 | **📅 DDL → 日历** | 导出 ICS，一键导入 Apple / Google 日历 | `scripts/sjtu_timetable_ics.py ddls` |
| 4 | **🗓️ 教学周** | 当前第几周、近期校历事件 | `scripts/sjtu_info.py week` |
| 5 | **📰 教务通知** | 教务处最新通知 + 摘要 | `scripts/sjtu_news.py jwc` |

### 🟠 高频级 — 每月多次

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 6 | **⭐ 课程评价** | 搜课程、看评分、对比不同老师 | `scripts/sjtu_course_review.py` |
| 7 | **📧 交大邮箱** | 未读、搜索、发送、邮箱概况 | `scripts/sjtu_mail.py` |
| 8 | **🍽️ 食堂推荐** | 7 大食堂 + 按时段智能推荐 | `scripts/sjtu_canteen.py recommend` |
| 9 | **📚 传承交大** | 往年试卷、笔记、PPT 资源搜索 | `scripts/sjtu_legacy.py search` |
| 10 | **📰 交大新闻** | 实时爬取交大新闻网 | `scripts/sjtu_news.py news` |

### 🟡 实用级 — 需要时用

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 11 | **🏛️ 图书馆** | 5 校区馆信息 + 开放时间 + 楼层导览 | `scripts/sjtu_library.py info` |
| 12 | **🏫 空教室** | 按教学楼查空教室 + 容量 + 类型 | `scripts/sjtu_classroom.py empty` |
| 13 | **🎨 交大 PPT** | 13 套官方模板 + Markdown → PPT | `scripts/generate_ppt.py` |
| 14 | **🖥️ 正版软件** | MATLAB / Office / NX 等 13 款免费软件 | `scripts/sjtu_software.py list` |
| 15 | **🚌 校园巴士** | 闵行 ↔ 徐汇时刻表 | `scripts/sjtu_info.py bus` |
| 16 | **📖 生存手册** | 搜索 / 浏览《上海交通大学生存手册》 | `scripts/sjtu_survive.py` |

### 🟢 工具级 — 开发者友好

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 17 | **🪞 镜像换源** | pip / conda / brew / docker / npm 一键换源 | `scripts/sjtu_mirror.py` |
| 18 | **🧰 在线工具** | LaTeX / OCR / TTS 等 9 个交大工具入口 | `scripts/sjtu_tools.py list` |
| 19 | **📅 校历** | 完整学期日程 + 放假安排 + 考试周 | `scripts/sjtu_info.py calendar` |
| 20 | **💧 水源社区** | 搜索 / 浏览交大水源论坛话题与帖子 | `scripts/shuiyuan_discourse.mjs` |

---

## 🚀 快速开始

### 1. 安装

```bash
# 安装 OpenClaw（如尚未安装）
npm install -g openclaw

# 克隆到 skills 目录
git clone https://github.com/YOUR_USERNAME/openclaw-sjtu.git \
  ~/.openclaw/workspace/skills/openclaw-sjtu

# 安装 Python 依赖
pip install requests beautifulsoup4 python-pptx pdfplumber handright Pillow reportlab
```

### 2. 配置

**一键配置（推荐）：**

```bash
cd ~/.openclaw/workspace/skills/openclaw-sjtu
python3 scripts/setup.py
```

交互式向导会逐步引导你完成所有配置，自动测试连接。也可手动编辑 `config.json`，详见下方各服务认证指南。

---

## 🔑 认证配置详解

> 不是所有服务都必须配置。**只有 Canvas Token 是必填项**，其余按需开启。

### 📋 Canvas LMS（必填 · DDL / 成绩 / 课件）

Canvas 是核心功能的基础，**必须配置**。

**Step 1：** 打开浏览器，登录 [oc.sjtu.edu.cn](https://oc.sjtu.edu.cn)

**Step 2：** 点击左侧边栏最底部的「设置」（或直接访问 `oc.sjtu.edu.cn/profile/settings`）

**Step 3：** 滚动到页面底部，找到「已批准的访问许可」区域

**Step 4：** 点击「+ 新建访问许可证」

**Step 5：** 在弹窗中：
- 用途填写 `openclaw-sjtu`（随意，仅供你自己辨认）
- 点击「生成令牌」

**Step 6：** **立即复制**生成的 Token（关闭弹窗后将无法再次查看）

**Step 7：** 填入配置：
```json
{
  "canvas_token": "你复制的Token",
  "base_url": "https://oc.sjtu.edu.cn"
}
```

**验证是否成功：** 直接对 AI 说「我有什么作业没交」，看到作业列表就说明配置成功 ✅

> ⚠️ Token 没有过期时间，但你可以随时在设置页面删除并重新生成。

---

### 📧 交大邮箱（可选 · 收发邮件）

用于查看未读邮件、搜索邮件、发送邮件。通过 IMAP/SMTP 协议直连 `mail.sjtu.edu.cn`。

**Step 1：** 确认你的 jAccount 用户名（登录 jaccount.sjtu.edu.cn 时用的那个，不含 @sjtu.edu.cn）

**Step 2：** 填入配置：
```json
{
  "sjtu_username": "你的jAccount用户名",
  "sjtu_password": "你的jAccount密码"
}
```

**验证是否成功：** 对 AI 说「有没有新邮件」，看到邮件列表就说明配置成功 ✅

> 💡 **安全建议：** 如果学校支持应用专用密码，建议使用应用专用密码而非主密码。
>
> ⚠️ `config.json` 已在 `.gitignore` 中，不会被提交到 Git。但请确保不要手动上传。

---

### ⭐ 选课社区（可选 · 课程评价）

[course.sjtu.plus](https://course.sjtu.plus) 提供课程评价和老师对比功能。由于 CDN 反爬机制，**推荐两种方式**：

#### 方式 A：通过 OpenClaw 浏览器代理（推荐，零配置）

如果你的 OpenClaw 配置了浏览器代理，直接对 AI 说「帮我查传热学的课程评价」即可，AI 会自动通过浏览器完成登录和查询，**无需任何配置**。

#### 方式 B：手动填入 Cookie

**Step 1：** 打开浏览器，登录 [course.sjtu.plus](https://course.sjtu.plus)（使用 jAccount）

**Step 2：** 登录成功后，按 `F12` 打开开发者工具

**Step 3：** 切换到「Network」（网络）选项卡

**Step 4：** 刷新页面，点击任意一个请求

**Step 5：** 在「Request Headers」中找到 `Cookie` 字段，复制完整内容

**Step 6：** 填入配置：
```json
{
  "course_sjtu_cookie": "你复制的完整Cookie字符串"
}
```

**验证是否成功：** 对 AI 说「帮我查高等数学的课程评价」，看到评分就说明配置成功 ✅

> ⚠️ Cookie 有时效性，过期后需重新获取。如果查询失败，重新登录并更新 Cookie。

---

### 💧 水源社区（可选 · 论坛搜索）

[水源社区](https://shuiyuan.sjtu.edu.cn) 是交大学生的 Discourse 论坛。配置后可搜索和浏览帖子。

**前置条件：** 需要 Node.js v18+（`node --version` 检查）

#### 方式 A：交互式授权（推荐）

**Step 1：** 运行授权初始化
```bash
node scripts/shuiyuan_discourse.mjs auth init
```

**Step 2：** 脚本会输出一个授权链接，在浏览器中打开

**Step 3：** 在水源社区页面完成授权确认

**Step 4：** 页面会显示一段加密字符串（payload），复制它

**Step 5：** 回到终端，运行：
```bash
node scripts/shuiyuan_discourse.mjs auth finish --payload "你复制的payload"
```

授权完成后，凭证自动保存到 `~/.openclaw/skills-data/shuiyuan-discourse/auth.json`。

#### 方式 B：手动配置

如果你已有 API Key，直接填入 `config.json`：
```json
{
  "shuiyuan_user_api_key": "你的User API Key",
  "shuiyuan_user_api_client_id": "你的Client ID"
}
```

**验证是否成功：** 对 AI 说「搜一下水源上关于选课的讨论」，看到帖子就说明配置成功 ✅

---

### 🔒 安全须知

| 注意事项 | 说明 |
|----------|------|
| `config.json` 不会被提交 | 已在 `.gitignore` 中排除 |
| 密码明文存储 | 目前 config.json 中密码为明文，请勿将文件分享给他人 |
| Token 可随时吊销 | Canvas Token 可在设置页面删除；水源授权可在社区设置中撤销 |
| 最小权限原则 | 只配置你需要的服务，不用的留空即可 |

---

### 3. 开始使用

直接和 AI 对话即可：

- *"我有什么作业没交？"*
- *"帮我查一下传热学的课程评价"*
- *"今天吃什么？"*
- *"帮我把 DDL 同步到日历"*

---

## 📖 能干什么？直接跟 AI 聊天就行

> 装好之后**不需要记任何命令**，直接用自然语言对话。以下是最受欢迎的使用场景：

### 🔥 作业辅导 — 最核心的功能

| 你说 | AI 帮你做 |
|------|-----------|
| "我有什么作业没交？" | 拉取所有未提交作业 + 截止倒计时，紧急的排最前 |
| "帮我看看这周数学作业要求" | 读取 Canvas 作业详情 + 下载附件 + 提取题目 |
| "对照老师课件，帮我辅导这次作业" | 下载课件 → AI 提取知识点 → 对照作业题目逐题分析思路 |
| "帮我写大作业初稿，给我提供思路" | 拉取作业要求 → 参考课件 → 生成结构化初稿 + 写作建议 |
| "这道题不会，帮我讲讲" | 结合课件内容，给出解题思路和步骤 |
| "帮我把 DDL 同步到日历" | 导出 ICS，一键导入 Apple / Google 日历 |

> 💡 **工作流示例：** 你说「这周热力学作业帮我辅导一下」→ AI 自动拉取作业要求 → 下载这周课件 → 提取关键公式和知识点 → 逐题给出解题思路和参考答案框架。

### 📚 水源社区智能摘要

| 你说 | AI 帮你做 |
|------|-----------|
| "去水源帮我看看转专业相关的帖子" | 搜索水源论坛 → 汇总关键信息 → 生成摘要 |
| "水源上大家怎么评价这门课？" | 检索相关讨论 → 提炼正反方观点 → 总结 |
| "帮我看看最近保研的讨论" | 拉取最新帖子 → 整理时间线和要点 |
| "水源上有没有人讨论过 XX 实验室？" | 精准搜索 → 过滤无关内容 → 归纳核心信息 |

> 💡 你不用自己翻几十页帖子，AI 帮你读完然后总结给你。

### ⭐ 选课参谋

| 你说 | AI 帮你做 |
|------|-----------|
| "帮我查一下高等数学的评价" | 搜索选课社区评分和评价 |
| "线性代数哪个老师好？" | 拉取同一门课不同老师的评分对比 |
| "这门课给分怎么样？工作量大吗？" | 综合评分、评价、给分分布 |
| "下学期想选通识课，推荐几门？" | 结合评分 + 水源讨论 + 传承交大资源，综合推荐 |

### 🎓 学术资源 & 考试

| 你说 | AI 帮你做 |
|------|-----------|
| "有没有高数往年试卷？" | 搜索传承交大 → 列出可用资源 |
| "帮我总结这门课的重点" | 下载全部课件 → AI 提取核心知识点 → 生成复习提纲 |
| "搜一下保研相关经验" | 搜索生存手册 + 水源社区 → 综合整理 |
| "帮我做个答辩 PPT" | 用交大官方模板 + Markdown 自动生成 PPT |

### 🏫 校园日常

| 你说 | AI 帮你做 |
|------|-----------|
| "今天吃什么？" | 按当前时段智能推荐食堂 |
| "图书馆几点关门？" | 查各馆开放时间 |
| "校车几点发？" | 闵行 ↔ 徐汇巴士时刻表 |
| "今天第几周？什么时候放假？" | 教学周 + 校历 |
| "有没有新邮件？" | 查看交大邮箱未读 |
| "有什么教务通知？" | 拉取最新教务处公告 |

---

## 📸 实战效果

> 以下为真实对话场景（已脱敏），展示 AI 助手的实际使用效果。

### 🔥 "帮我看看这周有什么作业，辅导一下"

**第一步：AI 自动拉取作业列表**
```
📋 4 个未交作业：
  🟡 [数据结构] 作业8 → 2026-04-01 23:59 (32h) ⚡紧急
  🟢 [大学物理] 物理作业七 → 2026-04-04 23:59 (104h)
  🟢 [大学物理] 物理作业八 → 2026-04-07 23:59 (176h)
  🟢 [工程热力学] 第二次作业 → 2026-04-09 23:59 (224h)
```

**第二步：AI 下载课件 + 读取作业要求 → 逐题辅导**
```
📝 数据结构 作业8 辅导

题目 1: 二叉搜索树的插入与删除
  📖 参考课件: 第7讲-二叉搜索树.pdf 第12-18页
  💡 思路: 插入操作递归比较 key 值，找到空位插入；
     删除分三种情况：叶子节点直接删、单子节点替换、
     双子节点找中序后继替换后递归删除...
  ✅ 关键公式: 平均查找长度 ASL = (1/n)Σ(level_i)

题目 2: AVL 树旋转
  📖 参考课件: 第8讲-平衡二叉树.pdf 第5-11页
  💡 思路: 判断失衡类型 (LL/RR/LR/RL)，
     LL → 右旋，RR → 左旋，LR → 先左旋后右旋...
```

### 📚 "去水源帮我看看转专业相关的帖子，总结一下"

```
🔍 已搜索水源社区 "转专业"，找到 23 个相关讨论

📋 核心信息汇总：

1. 📌 转专业时间节点
   - 大一下学期 5 月提交申请
   - 各院系考核方式不同（笔试/面试/综合）
   - GPA 门槛因院系而异，热门院系（如电院）竞争激烈

2. 🔥 高频讨论话题
   - 电院/计算机转入难度大，近年录取率约 30-40%
   - 部分院系接受跨大类转入
   - 建议提前修目标院系的先修课

3. 💬 过来人建议
   - "大一上绩点很重要，转专业主要看排名"
   - "面试时展示对目标专业的了解和热情"
   - "提前联系目标院系的老师会有帮助"

📎 热门帖子:
   • 《2025转专业经验分享》 👍 186  💬 47
   • 《电院转入面试经历》 👍 124  💬 38
```

### ⭐ "下学期想选通识课，有什么推荐？"

```
🎓 综合推荐（评分 + 水源口碑 + 往年资源）

1. ⭐ 心理学导论 — 评分 4.6/5
   👨‍🏫 推荐老师: 张老师 (4.8) > 王老师 (4.2)
   💬 水源评价: "给分超好，内容有趣，期末开卷"
   📚 传承交大: 有往年试卷 + 课程笔记

2. ⭐ 科技与社会 — 评分 4.4/5
   👨‍🏫 推荐老师: 李老师 (4.5)
   💬 水源评价: "作业少，考核方式灵活"
   📚 传承交大: 有期末论文范文

3. ⭐ 音乐鉴赏 — 评分 4.3/5
   💬 水源评价: "选到就是赚到，无作业无考试"
```

### 🍽️ "今天吃什么？"

```
🎯 食堂推荐 — 下午茶/小吃时段 (16:25)
============================================================

🧋 奶茶
   🏠 推荐: 玉兰苑
   💬 理由: 厝内小眷村，校内奶茶天花板

☕ 咖啡
   🏠 推荐: 瑞幸(三餐旁) / Timo(一餐旁) / 交佼(四餐旁)

🍞 面包糕点
   🏠 推荐: 思源面包(一餐旁)
   💬 理由: 新鲜出炉，下午茶好搭档
```

---

## 🔧 技术细节

### 配置字段说明

| 字段 | 必填 | 适用功能 | 说明 |
|------|------|----------|------|
| `canvas_token` | ✅ | DDL / 课程 / 成绩 | Canvas API Token（oc.sjtu.edu.cn → 设置 → 新建访问许可证） |
| `base_url` | ✅ | Canvas 全局 | 固定为 `https://oc.sjtu.edu.cn` |
| `save_dir` | ❌ | 课件下载 | 课件保存目录，默认 `~/Downloads/Canvas课件` |
| `calendar_name` | ❌ | DDL → 日历 | Apple 日历名称，默认 `Canvas作业` |
| `sjtu_username` | ❌ | 邮箱 | jAccount 用户名 |
| `sjtu_password` | ❌ | 邮箱 | jAccount 密码（建议使用应用专用密码） |
| `course_sjtu_cookie` | ❌ | 课程评价 | 选课社区 session cookie（通过浏览器登录获取） |
| `shuiyuan_user_api_key` | ❌ | 水源社区 | 水源论坛 User API Key（通过 `auth init` 授权获取） |
| `shuiyuan_user_api_client_id` | ❌ | 水源社区 | 水源论坛 API Client ID（授权时自动生成） |

### API 端点

| 服务 | 端点 | 认证方式 |
|------|------|----------|
| Canvas LMS | `oc.sjtu.edu.cn/api/v1/` | API Token |
| 交大邮箱 | `mail.sjtu.edu.cn:993/465` | IMAP/SMTP SSL |
| 选课社区 | `course.sjtu.plus/api/` | jAccount OAuth |
| 教务处 | `jwc.sjtu.edu.cn` | 无需认证 |
| 交大新闻 | `news.sjtu.edu.cn` | 无需认证 |
| 传承交大 | `share.dyweb.sjtu.cn` | 无需认证 |
| 生存手册 | `survivesjtu.gitbook.io` | 无需认证 |
| 水源社区 | `shuiyuan.sjtu.edu.cn` | User API Key |

### 项目结构

```
openclaw-sjtu/
├── README.md
├── SKILL.md                     # OpenClaw Skill 描述
├── CONTRIBUTING.md              # 贡献指南
├── LICENSE                      # MIT License
├── config.example.json          # 配置模板
├── scripts/
│   ├── setup.py                 # 交互式配置向导
│   ├── canvas_api.py            # Canvas LMS API（DDL / 课程 / 成绩）
│   ├── calendar_sync.py         # 日历同步
│   ├── sjtu_timetable_ics.py    # DDL / 课表导出 ICS
│   ├── sjtu_info.py             # 校历、教学周、校园巴士
│   ├── sjtu_canteen.py          # 食堂信息与推荐
│   ├── sjtu_library.py          # 图书馆信息
│   ├── sjtu_classroom.py        # 空教室查询
│   ├── sjtu_software.py         # 正版软件列表
│   ├── sjtu_news.py             # 交大新闻 + 教务通知
│   ├── sjtu_mail.py             # 交大邮箱（IMAP / SMTP）
│   ├── sjtu_course_review.py    # 选课社区 API
│   ├── sjtu_legacy.py           # 传承交大（课程资源）
│   ├── sjtu_survive.py          # 生存手册
│   ├── sjtu_mirror.py           # SJTUG 镜像换源
│   ├── sjtu_tools.py            # 在线工具集合
│   ├── sjtu_visual.py           # 视觉交大
│   ├── generate_ppt.py          # PPT 生成器
│   ├── handwrite_pdf.py         # 手写体 PDF 生成
│   ├── file_extractor.py        # 课件内容提取
│   ├── auto_homework.py         # 作业自动化辅助
│   ├── grading_assistant.py     # 助教批改辅助
│   ├── shuiyuan_discourse.mjs   # 水源社区（Node.js 主力）
│   └── shuiyuan_discourse.py    # 水源社区（Python 备用）
├── fonts/                       # 手写字体（12 款）
└── templates/                   # PPT 模板（13 套）
```

---

## ⚠️ 注意事项

1. **Canvas Token** 请妥善保管，切勿提交到公开仓库
2. **邮箱密码** 建议使用应用专用密码
3. **选课社区** 受 CDN 反爬限制，推荐通过浏览器代理调用
4. 部分数据为硬编码（食堂、教室等），如有变动请提 Issue
5. 校园巴士时刻表以学校最新通知为准

---

## 🤝 贡献

欢迎交大同学参与贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📜 License

[MIT License](LICENSE) © SJTU Students

## 🙏 致谢

- [OpenClaw](https://github.com/openclaw/openclaw) — AI 助手框架
- [SJTUG](https://mirror.sjtu.edu.cn) — 镜像服务
- [传承交大](https://share.dyweb.sjtu.cn) — 课程资源共享
- [SurviveSJTU](https://survivesjtu.gitbook.io) — 生存手册
- [SJTU 选课社区](https://course.sjtu.plus) — 课程评价平台
- 水源社区 — 灵感与信息来源

---

<div align="center">

**Made with ❤️ by 交大学子，for 交大学子**

</div>
