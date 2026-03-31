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

```bash
cd ~/.openclaw/workspace/skills/openclaw-sjtu
python3 scripts/setup.py
```

交互式配置向导会引导你逐步设置所有服务凭证（Canvas / 邮箱 / 选课社区 / 水源社区），自动测试连接，生成 `config.json`。

> 也可以手动复制 `cp config.example.json config.json` 后编辑。
>
> **各服务凭证获取方式：**
> - **Canvas Token**：登录 [oc.sjtu.edu.cn](https://oc.sjtu.edu.cn) → 左下角「设置」→「新建访问许可证」→ 复制 Token
> - **jAccount**：用于交大邮箱（IMAP/SMTP），建议使用应用专用密码
> - **选课社区 Cookie**：通过浏览器登录 [course.sjtu.plus](https://course.sjtu.plus) 后导出 cookie
> - **水源社区 API Key**：运行 `node scripts/shuiyuan_discourse.mjs auth init` 按提示授权

### 3. 开始使用

直接和 AI 对话即可：

- *"我有什么作业没交？"*
- *"帮我查一下传热学的课程评价"*
- *"今天吃什么？"*
- *"帮我把 DDL 同步到日历"*

---

## 📖 使用指南

### 📋 DDL 追踪

```bash
# 查看未交作业 + 倒计时
python3 scripts/canvas_api.py ddls

# 本学期全景报告
python3 scripts/canvas_api.py ddls-all

# 导出到日历（双击 .ics 导入 Apple 日历）
python3 scripts/sjtu_timetable_ics.py ddls ~/Desktop/ddls.ics
```

### ⭐ 课程评价

> ⚠️ course.sjtu.plus 有 CDN 反爬机制，推荐通过 OpenClaw 浏览器代理模式使用。

```bash
python3 scripts/sjtu_course_review.py search 传热学
python3 scripts/sjtu_course_review.py compare 燃烧学
python3 scripts/sjtu_course_review.py detail <course_id>
```

### 📧 交大邮箱

```bash
python3 scripts/sjtu_mail.py unread --limit 10
python3 scripts/sjtu_mail.py search -k "期末"
python3 scripts/sjtu_mail.py send --to someone@sjtu.edu.cn --subject "标题" --body "正文"
```

### 🍽️ 食堂推荐

```bash
python3 scripts/sjtu_canteen.py recommend   # 按时段智能推荐
python3 scripts/sjtu_canteen.py list        # 所有食堂信息
python3 scripts/sjtu_canteen.py menu 二餐   # 指定食堂菜单
```

### 🎨 PPT 生成

```bash
python3 scripts/generate_ppt.py --list-templates
python3 scripts/generate_ppt.py \
  --title "我的报告" \
  --markdown content.md \
  --template "0.上海交通大学通用PPT模板.pptx" \
  --output report.pptx
```

### 🪞 镜像换源

```bash
python3 scripts/sjtu_mirror.py pip      # pip
python3 scripts/sjtu_mirror.py conda    # conda
python3 scripts/sjtu_mirror.py brew     # Homebrew
python3 scripts/sjtu_mirror.py docker   # Docker
python3 scripts/sjtu_mirror.py npm      # npm
```

### 📚 更多功能

```bash
# 校园信息
python3 scripts/sjtu_info.py week           # 当前教学周
python3 scripts/sjtu_info.py bus            # 校园巴士时刻
python3 scripts/sjtu_info.py calendar       # 学期校历

# 图书馆 & 教室
python3 scripts/sjtu_library.py info
python3 scripts/sjtu_classroom.py empty --building 东上院

# 正版软件
python3 scripts/sjtu_software.py list
python3 scripts/sjtu_software.py search MATLAB

# 新闻 & 通知
python3 scripts/sjtu_news.py news 10        # 交大新闻
python3 scripts/sjtu_news.py jwc 10         # 教务通知

# 传承交大
python3 scripts/sjtu_legacy.py search "传热学"
python3 scripts/sjtu_legacy.py popular

# 生存手册
python3 scripts/sjtu_survive.py search "保研"
python3 scripts/sjtu_survive.py read "GPA"

# 在线工具
python3 scripts/sjtu_tools.py list

# 水源社区
node scripts/shuiyuan_discourse.mjs search "选课"
node scripts/shuiyuan_discourse.mjs topic <topic_id>
```

---

## 📸 实战效果

> 以下为真实运行输出（已脱敏），展示 AI 助手的实际使用效果。

### 📋 "我有什么作业没交？"

```
📋 4 个未交作业：
  🟡 [数据结构] 作业8 → 2026-04-01 23:59 (32h)
  🟢 [大学物理] 物理作业七 → 2026-04-04 23:59 (104h)
  🟢 [大学物理] 物理作业八 → 2026-04-07 23:59 (176h)
  🟢 [工程热力学] 第二次作业 → 2026-04-09 23:59 (224h)
```

### 🗓️ "今天第几周？"

```
🗓️  教学周信息
========================================
  📅 第 6 教学周 周二
  📅 日期: 2026-03-31 周二
  🏫 学期: 2025-2026学年 春季学期

  📌 近期事件:
     🌸 清明节放假 (4/4-4/6) (2026-04-04)
```

### 🍽️ "现在吃什么？"

```
🎯 食堂推荐 — 下午茶/小吃时段 (16:25)
============================================================

🧋 奶茶
   🏠 推荐: 玉兰苑
   💬 理由: 厝内小眷村，校内奶茶天花板

☕ 咖啡
   🏠 推荐: 瑞幸(三餐旁) / Timo(一餐旁) / 交佼(四餐旁)
   💬 理由: 校内咖啡选择不少

🍞 面包糕点
   🏠 推荐: 思源面包(一餐旁)
   💬 理由: 新鲜出炉，下午茶好搭档
```

### 📰 "有什么教务通知？"

```
📰 教务处通知
────────────────────────────────────────────────────
  1. 2026年全国大学生英语竞赛上海交大赛区准考证打印通知 [2026-03-30]
     📝 各位同学大家好! 准考证已公布，请尽快登录报名网站自行打印...
     🔗 https://jwc.sjtu.edu.cn/info/1222/125441.htm

  2. 上海交通大学2025-2026学年夏季学期选课通知 [2026-03-23]
     📝 夏季学期（7月6日-8月2日）开设培养计划内实习实践类课程...
     🔗 https://jwc.sjtu.edu.cn/info/1222/125311.htm

  3. 2026年上半年全国大学英语四、六级考试报名通知 [2026-03-16]
     📝 笔试6月13日（星期六），口试5月23-24日...
     🔗 https://jwc.sjtu.edu.cn/info/1222/125221.htm
```

### 🏛️ "图书馆几点关门？"

```
📚 上海交通大学图书馆信息
============================================================

🏛️  闵行校区主馆（新图书馆）
   📍 位置: 闵行校区中心位置，思源湖畔
   🕐 开放: 周一至周日 8:00-22:30
   🕐 考试季: 7:30-23:30
   💺 座位: 约 2000 个

🏛️  包玉刚图书馆
   📍 位置: 闵行校区西区
   🕐 开放: 周一至周日 8:00-22:30
   🕐 联楼: 24小时开放（全年）
   💺 座位: 约 1500 个
```

### 🚌 "校车几点发车？"

```
🚌 校园巴士时刻表 (工作日)
=======================================================

  🚍 闵行→徐汇
     路线: 闵行校区东川路大门 → 徐汇校区华山路大门
     耗时: 约40-60分钟
     班次:
       07:00 | 07:20 | 07:40 | 08:00 | 08:30 | 09:00
       09:30 | 10:00 | ... | 18:00 | 19:00 | 20:30 | 21:30
```

### 📚 "有没有往年试卷资源？"

```
🔥 热门课程资源
──────────────────────────────────────────────

📂 数学 (3 门)
   • 高等数学     数学科学学院    [大一必修, 理工科基础]
   • 线性代数     数学科学学院    [大一必修, 理工科基础]
   • 概率论与数理统计 数学科学学院    [大二, 理工科基础]

📂 计算机 (3 门)
   • 数据结构     电院    [大二, 计算机专业核心]
   • 操作系统     电院    [大三, 计算机专业核心]
   • 计算机网络    电院    [大三, 计算机专业核心]

共 25 门课程资源
💡 更多资源请访问: https://share.dyweb.sjtu.cn
```

### 🖥️ "交大有什么免费软件？"

```
🖥️  上海交通大学正版软件列表
────────────────────────────────────────────────────

📁 办公软件 (4 款)
   • 微软Office    • WPS Office    • 福昕PDF    • 金山文档

📁 科学计算 (6 款)
   • MATLAB    • LabVIEW    • ChemDraw
   • Siemens NX    • Gaussian    • 北太天元

📁 系统 & 安全 (3 款)
   • Windows    • VirtualBox    • ESET NOD32

共 13 款正版软件可用
下载地址: https://software.sjtu.edu.cn
```

### 📖 "搜一下保研相关的"

```
🔍 搜索: "保研"
────────────────────────────────────────────────────
  1. [子章节] 升学与就业 > 保研
     🔗 https://survivesjtu.gitbook.io/.../bao-yan
  2. [内容] 前言
     📝 ...保研者说、考研、破解留沪政策...
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
