---
name: sjtu-canvas
version: 1.0.0
license: MIT
description: |
  上海交通大学全能校园助手。覆盖 Canvas 作业管理、课程评价、校园匹配、校园生活、学术工具等 21 项功能。
  触发场景:
  (1) 查看/追踪作业DDL、提交状态、成绩
  (2) 下载课件、AI总结、作业辅导
  (3) 同步DDL到Apple日历
  (4) 查询课程评价、对比老师评分
  (5) 查看交大邮箱未读、搜索、发邮件
  (6) 食堂推荐、查菜单
  (7) 查教学周、校历、校园巴士时刻
  (8) 查图书馆、空教室
  (9) 查正版软件、镜像换源
  (10) 交大新闻、教务通知
  (11) 搜索往年课程资源（传承交大）
  (12) 查生存手册
  (13) 生成交大PPT
  (15) SJTU Date 匹配助手：一句话填问卷、查看匹配结果、自动破冰邮件、心动管理
  (14) 提交作业、助教批改
  (15) 搜索/浏览水源社区帖子
  触发词: Canvas, 课程, 作业, DDL, 截止, 成绩, 课件, PPT, 总结, 复习, 提交作业, 讨论区, 批改, 食堂, 吃什么, 图书馆, 教室, 空教室, 巴士, 校车, 教学周, 第几周, 校历, 放假, 邮箱, 邮件, 选课, 评价, 老师怎么样, 软件, MATLAB, Office, 镜像, pip, conda, 换源, 新闻, 教务, 通知, 传承, 往年, 试卷, 生存手册, 保研, 转专业, GPA, PPT模板, 手写, 水源, 水源社区, 论坛, 帖子, sjtudate, 配对, 匹配, 心动, date, 问卷, 填问卷, 脱单, 找对象, 找男朋友, 找女朋友, 破冰
---

# 上海交通大学全能校园助手

## 配置

- 配置文件: `config.json`（从 `config.example.json` 复制并填入凭证）
- Canvas URL: `https://oc.sjtu.edu.cn`
- 当前用户的课程列表通过 Canvas API 自动获取
- 所有脚本位于 `scripts/` 目录，用 `python3` 执行
- PPT 模板位于 `templates/`

---

## 🔴 刚需功能（每周都用）

### 1. DDL 追踪

**触发**: "我有什么作业"、"DDL"、"截止"、"未交作业"

```bash
python3 scripts/canvas_api.py ddls        # 未交作业 + 倒计时
python3 scripts/canvas_api.py ddls-all    # 学期全景报告
```

### 2. DDL → Apple 日历

**触发**: "同步日历"、"导出DDL"、"导入日历"

```bash
python3 scripts/sjtu_timetable_ics.py ddls ~/Desktop/ddls.ics
python3 scripts/calendar_sync.py          # macOS 直接同步
```

### 3. 教学周 / 校历

**触发**: "今天第几周"、"教学周"、"校历"、"什么时候放假"

```bash
python3 scripts/sjtu_info.py week         # 当前第几周
python3 scripts/sjtu_info.py calendar     # 完整学期校历
```

### 4. 教务通知

**触发**: "教务通知"、"教务处"、"选课通知"、"考试安排"

```bash
python3 scripts/sjtu_news.py jwc 10
```

---

## 🟠 高频功能（每月多次）

### 5. 课程评价

**触发**: "课程评价"、"老师怎么样"、"选课参考"、"评分"

> ⚠️ course.sjtu.plus 有 CDN 反爬机制，推荐通过 OpenClaw 浏览器代理模式使用（AI 自动处理认证）。

```bash
python3 scripts/sjtu_course_review.py search 传热学
python3 scripts/sjtu_course_review.py compare 燃烧学
python3 scripts/sjtu_course_review.py detail <course_id>
```

### 6. 交大邮箱

**触发**: "邮箱"、"邮件"、"未读"、"发邮件"

```bash
python3 scripts/sjtu_mail.py unread --limit 10
python3 scripts/sjtu_mail.py search -k "作业"
python3 scripts/sjtu_mail.py summary
python3 scripts/sjtu_mail.py send --to someone@sjtu.edu.cn --subject "标题" --body "正文"
```

凭证从 `config.json` 自动读取。

### 7. 食堂推荐

**触发**: "吃什么"、"食堂"、"推荐"、"菜单"

```bash
python3 scripts/sjtu_canteen.py recommend
python3 scripts/sjtu_canteen.py list
python3 scripts/sjtu_canteen.py menu 二餐
```

### 8. 传承交大

**触发**: "往年试卷"、"课程资源"、"传承"、"笔记"

```bash
python3 scripts/sjtu_legacy.py search "传热学"
python3 scripts/sjtu_legacy.py popular
```

### 9. 交大新闻

**触发**: "交大新闻"、"学校新闻"

```bash
python3 scripts/sjtu_news.py news 10
python3 scripts/sjtu_news.py all
```

---

## 🟡 实用功能（需要时用）

### 10. 图书馆

**触发**: "图书馆"、"开馆时间"、"座位"

```bash
python3 scripts/sjtu_library.py info
python3 scripts/sjtu_library.py seats
```

### 11. 空教室

**触发**: "空教室"、"哪里有教室"、"自习"

```bash
python3 scripts/sjtu_classroom.py empty
python3 scripts/sjtu_classroom.py empty --building 东上院
```

### 12. 交大 PPT

**触发**: "做PPT"、"PPT模板"、"生成PPT"

```bash
python3 scripts/generate_ppt.py --list-templates
python3 scripts/generate_ppt.py \
  --title "标题" \
  --markdown content.md \
  --template "0.上海交通大学通用PPT模板.pptx" \
  --output output.pptx
```

模板目录: `templates/`

### 13. 正版软件

**触发**: "正版软件"、"MATLAB"、"Office"

```bash
python3 scripts/sjtu_software.py list
python3 scripts/sjtu_software.py search "MATLAB"
```

### 14. 校园巴士

**触发**: "校车"、"巴士"、"闵行到徐汇"

```bash
python3 scripts/sjtu_info.py bus
```

### 15. 生存手册

**触发**: "生存手册"、"保研"、"转专业"、"GPA"

```bash
python3 scripts/sjtu_survive.py toc
python3 scripts/sjtu_survive.py search "保研"
python3 scripts/sjtu_survive.py read "GPA"
```

---

## 🟢 工具功能

### 16. 镜像换源

**触发**: "换源"、"pip源"、"镜像"

```bash
python3 scripts/sjtu_mirror.py pip
python3 scripts/sjtu_mirror.py conda
python3 scripts/sjtu_mirror.py brew
python3 scripts/sjtu_mirror.py docker
python3 scripts/sjtu_mirror.py npm
python3 scripts/sjtu_mirror.py list
```

### 17. 在线工具

**触发**: "LaTeX"、"在线工具"、"OCR"

```bash
python3 scripts/sjtu_tools.py list
```

### 18. 视觉交大

**触发**: "校园照片"、"校园风景"

```bash
python3 scripts/sjtu_visual.py albums
python3 scripts/sjtu_visual.py search "图书馆"
```

---

## 📚 Canvas 高级功能

### 课件下载 + AI 总结

```bash
python3 scripts/canvas_api.py courses
python3 scripts/canvas_api.py files <course_id>
python3 scripts/canvas_api.py download <course_id> <filename>
```

下载后用 `scripts/file_extractor.py` 提取文本内容。

### 成绩查询

```bash
python3 scripts/canvas_api.py grades
```

### 提交作业

⚠️ **提交前必须向用户确认课程、作业和文件**

```python
from scripts.canvas_api import submit_assignment
submit_assignment(course_id, assignment_id, [file_paths])
```

### 全自动作业流水线

```bash
python3 scripts/auto_homework.py scan
python3 scripts/auto_homework.py urgent 24
python3 scripts/auto_homework.py context <course_id> <assignment_id>
```

### 手写 PDF 生成

```bash
python3 scripts/handwrite_pdf.py input.txt output.pdf --style casual
# 风格: neat(工整) casual(随意) messy(潦草)
```

字体目录: `fonts/`（12 款手写字体）

---

---

## 💧 水源社区

**触发**: "水源"、"水源社区"、"论坛"、"帖子"、"搜帖子"

> 只读模式：仅支持搜索和浏览，不支持发帖/回复等写操作。

```bash
# 搜索话题
node scripts/shuiyuan_discourse.mjs search "选课"

# 查看话题详情
node scripts/shuiyuan_discourse.mjs topic <topic_id>

# 按分类浏览
node scripts/shuiyuan_discourse.mjs categories
```

**凭证配置**（三选一，按优先级）：

1. **config.json**（推荐）：填入 `shuiyuan_user_api_key` 和 `shuiyuan_user_api_client_id`
2. **环境变量**：设置 `SHUIYUAN_USER_API_KEY` 和 `SHUIYUAN_USER_API_CLIENT_ID`
3. **交互授权**：
```bash
node scripts/shuiyuan_discourse.mjs auth init
# 按提示完成授权后：
node scripts/shuiyuan_discourse.mjs auth finish --payload "<payload>"
```
授权后凭证存储于 `~/.openclaw/skills-data/shuiyuan-discourse/auth.json`。

---

## 依赖

```bash
pip3 install requests beautifulsoup4 python-pptx pdfplumber handright Pillow reportlab
```

水源社区功能额外需要 Node.js（v18+）。

## 注意事项

1. **提交作业** 前必须向用户确认
2. Canvas Token 失效时需在 oc.sjtu.edu.cn → 设置 → 新建访问许可证 重新生成
3. 选课社区受 CDN 反爬限制，推荐通过浏览器代理调用
4. 食堂、教室等部分数据为硬编码，如有变动需更新脚本
5. 校园巴士时刻表以学校最新通知为准
