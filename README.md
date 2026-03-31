<div align="center">

# 🎓 openclaw-sjtu

**上海交通大学全能 AI 校园助手**

*基于 [OpenClaw](https://github.com/nicepkg/openclaw) 的交大校园 Skill 包*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey.svg)]()

覆盖作业追踪、课程评价、校园生活、学术工具等 **20 项功能**，专为交大本科生打造。

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
cp config.example.json config.json
# 编辑 config.json，填入你的凭证
```

> **获取 Canvas Token：** 登录 [oc.sjtu.edu.cn](https://oc.sjtu.edu.cn) → 左下角「设置」→「新建访问许可证」→ 复制 Token

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

## 📸 Screenshots / Demo

> 🚧 截图与演示视频即将添加，敬请期待。

---

## 🔧 技术细节

### 配置字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `canvas_token` | ✅ | Canvas API Token（在 oc.sjtu.edu.cn 设置中生成） |
| `base_url` | ✅ | Canvas 地址，固定为 `https://oc.sjtu.edu.cn` |
| `save_dir` | ❌ | 课件下载目录，默认 `~/Downloads/Canvas课件` |
| `calendar_name` | ❌ | 日历名称，默认 `Canvas作业` |
| `sjtu_username` | ❌ | jAccount 用户名（邮箱功能需要） |
| `sjtu_password` | ❌ | jAccount 密码（邮箱功能需要） |

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
