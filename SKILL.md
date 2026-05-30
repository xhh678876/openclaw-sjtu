---
name: sjtu
version: 2.0.0
license: MIT
description: |
  上海交通大学全能校园助手 —— 一组纯命令行脚本，任何能执行 shell 的 AI agent 都可接入
  (Claude Code / Codex / Cursor / Gemini CLI / 自建 agent 皆可)，无需任何特定平台或运行时。
  覆盖 Canvas 作业/成绩、选课社区课评、传承交大资料、校园生活、学术工具等 20+ 项功能。
  触发场景:
  (1) 查看/追踪作业 DDL、提交状态、成绩 (Canvas)
  (2) 下载课件、AI 总结、自动作业流水线
  (3) 同步 DDL 到 Apple 日历
  (4) 查询课程评价、对比老师评分 (选课社区 jCourse)
  (5) 搜往年试卷/课程资料 (传承交大)
  (6) 查交大邮箱、食堂、图书馆、空教室、校园巴士
  (7) 查教学周、校历、教务通知、交大新闻
  (8) 查正版软件、生存手册、在线工具
  (9) 生成交大 PPT、手写 PDF
  (10) 搜索/浏览水源社区帖子
  触发词: Canvas, 课程, 作业, DDL, 截止, 成绩, 课件, PPT, 总结, 复习, 提交作业, 批改,
  食堂, 吃什么, 图书馆, 教室, 空教室, 巴士, 校车, 教学周, 第几周, 校历, 放假, 邮箱, 邮件,
  选课, 评价, 老师怎么样, 软件, MATLAB, Office, 新闻, 教务, 通知, 传承, 往年, 试卷,
  生存手册, 保研, 转专业, GPA, PPT模板, 手写, 水源, 水源社区, 论坛, 帖子
---

# 上海交通大学全能校园助手 (sjtu)

> **平台无关。** 本 skill 就是一组 `scripts/` 下的独立 CLI 脚本（Python3 / Node.js）。
> 任何能运行 shell 命令、读文件的 agent 都能调用——Claude Code、Codex、Cursor、Gemini CLI、
> LangChain/自建 agent 都行。不依赖任何特定网关、浏览器代理或私有运行时。

## 给 Agent 的调用约定

1. **始终先 `cd ~/openclaw-sjtu` 再执行脚本**（脚本按仓库根定位 config/templates/fonts）。
2. 凭证统一放仓库根 `config.json`（已被 `.gitignore` 忽略）；多数脚本也支持等价**环境变量**。
3. 每个脚本都是 `python3 scripts/xxx.py <子命令>` 或 `node scripts/xxx.mjs <子命令>`，
   不传参或 `help` 会打印用法。
4. 凡涉及**写操作**（发邮件、提交作业、发帖、心动）的命令，执行前必须向用户确认。
5. 缺凭证时脚本会**明确报错**告诉你缺什么、怎么配——不会假装成功（见各功能 selftest）。

## 配置 (config.json)

从 `config.example.json` 复制为 `config.json` 并按需填写。**不需要全部填**——只填你要用的功能对应的凭证：

| 配置键 | 用于 | 怎么拿 |
|--------|------|--------|
| `jcourse_api_key` | 选课社区课评 | course.sjtu.plus → 个人中心 → API 密钥 |
| `canvas_token` / `canvas_profiles` | Canvas 全套 | oc.sjtu.edu.cn → 账户 → 设置 → 新建访问许可证 |
| `dyweb_token` | 传承交大 | jAccount 登录后抓 token（见下方传承小节） |
| `sjtu_username` / `sjtu_password` | 交大邮箱 | 邮箱账号 + 密码/授权码 |
| `shuiyuan_user_api_key` | 水源社区 | 脚本内 `auth init` 链接授权 |

环境变量等价物：`JCOURSE_API_KEY`、`DYWEB_TOKEN`（优先级高于 config.json）。

---

## 🔐 功能 × 认证 × 状态 总表

> 「状态」是 2026-05 实测结论。**静态数据** = 内置离线数据（非实时，但稳定可用）；
> **实时** = 真实抓取线上数据；**需登录** = 缺凭证时会明确报错。

| 功能 | 入口脚本 | 认证 | 状态 |
|------|----------|------|------|
| 课程评价 / 老师对比 | `sjtu_course_review.py` | jcourse_api_key | ✅ 实时 |
| Canvas DDL / 课程 / 成绩 | `canvas_api.py` | canvas_token | ✅ 实时 |
| 自动作业流水线 | `auto_homework.py` | canvas_token | ✅ 实时 |
| DDL → Apple 日历 | `sjtu_timetable_ics.py` | canvas_token | ✅ 实时 |
| 传承交大 资料/试卷 | `sjtu_legacy.py` | dyweb_token | 🔑 需登录 |
| 交大邮箱 | `sjtu_mail.py` | 邮箱账密 | 🔑 需登录 |
| 水源社区 (只读) | `shuiyuan_discourse.mjs` | user_api_key | ✅ 实时 |
| 交大新闻 / 教务通知 | `sjtu_news.py` | 无 | ✅ 实时 |
| 正版软件 | `sjtu_software.py` | 无 | ✅ 实时 |
| 生存手册 | `sjtu_survive.py` | 无 | ✅ 实时 |
| 视觉交大 图库 | `sjtu_visual.py` | 无 | ✅ 实时 |
| 教学周 / 校历 | `sjtu_info.py week/calendar` | 无 | 📌 静态数据 |
| 校园巴士 | `sjtu_info.py bus` | 无 | 📌 静态数据 |
| 食堂推荐 | `sjtu_canteen.py` | 无 | 📌 静态数据 |
| 图书馆 (信息) | `sjtu_library.py` | 无 | 📌 静态数据 |
| 空教室 (清单) | `sjtu_classroom.py` | 无 | 📌 静态数据 |
| 在线工具目录 | `sjtu_tools.py` | 无 | 📌 静态数据 |
| 交大 PPT | `generate_ppt.py` | 无 | ✅ 本地 |
| 手写 PDF | `handwrite_pdf.py` | 无 | ✅ 本地 |
| 镜像换源 | `sjtu_mirror.py` | 无 | ⚠️ 接口变更 |
| 视觉交大 | `sjtu_visual.py` | — | ❌ 站点已下线 |

---

## 🔴 刚需功能

### 课程评价 / 老师对比 (选课社区 jCourse) ✅

走 jCourse 开放 API（Bearer key），无需 cookie / 浏览器。

```bash
python3 scripts/sjtu_course_review.py search 传热学       # 搜课（名称/课号/老师）
python3 scripts/sjtu_course_review.py detail 6807        # 课程详情 + 同课号老师对比
python3 scripts/sjtu_course_review.py reviews 6807 5     # 某门课的评价（前5条）
python3 scripts/sjtu_course_review.py compare 传热学      # 同名课不同老师评分对比
python3 scripts/sjtu_course_review.py selftest          # 自检 key / 连通性
```

搜索结果与详情里的 `#数字` 是课程 ID，传给 `detail` / `reviews`。

### Canvas DDL / 课程 / 成绩 ✅

```bash
python3 scripts/canvas_api.py ddls                       # 未交作业（默认 profile）
python3 scripts/canvas_api.py ddls-all                   # 学期全景
python3 scripts/canvas_api.py courses                    # 课程列表
python3 scripts/canvas_api.py grades                     # 成绩（无评分时输出为空属正常）
python3 scripts/canvas_api.py --profile teacher courses  # 教师端（若配了双 profile）
```

- 学生端：查个人课程/作业/DDL/成绩/提交状态。
- 教师端：查管理课程、全班提交、成绩册。涉及「全班/课程管理」优先教师端。

### Canvas 课件下载 + 自动作业 ✅

```bash
python3 scripts/canvas_api.py files <course_id>          # 列课件
python3 scripts/canvas_api.py download <course_id> <filename>
python3 scripts/auto_homework.py scan                    # 扫未提交
python3 scripts/auto_homework.py urgent 24               # 24h 内紧急
```
下载后用 `scripts/file_extractor.py` 提取文本。⚠️ 提交作业前必须向用户确认。

### DDL → Apple 日历 ✅

```bash
python3 scripts/sjtu_timetable_ics.py ddls ~/Desktop/ddls.ics
python3 scripts/calendar_sync.py          # macOS 直接同步
```

---

## 🟠 校园生活

### 传承交大 往年资料 / 试卷 🔑

> 传承新站（beta.share.dyweb.sjtu.cn）**强制 jAccount 登录，无免登录接口**。
> 需先拿 token：`python3 scripts/save_sjtu_cookies.py legacy`（浏览器登一次自动抓 token），
> 或在 config.json 填 `dyweb_token`（F12 → Application → Local Storage 的 `token`）。

```bash
python3 scripts/sjtu_legacy.py search 传热学      # 搜课程
python3 scripts/sjtu_legacy.py course <课程ID>    # 课程详情
python3 scripts/sjtu_legacy.py materials <课程ID> # 某课的资料列表
python3 scripts/sjtu_legacy.py selftest          # 检查 token / 连通性
```
⚠️ 下载资料消耗积分，本工具不自动下载。

### 交大邮箱 🔑

```bash
python3 scripts/sjtu_mail.py unread --limit 10
python3 scripts/sjtu_mail.py search -k "作业"
python3 scripts/sjtu_mail.py summary
python3 scripts/sjtu_mail.py send --to x@sjtu.edu.cn --subject "标题" --body "正文"  # ⚠️ 发信前确认
```
凭证从 config.json 的 `sjtu_username` / `sjtu_password` 读取。

### 水源社区 (只读) ✅

```bash
node scripts/shuiyuan_discourse.mjs search "选课"
node scripts/shuiyuan_discourse.mjs topic <topic_id>
node scripts/shuiyuan_discourse.mjs categories
```
首次授权（仅链接授权方式）：
```bash
node scripts/shuiyuan_discourse.mjs auth init           # 生成授权链接
node scripts/shuiyuan_discourse.mjs auth finish --payload "<payload>"
```
凭证存 `~/.openclaw/skills-data/shuiyuan-discourse/auth.json`。需 Node.js ≥18。

### 食堂 / 图书馆 / 空教室 📌

```bash
python3 scripts/sjtu_canteen.py recommend     # 按时段推荐
python3 scripts/sjtu_canteen.py menu 二餐
python3 scripts/sjtu_library.py info          # 各馆开放时间/位置
python3 scripts/sjtu_classroom.py empty       # 教学楼教室清单
```
> 📌 这几项是内置静态数据（学校无公开实时 API）。座位/空闲实时状态需 jAccount 登录教务系统，当前未实现。

---

## 🟡 信息查询

### 教务通知 / 交大新闻 ✅（实时抓取）

```bash
python3 scripts/sjtu_news.py jwc 10              # 教务处通知（标题/日期/摘要/链接）
python3 scripts/sjtu_news.py news 10             # 交大要闻
python3 scripts/sjtu_news.py news 5 --column mtjj # 媒体聚焦栏目
python3 scripts/sjtu_news.py news 5 --json       # 结构化输出，供 agent 解析
```

### 教学周 / 校历 / 校园巴士 📌（静态数据）

```bash
python3 scripts/sjtu_info.py week          # 今天第几教学周
python3 scripts/sjtu_info.py calendar      # 学期校历
python3 scripts/sjtu_info.py bus           # 校园巴士时刻
```
> 📌 数据每学期手工维护，跨学期需更新。

### 正版软件 / 生存手册 / 在线工具 ✅📌

```bash
python3 scripts/sjtu_software.py list                    # ✅ 实时抓取
python3 scripts/sjtu_survive.py toc                      # ✅ 目录(来自 sitemap)
python3 scripts/sjtu_survive.py search bao-yan           # ✅ 按拼音 slug 搜(gpa/bao-yan/xuan-ke)
python3 scripts/sjtu_survive.py read bao-yan             # ✅ 读章节正文
python3 scripts/sjtu_tools.py list                      # 📌 静态目录
```
> 生存手册是 GitBook，章节 slug 为拼音；搜索用拼音片段（`gpa`/`bao-yan`/`zhuan-zhuan-ye`）比中文更准。

### 视觉交大 官方图库 ✅

```bash
python3 scripts/sjtu_visual.py themes               # 主题相册(南洋筑韵/SJTU SCENE/航拍/运动交大…)
python3 scripts/sjtu_visual.py images 42 6          # 某主题前6张(含原图直链/尺寸/下载数)
python3 scripts/sjtu_visual.py search 图书馆         # 全站搜图
python3 scripts/sjtu_visual.py download <图片直链>   # 下载原图
```
> vs.sjtu.edu.cn 官方校园图库，公开可下载（高清原图，多为数 MB）。

---

## 🟢 生成工具

### 交大 PPT ✅

```bash
python3 scripts/generate_ppt.py --list-templates
python3 scripts/generate_ppt.py --title "标题" --markdown content.md \
  --template "0.上海交通大学通用PPT模板.pptx" --output out.pptx
```
模板在 `templates/`；默认自动清空示例页、匹配版式、优化文字样式（`--no-polish` 关闭）。
需 `pip install python-pptx`。

### 手写 PDF ✅

```bash
python3 scripts/handwrite_pdf.py input.txt output.pdf --style casual
# 风格: neat(工整) casual(随意) messy(潦草)；字体在 fonts/（12 款手写体）
```
需 `pip install reportlab handright Pillow`。

---

## 🧩 子 Skill（独立模块，各有 SKILL.md）

主 `/sjtu` 覆盖日常功能；下列是独立成 skill 的进阶模块，多需 jAccount 登录或较重：

| Skill | 用途 | 入口 |
|------|------|------|
| [sjtu-deadlines](skills/sjtu-deadlines/SKILL.md) | 跨平台聚合 DDL (Canvas+phycai+icourse163+lcme) | `python3 -m scripts.unified_ddl` |
| [sjtu-oneshot](skills/sjtu-oneshot/SKILL.md) | 一键 jAccount 登录 + 抓全平台信息 | `python3 scripts/sjtu_oneshot.py` |
| [sjtu-crawler](skills/sjtu-crawler/SKILL.md) | 全站门户爬虫 + LLM 蒸馏 | `python3 scripts/sjtu_crawler.py crawl` |
| [shuiyuan-rag-service](skills/shuiyuan-rag-service/SKILL.md) | 水源 RAG 常驻服务 (127.0.0.1:9111) | `uvicorn shuiyuan_rag_http:app` |
| [sjtu-cookie-saver](skills/sjtu-cookie-saver/SKILL.md) | 手动登录抓第三方站 cookie/token | `python3 scripts/save_sjtu_cookies.py` |
| [lobster-square](skills/lobster-square/SKILL.md) | clawsjtu.com 龙虾广场 API（独立项目） | `bash scripts/call.sh` |

委派对照（用户提到这些词时优先用子 skill）：
- "我有什么 DDL / 作业 / 实验"（跨平台）→ **sjtu-deadlines**
- "登录所有 SJTU 平台 / 刷新所有 cookies" → **sjtu-oneshot**
- "爬交大网站 / 抓教务通知 / 蒸馏公告" → **sjtu-crawler**
- "刷新选课社区或传承 cookie / token" → **sjtu-cookie-saver**

共享工具层（不单独成 skill）：
- `scripts/auth/` — jAccount SSO + cookie store + Chrome cookies 导入
- `scripts/platforms/` — 各平台 HTTP/Playwright 适配器
- `scripts/scheduler/` — macOS launchd 服务安装/卸载

---

## 依赖

```bash
pip3 install requests beautifulsoup4 python-pptx pdfplumber handright Pillow reportlab
# 子 skill 额外：
pip3 install -r scripts/requirements-platforms.txt    # sjtu-deadlines / sjtu-oneshot
playwright install chromium                            # sjtu-oneshot / cookie-saver
pip3 install fastapi uvicorn                           # shuiyuan-rag-service
```
水源社区、SJTU Date 等 `.mjs` 脚本需 Node.js ≥18。

## 注意事项

1. **写操作**（提交作业、发邮件、发帖）执行前必须向用户确认。
2. **凭证失效**：Canvas token、jCourse key、传承 token 失效时按上表重新生成即可。
3. **📌 静态数据**项（食堂/校历/巴士/教室/教学周）为内置离线数据，跨学期可能过期。
4. **校园网**：部分子 skill（phycai/lcme）需校园网或 VPN。
5. 子 skill 命令行调用**密码不上 argv**；首次保存用 `--save-creds`，后续裸跑。
6. ⚠️ `镜像换源 sjtu_mirror.py` 接口已变更，当前列表不准，待修。
