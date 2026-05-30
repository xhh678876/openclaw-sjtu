---
name: sjtu
version: 2.1.0
license: MIT
description: |
  上海交通大学全能校园助手 —— 一组平台无关的命令行脚本，任何能执行 shell 的 AI agent 都可接入
  (Claude Code / Codex / Cursor / Gemini CLI / LangChain / 自建 agent 皆可)，不依赖任何特定网关、
  浏览器代理或私有运行时。覆盖 Canvas 作业/成绩、选课社区课评、传承交大资料、交大邮箱、校园生活、
  学术工具、水源社区等 20+ 项功能。
  触发场景:
  (1) 查看/追踪作业 DDL、提交状态、成绩 (Canvas)
  (2) 同步 DDL 到 Apple 日历 / 导出 .ics
  (3) 查询课程评价、对比老师评分 (选课社区 jCourse)
  (4) 搜往年试卷 / 课程资料 (传承交大)
  (5) 查交大邮箱未读 / 搜索 / 发信
  (6) 食堂推荐、图书馆、空教室、校园巴士、教学周、校历
  (7) 教务通知、交大新闻、正版软件、生存手册、在线工具
  (8) 生成交大 PPT、手写 PDF、校园官方图库
  (9) 搜索 / 浏览水源社区帖子
  触发词: Canvas, 课程, 作业, DDL, 截止, 成绩, 课件, PPT, 总结, 复习, 提交作业, 批改,
  食堂, 吃什么, 图书馆, 教室, 空教室, 巴士, 校车, 教学周, 第几周, 校历, 放假, 邮箱, 邮件,
  选课, 评价, 老师怎么样, 软件, MATLAB, Office, 新闻, 教务, 通知, 传承, 往年, 试卷,
  生存手册, 保研, 转专业, GPA, PPT模板, 手写, 校园地图, 视觉交大, 水源, 水源社区, 论坛, 帖子
---

# 上海交通大学全能校园助手 (sjtu)

> **平台无关。** 本 skill 是 `scripts/` 下的一组独立 CLI 脚本（Python3 / Node.js）。任何能运行
> shell 命令、读文件的 agent 都能调用——不依赖任何特定网关、浏览器代理或私有运行时。
> 凭证集中在仓库根 `config.json`（已被 `.gitignore` 忽略，不会进版本库）。

---

## 一、给 Agent 的调用约定（必读）

1. **执行前先 `cd ~/openclaw-sjtu`**。脚本按仓库根定位 `config.json` / `templates/` / `fonts/`，
   不在此目录会找不到配置或资源。
2. **调用形式**：Python 脚本用 `python3 scripts/<名>.py <子命令> [参数]`；
   `.mjs` 脚本用 `node scripts/<名>.mjs <子命令>`（**水源用 node，不是 python3**）。
   不带参数一般打印用法。
3. **凭证**：统一放仓库根 `config.json`（从 `config.example.json` 复制）。**按需填**——只填要用的
   功能对应字段即可。部分脚本也支持等价环境变量（见 §2）。
4. **写操作必须先确认**：会改服务器/外部状态的命令（发邮件、传承下载消耗积分等），执行前必须向
   用户复述对象并取得确认。本文档用 ⚠️ 标出。注：Canvas **提交作业当前未暴露为 CLI 子命令**
   （仅库函数 `submit_assignment`），不会被误触发。
5. **缺凭证 = 明确报错**：脚本不会假装成功。缺 key/token 会打印「缺什么、怎么配」，多数带 `selftest`。
6. **状态语义**：✅实时=真实抓线上数据；📌静态=内置离线数据（稳定但非实时，跨学期可能过期）；
   🔑需登录=缺凭证会明确报错；⚙️本地=纯本地生成；⚠️注意=有依赖缺失或接口变更，见说明。
7. **环境提示**：macOS **无 `timeout` 命令**，文档示例都不用 timeout，脚本自带超时，直接运行即可。

---

## 二、配置 (config.json)

从 `config.example.json` 复制为 `config.json`，按需填写：

| 配置字段 | 用于功能 | 怎么获取 |
|----------|----------|----------|
| `canvas_token` | Canvas 全套（DDL/课程/成绩/课件/作业/日历） | oc.sjtu.edu.cn → 头像 → 设置 → 「+ 新建访问许可证」 |
| `canvas_profiles` + `canvas_default_profile` | Canvas 学生/教师双身份 | 各生成一个 token，分别填到 `canvas_profiles.student.token` / `.teacher.token`，默认身份填 `canvas_default_profile` |
| `base_url` | Canvas 站点 | 默认 `https://oc.sjtu.edu.cn`，一般不用改 |
| `save_dir` | 课件下载目录 | 默认 `~/Downloads/Canvas课件` |
| `jcourse_api_key` | 选课社区课评 | course.sjtu.plus → 个人中心 → API 密钥 |
| `dyweb_token` | 传承交大资料 | jAccount 登录后抓 token（见 §3.5） |
| `sjtu_username` / `sjtu_password` | 交大邮箱 IMAP/SMTP | 邮箱账号 + 密码（或授权码） |
| `shuiyuan_user_api_key` + `shuiyuan_user_api_client_id` | 水源社区 | 脚本内 `auth init` 链接授权（见 §3.7） |

**等价环境变量**（优先级高于 config.json）：`JCOURSE_API_KEY`、`DYWEB_TOKEN`、`OPENCLAW_SJTU_CANVAS_PROFILE`。

> 🔒 `config.json` 已在 `.gitignore`，含真实凭证，**切勿 `git add`**。只提交 `config.example.json`（占位符）。

---

## 三、功能 × 入口 × 认证 × 状态 总表

| 功能 | 入口脚本 | 认证 | 状态 |
|------|----------|------|------|
| Canvas 课程 / DDL / 成绩 / 身份 | `canvas_api.py` | canvas_token | ✅ 实时 |
| 自动作业扫描 / 作答上下文 / 新作业监测 | `auto_homework.py` | canvas_token | ✅ 实时 |
| DDL+课程 → .ics 日历文件 | `sjtu_timetable_ics.py` | canvas_token | ✅ 实时 |
| DDL → macOS 日历同步 | `calendar_sync.py` | canvas_token | ⚙️ 本地(仅 macOS) |
| 课程评价 / 老师对比 (jCourse) | `sjtu_course_review.py` | jcourse_api_key | ✅ 实时 |
| 传承交大 往年资料 / 试卷 | `sjtu_legacy.py` | dyweb_token | 🔑 需登录 |
| 交大邮箱 未读 / 搜索 / 发信 | `sjtu_mail.py` | 邮箱账密 | 🔑 需登录 |
| 教务通知 / 交大新闻 | `sjtu_news.py` | 无 | ✅ 实时 |
| 正版软件查询 | `sjtu_software.py` | 无 | ✅ 实时 |
| 生存手册 | `sjtu_survive.py` | 无 | ✅ 实时 |
| 视觉交大 官方图库 | `sjtu_visual.py` | 无 | ✅ 实时 |
| 水源社区 (只读) | `shuiyuan_discourse.mjs` | shuiyuan_user_api_key | ✅ 实时 |
| 课件文本提取（配合 Canvas） | `file_extractor.py` | 无 | ✅ 本地 |
| 教学周 / 校历 / 校园巴士 | `sjtu_info.py` | 无 | 📌 静态 |
| 食堂推荐 / 菜单 | `sjtu_canteen.py` | 无 | 📌 静态 |
| 图书馆 信息 / 座位说明 | `sjtu_library.py` | 无 | 📌 静态 |
| 空教室 / 教学楼清单 | `sjtu_classroom.py` | 无 | 📌 静态 |
| 在线工具目录 | `sjtu_tools.py` | 无 | 📌 静态 |
| 交大 PPT 生成 | `generate_ppt.py` | 无 | ⚙️ 本地(需 python-pptx) |
| 手写 PDF 生成 | `handwrite_pdf.py` | 无 | ⚠️ 需装 handright |
| 镜像换源指引 | `sjtu_mirror.py` | 无 | ⚙️ 本地(list 接口已变) |

---

## 四、功能详解

> 每条都标注了**真实子命令**（已逐行核对源码 + 实跑）。脚本帮助里写 `python3 sjtu_xxx.py`，从仓库根
> 调用时实际路径是 `scripts/sjtu_xxx.py`。

### 4.1 Canvas 课程 / DDL / 成绩 ✅ — `canvas_api.py`

需 `canvas_token`。**CLI 仅 5 个只读子命令**，全局 `--profile <name>` 可放命令前后任意位置切换
学生/教师身份（缺省用 `canvas_default_profile`）。无参数时默认执行 `courses`。

```bash
python3 scripts/canvas_api.py me                       # 验证 token + 显示当前身份(学生/教师)
python3 scripts/canvas_api.py courses                  # 列出所有课程: [课程ID] 课程名 [角色]
python3 scripts/canvas_api.py ddls                     # 未来未提交作业, 按截止排序(🔴<24h/🟡<72h/🟢)
python3 scripts/canvas_api.py ddls-all                 # 本学期DDL全景: 统计+待交+老师反馈
python3 scripts/canvas_api.py grades                   # 各课已评分作业的得分
python3 scripts/canvas_api.py --profile teacher courses # 教师端: 管理课程/全班提交/成绩册
```
- 课程 ID 从 `courses` 输出取，用于其它需要 course_id 的脚本。
- DDL 走 Canvas Planner API 一次性拉取（含 submitted/graded/late/missing/feedback）；时区固定 UTC+8。
- ⚠️ 课件下载、作业提交、讨论区、日历事件等是**库函数，未做成 CLI 子命令**；提交作业需另调
  `canvas_api.submit_assignment(...)` 并确认，普通调用不会触发写操作。
- `ddls-all` 的学期起始日在源码里硬编码（`2026-02-17`），跨学期需改源码。
- 依赖 `requests`；需能访问 oc.sjtu.edu.cn（校园网或可达网络）。

### 4.2 自动作业流水线 ✅ — `auto_homework.py`

需 `canvas_token`。5 个子命令（无参默认 `scan`）：

```bash
python3 scripts/auto_homework.py scan                  # 扫所有未提交作业, 按剩余时间升序(只读)
python3 scripts/auto_homework.py urgent 24             # 只看 N 小时内截止(默认48)(只读)
python3 scripts/auto_homework.py context <course_id> <assignment_id>  # 拉题面+下载图片/课件, 生成 ai_prompt.md
python3 scripts/auto_homework.py full <course_id> <assignment_id>     # 同 context + 提示后续提交步骤
python3 scripts/auto_homework.py watch                 # 对比上次状态, 报新增作业(写 .homework_state.json, 适配 cron)
```
- `context`/`full` 会向 `~/Downloads/Canvas作业上下文/` 与 `~/Downloads/Canvas课件/` **下载文件**；
  生成的 `ai_prompt.md` 可喂 LLM 辅助作答。**本身不提交作业**。
- `context`/`full` 提取课件正文需 `python-pptx` / `pdfplumber` / `python-docx`（缺失则该文件标注「需安装」，不崩）。

### 4.3 DDL → 日历 ✅ / ⚙️ — `sjtu_timetable_ics.py` + `calendar_sync.py`

需 `canvas_token`。`sjtu_timetable_ics.py` 3 个子命令，可选第二参为输出路径：

```bash
python3 scripts/sjtu_timetable_ics.py ddls [输出.ics]     # 未来DDL→ICS, 每个含截止前1h/24h两个提醒(默认 ~/Downloads/sjtu_ddls.ics)
python3 scripts/sjtu_timetable_ics.py calendar [输出.ics] # 课程日历事件→ICS(默认 ~/Downloads/sjtu_calendar.ics)
python3 scripts/sjtu_timetable_ics.py all [输出.ics]      # DDL+日历合并(默认 ~/Downloads/sjtu_timetable.ics)
python3 scripts/calendar_sync.py                         # ⚙️ 仅macOS: 直接同步未来DDL进"日历"app的"Canvas作业"日历
```
- ICS 双击即可导入 Apple/Google 日历。`calendar` / `all` 的学期区间硬编码 `2026-02-17→2026-07-15`。
- `calendar_sync.py` 无参数、无 flag，运行即写本机日历（按事件标题去重）；首次需在 macOS
  「系统设置→隐私与安全性→自动化」授予终端/Python 控制「日历」权限。

### 4.4 课程评价 / 老师对比（选课社区 jCourse）✅ — `sjtu_course_review.py`

走 jCourse 开放 API（Bearer key），无需 cookie / 浏览器。需 `jcourse_api_key`。

```bash
python3 scripts/sjtu_course_review.py search 传热学      # 搜课(名称/课号/老师)
python3 scripts/sjtu_course_review.py detail 6807       # 课程详情 + 同课号其他老师评分对比
python3 scripts/sjtu_course_review.py reviews 6807 5    # 看某门课的评价(前5条)
python3 scripts/sjtu_course_review.py compare 传热学     # 同名课不同老师评分横向对比
python3 scripts/sjtu_course_review.py selftest         # 自检 API Key 与连通性
```
搜索结果与详情里的 `#数字` 是课程 ID，传给 `detail` / `reviews`。

### 4.5 传承交大 往年资料 / 试卷 🔑 — `sjtu_legacy.py`

传承新站（beta.share.dyweb.sjtu.cn）**强制 jAccount 登录，无免登录接口**。先拿 token：

```bash
# 方式A(推荐): 浏览器登一次自动抓 token
python3 scripts/save_sjtu_cookies.py legacy
# 方式B: config.json 填 dyweb_token (F12 → Application → Local Storage 的 token)
# 方式C: export DYWEB_TOKEN=...
```
拿到 token 后：
```bash
python3 scripts/sjtu_legacy.py search 传热学      # 搜课程
python3 scripts/sjtu_legacy.py course <课程ID>    # 课程详情
python3 scripts/sjtu_legacy.py materials <课程ID> # 某课程的资料列表
python3 scripts/sjtu_legacy.py selftest          # 检查 token 与连通性
```
⚠️ 下载资料会消耗站内积分，本工具只列清单**不自动下载**。

### 4.6 交大邮箱 🔑 — `sjtu_mail.py`

需 `sjtu_username` / `sjtu_password`（IMAP 993 / SMTP 465，走 mail.sjtu.edu.cn，**需校园网/VPN**）。
凭证也可用 `-u/-p` 临时传（优先于 config.json）。

```bash
python3 scripts/sjtu_mail.py unread --limit 10            # 未读邮件(不标记已读)
python3 scripts/sjtu_mail.py search --keyword 作业        # 按主题+发件人搜(可缩写 -k)
python3 scripts/sjtu_mail.py summary                      # 邮箱概况(总数/未读/最近5封)
python3 scripts/sjtu_mail.py send --to x@sjtu.edu.cn --subject "标题" --body "正文" [--html]  # ⚠️ 发信
```
⚠️ `send` 会真发邮件（From=登录账号），执行前**必须**向用户确认收件人/主题/正文。

### 4.7 水源社区（只读）✅ — `shuiyuan_discourse.mjs`（用 node）

需 `shuiyuan_user_api_key`（首次走链接授权）。Node.js ≥18，**严格只读**（代码层只允许 GET + 路径白名单，
不能发帖/回复/点赞）。访问 shuiyuan.sjtu.edu.cn 通常需校园网/VPN。

```bash
# 首次授权(链接授权)
node scripts/shuiyuan_discourse.mjs auth init                       # 生成授权链接
node scripts/shuiyuan_discourse.mjs auth finish --payload "<payload>"  # 浏览器授权后粘回 payload
node scripts/shuiyuan_discourse.mjs auth status                     # 查看凭证状态
# 日常只读
node scripts/shuiyuan_discourse.mjs search "选课" --max-results 10  # 全文搜索(支持 #分类 @用户 order:likes topic:<id> 等算子)
node scripts/shuiyuan_discourse.mjs latest --max-results 30        # 最新话题
node scripts/shuiyuan_discourse.mjs categories                     # 全部版块(id/名称/帖数)
node scripts/shuiyuan_discourse.mjs topic <topic_id> --post-limit 5  # 看某话题及楼层正文
node scripts/shuiyuan_discourse.mjs post <post_id>                # 看单楼正文
node scripts/shuiyuan_discourse.mjs filter "category:xx tags:yy"  # Discourse 过滤式
node scripts/shuiyuan_discourse.mjs image <图片URL> --output meta # 安全取帖内图片(meta/data-url/media-path)
node scripts/shuiyuan_discourse.mjs vision-check                  # 检查模型是否支持图片输入
```
- 凭证存 `~/.openclaw/skills-data/shuiyuan-discourse/auth.json`（0600）。
- 限流（429）会被规整为 `rate_limited:true` 并给重试间隔，等几十秒重试同一命令即可。
- 全局选项：`--site` / `--runtime auto|node|curl` / `--timeout` / `--auth-file` 等。

---

## 五、信息查询与校园生活

### 教务通知 / 交大新闻 ✅（实时）— `sjtu_news.py`

```bash
python3 scripts/sjtu_news.py jwc 10              # 教务处通知(标题/日期/摘要/链接)
python3 scripts/sjtu_news.py news 10            # 交大要闻
python3 scripts/sjtu_news.py news 5 --column mtjj # 媒体聚焦(jdyw=要闻 / mtjj=媒体聚焦)
python3 scripts/sjtu_news.py news 5 --json      # 结构化 JSON, 便于 agent 解析
python3 scripts/sjtu_news.py all 10             # 新闻+教务一起抓
```

### 正版软件 ✅（实时）— `sjtu_software.py`

```bash
python3 scripts/sjtu_software.py list                 # 列校内正版软件(系统/办公/科学计算/网络安全)
python3 scripts/sjtu_software.py list --category 办公  # 按类别筛选(仅 list)
python3 scripts/sjtu_software.py list --json          # JSON 输出
python3 scripts/sjtu_software.py search MATLAB        # 关键词搜
```
> 抓 software.sjtu.edu.cn；断网/解析失败会静默回退到内置 13 条数据（可能过时）。

### 生存手册 ✅（实时，GitBook）— `sjtu_survive.py`

```bash
python3 scripts/sjtu_survive.py toc              # 全书目录(来自 sitemap, 约110页)
python3 scripts/sjtu_survive.py toc gpa          # 目录按关键词过滤
python3 scripts/sjtu_survive.py search bao-yan   # 搜章节
python3 scripts/sjtu_survive.py read bao-yan     # 读章节正文
```
> GitBook 章节 slug 为**拼音**，搜索用拼音片段（`gpa` / `bao-yan` / `zhuan-zhuan-ye`）比中文更准。

### 视觉交大 官方图库 ✅（实时）— `sjtu_visual.py`

```bash
python3 scripts/sjtu_visual.py themes            # 主题相册(南洋筑韵/SJTU SCENE/航拍/运动交大…)
python3 scripts/sjtu_visual.py images 42 6       # 某主题前6张(含原图直链/尺寸/下载数)
python3 scripts/sjtu_visual.py search 图书馆      # 全站搜图
python3 scripts/sjtu_visual.py download <图片直链> [输出路径]  # 下载高清原图(常数MB)
```

### 课件文本提取 ✅（本地）— `file_extractor.py`

```bash
python3 scripts/file_extractor.py <文件>          # 单文件提取文本到 stdout(前2000字, 支持 pptx/ppt/pdf/docx/txt/md)
python3 scripts/file_extractor.py <目录>          # 批量提取目录内 pptx/pdf/docx, 打印字符数
python3 scripts/file_extractor.py <目录> <输出目录> # 批量转 Markdown 落盘(每文件一个 .md)
```
> 位置参数 CLI，无子命令。PPTX/PDF 提取需 `pip install python-pptx pdfplumber`。配合 Canvas 课件做 AI 总结。

### 教学周 / 校历 / 巴士 / 食堂 / 图书馆 / 空教室 / 在线工具 📌（静态）

```bash
python3 scripts/sjtu_info.py week                # 今天第几教学周 + 近期事件
python3 scripts/sjtu_info.py calendar            # 学期校历
python3 scripts/sjtu_info.py bus                 # 校园巴士时刻(按工作日/周末自动切换)
python3 scripts/sjtu_canteen.py list             # 列闵行 7 个食堂
python3 scripts/sjtu_canteen.py menu 二餐         # 某食堂菜单(简称: 一餐/二餐/三餐/四餐/五餐/哈乐/玉兰苑)
python3 scripts/sjtu_canteen.py recommend        # 按当前时段推荐
python3 scripts/sjtu_library.py info             # 5 个馆开放时间/位置/座位数
python3 scripts/sjtu_library.py seats            # 座位预约系统指引(非实时余量)
python3 scripts/sjtu_classroom.py empty          # 全部教学楼教室清单(77间)
python3 scripts/sjtu_classroom.py empty --building 东上院  # 按楼筛选
python3 scripts/sjtu_classroom.py info           # 教学楼概览; info --building 东上院 看单楼详情+课程时间表
python3 scripts/sjtu_tools.py list               # 12 项校内在线工具目录
python3 scripts/sjtu_tools.py latex              # 某工具详情+可达性(latex/notes/ocr/tts/ai/feedback)
```
> 📌 这几项为内置离线数据（学校无公开实时 API），每学期手工维护，跨学期可能过期。座位实时余量 /
> 真实空闲教室需 jAccount 登录教务系统，当前未实现。`sjtu_tools` 的详情命令会对 URL 做可达性探测
> （校外多显示「无法连接」属正常）。

---

## 六、生成工具 ⚙️

### 交大 PPT — `generate_ppt.py`（需 `pip install python-pptx`）

```bash
python3 scripts/generate_ppt.py --list-templates                  # 列 templates/ 下 9 个交大官方模板
python3 scripts/generate_ppt.py --title "标题" --markdown notes.md \
  --template "百廿红" --output out.pptx                            # 从 Markdown 生成多页 PPT
python3 scripts/generate_ppt.py --title "标题" --no-polish         # 关闭默认文字美化
```
- 单命令多 flag（无子命令）。`--markdown` 可传文件路径或内联文本；`##`→内容页、`#`→章节过渡页。
- `--template` 传模板名子串即可（如「百廿红」匹配 `1.百廿红-李一.pptx`）；缺省用交大通用模板。
- ⚠️ 未装 `python-pptx` 时脚本在导入阶段就退出（连 `--list-templates` 也跑不了），先装依赖。

### 手写 PDF — `handwrite_pdf.py` ⚠️（需 `pip install handright`）

```bash
python3 scripts/handwrite_pdf.py input.txt output.pdf --style casual   # 文件→手写PDF
python3 scripts/handwrite_pdf.py --text "要写的内容" out.pdf --ruled    # 直传文本, 带信纸横线
# 风格: neat(工整) / casual(随意,默认) / messy(潦草)
```
> ⚠️ 当前 `handright` 依赖**未安装**，运行会 `ModuleNotFoundError`；先 `pip install handright`
> （Pillow 已装）。字体已就绪（仓库 `fonts/` 及 workspace 下均有手写体）。

### 镜像换源指引 — `sjtu_mirror.py`

```bash
python3 scripts/sjtu_mirror.py pip               # pip 换源命令(临时/永久/配置文件)
python3 scripts/sjtu_mirror.py conda             # conda ~/.condarc
python3 scripts/sjtu_mirror.py brew              # Homebrew 环境变量
python3 scripts/sjtu_mirror.py docker            # Docker daemon.json
python3 scripts/sjtu_mirror.py npm               # npm registry
python3 scripts/sjtu_mirror.py list              # ⚠️ 列镜像(后端接口已变, 可能回退内置静态列表)
```
> `pip/conda/brew/docker/npm` 只打印换源**指引文本**，不修改任何配置文件，需用户自己执行。
> ⚠️ 仅 `list` 联网，其后端 API 已变更，结果可能不准。

---

## 七、子 Skill（独立模块，各有 SKILL.md）

主 `/sjtu` 覆盖日常功能；下列是独立成 skill 的进阶模块，多需 jAccount 登录或较重，按需委派：

| Skill | 用途 | 入口 |
|------|------|------|
| [sjtu-deadlines](skills/sjtu-deadlines/SKILL.md) | 跨平台聚合 DDL（Canvas+phycai物理实验+icourse163 MOOC+lcme实验预约） | `python3 -m scripts.unified_ddl` |
| [sjtu-oneshot](skills/sjtu-oneshot/SKILL.md) | 单次 jAccount 登录刷新所有 cookie + 拉全平台信息 | `python3 scripts/sjtu_oneshot.py` |
| [sjtu-crawler](skills/sjtu-crawler/SKILL.md) | 全站门户爬虫（50+ 站点通知）+ LLM 蒸馏成结构化 JSON | `python3 scripts/sjtu_crawler.py crawl` |
| [shuiyuan-rag-service](skills/shuiyuan-rag-service/SKILL.md) | 水源 RAG 常驻 FastAPI 服务（127.0.0.1:9111，BGE 预加载） | `uvicorn shuiyuan_rag_http:app` |
| [sjtu-cookie-saver](skills/sjtu-cookie-saver/SKILL.md) | 手动登录抓第三方站 cookie/token（主要给传承交大） | `python3 scripts/save_sjtu_cookies.py` |
| [sjtu-date](skills/sjtu-date/SKILL.md) | SJTU Date 匹配助手（填问卷/查匹配/破冰） | `node scripts/sjtudate.mjs` |
| [lobster-square](skills/lobster-square/SKILL.md) | clawsjtu.com 龙虾广场 API（独立项目，搭车存放） | `bash scripts/call.sh` |

**委派对照**（用户提到这些词时优先用对应子 skill）：
- “我有什么 DDL / 作业 / 实验”（跨平台聚合）→ **sjtu-deadlines**
- “登录所有 SJTU 平台 / 刷新所有 cookies” → **sjtu-oneshot**
- “爬交大网站 / 抓教务通知 / 蒸馏公告” → **sjtu-crawler**
- “刷新传承 / 第三方站 cookie / token” → **sjtu-cookie-saver**
- “填 SJTU Date 问卷 / 查匹配 / 脱单” → **sjtu-date**

**其他辅助脚本**（不单独成 skill）：
- `grading_assistant.py` — 助教批改助手（批量拉学生提交 + 生成评分上下文，需 Canvas 教师端 token）
- `sjtu_distill.py` — 用 Claude 把 crawler 爬下的文档蒸馏成结构化摘要

**共享工具层**：`scripts/auth/`（jAccount SSO + cookie store）、`scripts/platforms/`（各平台适配器）、
`scripts/scheduler/`（macOS launchd 服务）。

---

## 八、依赖安装

```bash
# 主功能
pip3 install requests beautifulsoup4 python-pptx pdfplumber python-docx handright Pillow reportlab
# 子 skill 额外
pip3 install -r scripts/requirements-platforms.txt    # sjtu-deadlines / sjtu-oneshot
playwright install chromium                            # sjtu-oneshot / cookie-saver(浏览器登录)
pip3 install fastapi uvicorn                           # shuiyuan-rag-service
```
- 水源、SJTU Date 等 `.mjs` 脚本需 **Node.js ≥18**（用内置 fetch，无需 npm 包）。
- 仓库自带 `.venv`，建议用它的 python 运行需第三方库的脚本（PPT/手写PDF/课件提取）。

---

## 九、故障排查

| 现象 | 原因 / 处理 |
|------|-------------|
| `未配置 ... key/token` / `Canvas token not configured` | 对应功能凭证没填，按 §2 配置表补 config.json 字段 |
| Canvas 401 / token 失效 | oc.sjtu.edu.cn 重新生成访问许可证，更新 `canvas_token` |
| jCourse 课评报错 | 先 `selftest`；key 失效则 course.sjtu.plus 重新生成 |
| 传承交大 `LoginRequired` | token 缺失/过期，重跑 `save_sjtu_cookies.py legacy` |
| 邮箱连接超时 | IMAP/SMTP 需校园网或 VPN（mail.sjtu.edu.cn） |
| 水源返回 429 | 站点限流，正常现象，等几十秒重试同一命令 |
| `ModuleNotFoundError: handright` | 手写PDF 缺依赖，`pip install handright` |
| `❌ 缺少 python-pptx` | PPT 生成缺依赖，`pip install python-pptx` |
| `[提取失败: No module named 'pptx'/'pdfplumber']` | 课件提取缺依赖，`pip3 install python-pptx pdfplumber` |
| 部分子 skill 连不上（phycai/lcme） | 需校园网或 VPN |
| `command not found: timeout`（macOS） | 文档示例无需 timeout，脚本自带超时，直接运行 |

---

## 十、注意事项

1. **写操作**（发邮件 / 传承下载消耗积分）执行前必须向用户确认。Canvas 提交作业未做成 CLI，需显式调库函数。
2. **凭证失效**：Canvas token、jCourse key、传承 token 失效时按 §9 重新生成。
3. **📌 静态数据**项（食堂 / 校历 / 巴士 / 教室 / 教学周 / 在线工具）为内置离线数据，跨学期可能过期。
4. **校园网**：邮箱、水源、部分子 skill（phycai/lcme）需校园网或 VPN。
5. `config.json` 含真实凭证，已被 git 忽略，**切勿提交**；只提交 `config.example.json`（占位符）。
6. ⚠️ 已知待修：`sjtu_mirror.py` list 后端接口已变更；`handwrite_pdf.py` 需先装 handright。
