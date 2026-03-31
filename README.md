# 🎓 openclaw-sjtu

> 上海交通大学全能 AI 助手 — 基于 [OpenClaw](https://github.com/openclaw/openclaw) 的交大校园 Skill 包

一个让 AI 助手真正理解交大校园的工具集。覆盖作业追踪、课程评价、校园生活、学术工具等 **19 项功能**，专为交大本科生打造。

## ✨ 功能总览（按学生需要程度排序）

### 🔴 刚需级 — 每周都用

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 1 | **📋 DDL 追踪** | Canvas 未交作业 + 截止倒计时 | `canvas_api.py ddls` |
| 2 | **📊 DDL 全景** | 本学期全部 DDL 状态 + 老师反馈 + 迟交记录 | `canvas_api.py ddls-all` |
| 3 | **📅 DDL → 日历** | 导出 ICS 文件，一键导入 Apple/Google 日历 | `sjtu_timetable_ics.py ddls` |
| 4 | **🗓️ 教学周** | 今天第几周、周几、近期校历事件 | `sjtu_info.py week` |
| 5 | **📰 教务通知** | 教务处面向学生的最新通知 + 摘要 | `sjtu_news.py jwc` |

### 🟠 高频级 — 每月多次

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 6 | **⭐ 课程评价** | 搜课程、看评分、对比不同老师（选课社区 API） | `sjtu_course_review.py` |
| 7 | **📧 交大邮箱** | 未读邮件、搜索、发送、邮箱概况 | `sjtu_mail.py` |
| 8 | **🍽️ 食堂推荐** | 7 个食堂信息 + 按时段智能推荐 | `sjtu_canteen.py recommend` |
| 9 | **📚 传承交大** | 往年课程资源搜索（试卷、笔记、PPT） | `sjtu_legacy.py search` |
| 10 | **📰 交大新闻** | 实时爬取交大新闻网最新消息 | `sjtu_news.py news` |

### 🟡 实用级 — 需要时用

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 11 | **🏛️ 图书馆** | 5 个校区馆信息 + 开放时间 + 楼层导览 | `sjtu_library.py info` |
| 12 | **🏫 空教室** | 按教学楼查教室列表 + 容量 + 类型 | `sjtu_classroom.py empty` |
| 13 | **🎨 交大 PPT** | 13 套官方模板 + Markdown → PPT 自动生成 | `generate_ppt.py` |
| 14 | **🖥️ 正版软件** | 13 款交大免费软件（MATLAB/Office/NX 等） | `sjtu_software.py list` |
| 15 | **🚌 校园巴士** | 闵行 ↔ 徐汇时刻表，区分工作日/周末 | `sjtu_info.py bus` |
| 16 | **📖 生存手册** | 搜索/浏览《上海交通大学生存手册》 | `sjtu_survive.py` |

### 🟢 工具级 — 开发者友好

| # | 功能 | 说明 | 脚本 |
|---|------|------|------|
| 17 | **🪞 镜像换源** | SJTUG 镜像一键配置（pip/conda/brew/docker/npm） | `sjtu_mirror.py` |
| 18 | **🧰 在线工具** | LaTeX/OCR/TTS/AI 平台等 9 个交大工具入口 | `sjtu_tools.py list` |
| 19 | **📅 校历** | 完整学期日程 + 放假安排 + 考试周 | `sjtu_info.py calendar` |

## 🚀 快速开始

### 1. 安装 OpenClaw

```bash
npm install -g openclaw
```

### 2. 安装本 Skill

```bash
# 方式一：从 GitHub
git clone https://github.com/xiehaohui/openclaw-sjtu.git ~/.openclaw/workspace/skills/openclaw-sjtu

# 方式二：从 ClawHub（即将上线）
# clawhub install openclaw-sjtu
```

### 3. 配置

复制示例配置并填入你的凭证：

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "canvas_token": "你的Canvas API Token",
  "base_url": "https://oc.sjtu.edu.cn",
  "save_dir": "~/Downloads/Canvas课件",
  "sjtu_username": "你的jAccount用户名",
  "sjtu_password": "你的jAccount密码"
}
```

**获取 Canvas Token：**
1. 登录 [oc.sjtu.edu.cn](https://oc.sjtu.edu.cn)
2. 点击左下角「设置」→ 「新建访问许可证」
3. 复制生成的 Token

### 4. 依赖

```bash
pip install requests beautifulsoup4 python-pptx
```

## 📖 详细使用指南

### 📋 DDL 追踪（最常用！）

```bash
# 查看未交作业
python3 scripts/canvas_api.py ddls

# 输出示例：
# 📋 3 个未交作业：
#   🟡 [机械振动学] 作业8 → 2026-04-01 23:59 (36h)
#   🟢 [燃烧学] 作业七 → 2026-04-04 23:59 (108h)
#   🟢 [热力系统] 第二次作业 → 2026-04-09 23:59 (228h)

# 本学期全景报告
python3 scripts/canvas_api.py ddls-all

# 导出到日历
python3 scripts/sjtu_timetable_ics.py ddls ~/Desktop/ddls.ics
# 然后双击 .ics 文件即可导入 Apple 日历
```

### ⭐ 课程评价

> ⚠️ course.sjtu.plus 有 CDN 反爬机制，Python requests 无法直接调用。
> 推荐通过 OpenClaw 浏览器代理模式使用（AI 助手自动处理认证）。

```bash
# CLI 模式（需要先配置 cookie）
python3 scripts/sjtu_course_review.py search 传热学
python3 scripts/sjtu_course_review.py compare 燃烧学
python3 scripts/sjtu_course_review.py detail 8158

# OpenClaw 模式（推荐，直接对话）
# 跟 AI 说："帮我查一下燃烧学的课程评价"
```

### 📧 交大邮箱

```bash
# 查看未读邮件
python3 scripts/sjtu_mail.py unread --limit 10

# 搜索邮件
python3 scripts/sjtu_mail.py search --keyword "作业"

# 邮箱概况
python3 scripts/sjtu_mail.py summary

# 发送邮件
python3 scripts/sjtu_mail.py send --to someone@sjtu.edu.cn --subject "标题" --body "正文"
```

### 🍽️ 食堂推荐

```bash
# 查看所有食堂
python3 scripts/sjtu_canteen.py list

# 智能推荐（根据当前时段）
python3 scripts/sjtu_canteen.py recommend

# 查看特定食堂菜单
python3 scripts/sjtu_canteen.py menu 二餐
```

### 🎨 交大 PPT 生成

```bash
# 列出可用模板
python3 scripts/generate_ppt.py --list-templates

# 从 Markdown 生成 PPT
python3 scripts/generate_ppt.py \
  --title "我的报告" \
  --markdown content.md \
  --template "0.上海交通大学通用PPT模板.pptx" \
  --output report.pptx
```

支持 13 套官方模板：

| 模板 | 风格 | 设计者 |
|------|------|--------|
| 通用PPT模板 | 官方标准 | 学校官方 |
| 百廿红 | 校庆红色 | 李一 |
| 简单蓝 | 简洁学术 | 沈小丹 |
| 暗夜奔驰 | 深色科技 | 徐臻 |
| 赤霞银珠 | 优雅渐变 | 徐臻 |
| 酒红醉人 | 暖色商务 | 徐臻 |
| 天空之境 | 蓝色清新 | 潘冬远、张娉 |
| 深海金芒 | 深蓝金色 | 许歆瑶 |
| 浩瀚星河 | 星空主题 | 迮佳 |
| 鎏金岁月 | 复古金色 | 陈玥彤 |

### 🪞 镜像换源

```bash
# 列出所有可用镜像
python3 scripts/sjtu_mirror.py list

# 一键配置各工具换源
python3 scripts/sjtu_mirror.py pip      # pip 换源
python3 scripts/sjtu_mirror.py conda    # conda 换源
python3 scripts/sjtu_mirror.py brew     # Homebrew 换源
python3 scripts/sjtu_mirror.py docker   # Docker 换源
python3 scripts/sjtu_mirror.py npm      # npm 换源
```

### 📚 更多功能

```bash
# 校园信息
python3 scripts/sjtu_info.py week       # 当前教学周
python3 scripts/sjtu_info.py bus        # 校园巴士时刻
python3 scripts/sjtu_info.py calendar   # 学期校历

# 图书馆
python3 scripts/sjtu_library.py info    # 各馆信息

# 教室查询
python3 scripts/sjtu_classroom.py empty                  # 所有教学楼
python3 scripts/sjtu_classroom.py empty --building 东上院  # 指定教学楼

# 正版软件
python3 scripts/sjtu_software.py list           # 列出所有
python3 scripts/sjtu_software.py search MATLAB  # 搜索

# 新闻与通知
python3 scripts/sjtu_news.py news 10   # 交大新闻
python3 scripts/sjtu_news.py jwc 10    # 教务通知
python3 scripts/sjtu_news.py all       # 全部

# 传承交大（课程资源）
python3 scripts/sjtu_legacy.py search "传热学"
python3 scripts/sjtu_legacy.py popular

# 生存手册
python3 scripts/sjtu_survive.py toc              # 目录
python3 scripts/sjtu_survive.py search "保研"     # 搜索
python3 scripts/sjtu_survive.py read "GPA"        # 阅读

# 在线工具
python3 scripts/sjtu_tools.py list      # 列出所有工具
```

## 📁 项目结构

```
openclaw-sjtu/
├── README.md                    # 本文件
├── SKILL.md                     # OpenClaw Skill 描述
├── config.example.json          # 配置模板
├── scripts/
│   ├── canvas_api.py            # Canvas LMS API（DDL/课程/成绩）
│   ├── sjtu_info.py             # 校历、教学周、校园巴士
│   ├── sjtu_canteen.py          # 食堂信息与推荐
│   ├── sjtu_library.py          # 图书馆信息
│   ├── sjtu_classroom.py        # 空教室查询
│   ├── sjtu_software.py         # 正版软件列表
│   ├── sjtu_news.py             # 交大新闻 + 教务通知
│   ├── sjtu_mail.py             # 交大邮箱（IMAP/SMTP）
│   ├── sjtu_course_review.py    # 选课社区 API
│   ├── sjtu_legacy.py           # 传承交大（课程资源）
│   ├── sjtu_survive.py          # 生存手册
│   ├── sjtu_mirror.py           # SJTUG 镜像换源
│   ├── sjtu_tools.py            # 在线工具集合
│   ├── sjtu_visual.py           # 视觉交大
│   ├── sjtu_timetable_ics.py    # DDL/课表导出 ICS
│   ├── generate_ppt.py          # PPT 生成器（在 ppt/ 目录）
│   ├── handwrite_pdf.py         # 手写体 PDF 生成
│   ├── file_extractor.py        # 课件内容提取
│   ├── auto_homework.py         # 作业自动化辅助
│   ├── grading_assistant.py     # 助教批改辅助
│   └── calendar_sync.py         # 日历同步
├── fonts/                       # 手写字体（12款）
├── templates/                   # PPT 模板（13套）
└── references/                  # 参考文档
```

## 🔧 技术细节

### API 端点

| 服务 | 端点 | 认证方式 |
|------|------|----------|
| Canvas LMS | `oc.sjtu.edu.cn/api/v1/` | API Token |
| 交大邮箱 | `mail.sjtu.edu.cn:993/465` | IMAP/SMTP SSL |
| 选课社区 | `course.sjtu.plus/api/` | jAccount OAuth (httpOnly cookie) |
| 教务处 | `jwc.sjtu.edu.cn` | 无需认证（爬虫） |
| 交大新闻 | `news.sjtu.edu.cn` | 无需认证（爬虫） |
| 传承交大 | `share.dyweb.sjtu.cn` | 无需认证 |
| 生存手册 | `survivesjtu.gitbook.io` | 无需认证 |

### 同类项目对比

| 项目 | 学校 | 功能数 | 特色 |
|------|------|--------|------|
| **openclaw-sjtu** | 上海交通大学 | **19** | Canvas+邮箱+选课社区+PPT+生活全覆盖 |
| KU Portal | 高丽大学 | ~8 | 课表、成绩为主 |

### 差异化优势

- 🎯 **选课社区集成**：唯一接入 course.sjtu.plus API 的工具
- 🎨 **PPT 自动生成**：13 套官方模板 + Markdown → PPT
- 📧 **邮箱管理**：IMAP 直连，收发搜索全功能
- 🍽️ **校园生活**：食堂推荐、巴士时刻、图书馆一站式
- 📚 **学术资源**：传承交大 + 生存手册 + 正版软件
- 🤖 **AI 原生**：为 OpenClaw AI 助手设计，对话式交互

## 📝 注意事项

1. **Canvas Token** 请妥善保管，不要提交到公开仓库
2. **邮箱密码** 建议使用应用专用密码
3. **选课社区** 需要通过浏览器登录（CDN 反爬限制）
4. 部分数据为硬编码（食堂、教室），如有变动请提 Issue
5. 校园巴士时刻表以学校最新通知为准

## 🤝 贡献

欢迎交大同学贡献代码！

- 提 Issue 报告 bug 或建议新功能
- Fork + PR 贡献代码
- 完善硬编码数据（食堂菜单、教室信息等）

## 📜 License

MIT License

## 🙏 致谢

- [OpenClaw](https://github.com/openclaw/openclaw) — AI 助手框架
- [SJTUG](https://mirror.sjtu.edu.cn) — 镜像服务
- [传承交大](https://share.dyweb.sjtu.cn) — 课程资源共享
- [SurviveSJTU](https://survivesjtu.gitbook.io) — 生存手册
- [SJTU选课社区](https://course.sjtu.plus) — 课程评价平台
- 水源社区 — 灵感与信息来源

---

**Made with ❤️ by 交大学子，for 交大学子**
