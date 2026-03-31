---
name: sjtu-canvas
description: |
  上海交通大学全能校园助手。覆盖 Canvas 作业管理、课程评价、校园生活、学术工具等 19 项功能。
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
  (14) 提交作业、助教批改
  触发词: Canvas, 课程, 作业, DDL, 截止, 成绩, 课件, PPT, 总结, 复习, 提交作业, 讨论区, 批改, 传热学, 机械振动, 燃烧学, 热力系统, 遗传学, 食堂, 吃什么, 图书馆, 教室, 空教室, 巴士, 校车, 教学周, 第几周, 校历, 放假, 清明, 五一, 邮箱, 邮件, 选课, 评价, 老师怎么样, 软件, MATLAB, Office, 镜像, pip, conda, 换源, 新闻, 教务, 通知, 传承, 往年, 试卷, 生存手册, 保研, 转专业, GPA, PPT模板, 手写
---

# 上海交通大学全能校园助手

## 配置

- 配置文件: `skills/sjtu-canvas/config.json`
- Canvas URL: `https://oc.sjtu.edu.cn`
- 用户: 谢豪辉 (ID: 415063)
- 所有脚本位于 `skills/sjtu-canvas/scripts/`，用 `python3` 执行
- PPT 生成器位于 `skills/sjtu-ppt/scripts/generate_ppt.py`
- PPT 模板位于 `skills/sjtu-ppt/templates/`

## 当前课程 (2025-2026 春季学期)

| ID | 课程名 | 老师 | 教室 |
|---|---|---|---|
| 87891 | 传热学 | 徐治国 | 东上院206 |
| 87838 | 机械振动学 | 吴海军 | 下院307 |
| 87905 | 燃烧学 | 林赫 | 东下院408 |
| 87878 | 热力系统设计与实践 | 韩东 | 东下院313 |
| 86731 | 遗传学与社会 | 付力文 | 东下院203 |

---

## 🔴 刚需功能（每周都用）

### 1. DDL 追踪

**触发**: "我有什么作业"、"DDL"、"截止"、"未交作业"

```bash
# 查看未交作业 + 倒计时
python3 scripts/canvas_api.py ddls

# 本学期全景（全部DDL + 状态 + 老师反馈 + 迟交记录）
python3 scripts/canvas_api.py ddls-all
```

### 2. DDL → Apple 日历

**触发**: "同步日历"、"导出DDL"、"导入日历"

```bash
# 导出 ICS 文件
python3 scripts/sjtu_timetable_ics.py ddls ~/Desktop/ddls.ics
# 然后双击 .ics 即可导入 Apple 日历

# 直接同步到 Apple 日历（macOS）
python3 scripts/calendar_sync.py
```

### 3. 教学周 / 校历

**触发**: "今天第几周"、"教学周"、"校历"、"什么时候放假"、"清明"、"五一"

```bash
python3 scripts/sjtu_info.py week      # 当前第几周 + 近期事件
python3 scripts/sjtu_info.py calendar  # 完整学期校历
```

### 4. 教务通知

**触发**: "教务通知"、"教务处"、"选课通知"、"考试安排"

```bash
python3 scripts/sjtu_news.py jwc 10   # 教务处最新通知（含摘要）
```

---

## 🟠 高频功能（每月多次）

### 5. 课程评价 ⚠️

**触发**: "课程评价"、"老师怎么样"、"选课参考"、"评分"

> ⚠️ course.sjtu.plus 有 CDN 反爬，Python 脚本需要 cookie。
> **推荐方式**：通过浏览器代理调用 API（已登录 xhh666）。

浏览器代理调用方式（在 OpenClaw browser 中执行）：
```javascript
// 搜索课程
fetch('/api/search/?q=传热学&page_size=10', {credentials:'same-origin'}).then(r=>r.json())

// 课程详情 + 老师对比
fetch('/api/course/8158/', {credentials:'same-origin'}).then(r=>r.json())
```

浏览器必须先打开 course.sjtu.plus 并保持登录状态。
如果 session 过期，导航到 course.sjtu.plus/login，邮箱密码登录 tab 填入 xhh666 / xhhxhh66666 点击登录。

脚本方式（备用，需 cookie）：
```bash
python3 scripts/sjtu_course_review.py search 传热学
python3 scripts/sjtu_course_review.py compare 燃烧学
python3 scripts/sjtu_course_review.py detail 8158
```

### 6. 交大邮箱

**触发**: "邮箱"、"邮件"、"未读"、"发邮件"

```bash
python3 scripts/sjtu_mail.py unread --limit 10    # 未读邮件
python3 scripts/sjtu_mail.py search -k "作业"     # 搜索
python3 scripts/sjtu_mail.py summary              # 邮箱概况
python3 scripts/sjtu_mail.py send --to X --subject Y --body Z  # 发送
```

凭证从 config.json 自动读取（sjtu_username / sjtu_password）。

### 7. 食堂推荐

**触发**: "吃什么"、"食堂"、"推荐"、"菜单"、"哪个食堂"

```bash
python3 scripts/sjtu_canteen.py recommend   # 按当前时段智能推荐
python3 scripts/sjtu_canteen.py list        # 所有食堂信息
python3 scripts/sjtu_canteen.py menu 二餐   # 指定食堂菜单
```

### 8. 传承交大（课程资源）

**触发**: "往年试卷"、"课程资源"、"传承"、"笔记"

```bash
python3 scripts/sjtu_legacy.py search "传热学"  # 搜索课程资源
python3 scripts/sjtu_legacy.py popular          # 热门课程资源
```

### 9. 交大新闻

**触发**: "交大新闻"、"学校新闻"、"最近发生什么"

```bash
python3 scripts/sjtu_news.py news 10   # 交大新闻网
python3 scripts/sjtu_news.py all       # 新闻 + 教务 + 信息公开
```

---

## 🟡 实用功能（需要时用）

### 10. 图书馆

**触发**: "图书馆"、"开馆时间"、"座位"

```bash
python3 scripts/sjtu_library.py info    # 5馆信息 + 开放时间 + 楼层
python3 scripts/sjtu_library.py seats   # 座位预约信息
```

### 11. 空教室

**触发**: "空教室"、"哪里有教室"、"自习"

```bash
python3 scripts/sjtu_classroom.py empty                  # 所有教学楼
python3 scripts/sjtu_classroom.py empty --building 东上院  # 指定教学楼
python3 scripts/sjtu_classroom.py info --building 东上院   # 教学楼详情
```

### 12. 交大 PPT

**触发**: "做PPT"、"PPT模板"、"生成PPT"、"交大模板"

```bash
# 列出模板
python3 skills/sjtu-ppt/scripts/generate_ppt.py --list-templates

# 生成 PPT（先写 markdown 文件，再传入）
python3 skills/sjtu-ppt/scripts/generate_ppt.py \
  --title "标题" \
  --markdown content.md \
  --template "0.上海交通大学通用PPT模板.pptx" \
  --output output.pptx
```

模板目录: `skills/sjtu-ppt/templates/`（9 套）

### 13. 正版软件

**触发**: "正版软件"、"MATLAB"、"Office"、"免费软件"

```bash
python3 scripts/sjtu_software.py list             # 列出所有（13款）
python3 scripts/sjtu_software.py search "MATLAB"  # 搜索
```

### 14. 校园巴士

**触发**: "校车"、"巴士"、"去徐汇"、"闵行到徐汇"

```bash
python3 scripts/sjtu_info.py bus   # 闵行↔徐汇时刻表
```

### 15. 生存手册

**触发**: "生存手册"、"保研"、"考研"、"转专业"、"GPA"

```bash
python3 scripts/sjtu_survive.py toc              # 目录
python3 scripts/sjtu_survive.py search "保研"     # 搜索
python3 scripts/sjtu_survive.py read "GPA"        # 阅读章节
```

---

## 🟢 工具功能

### 16. 镜像换源

**触发**: "换源"、"pip源"、"镜像"、"conda源"

```bash
python3 scripts/sjtu_mirror.py pip      # pip 换源
python3 scripts/sjtu_mirror.py conda    # conda 换源
python3 scripts/sjtu_mirror.py brew     # Homebrew 换源
python3 scripts/sjtu_mirror.py docker   # Docker 换源
python3 scripts/sjtu_mirror.py npm      # npm 换源
python3 scripts/sjtu_mirror.py list     # 所有可用镜像
```

### 17. 在线工具

**触发**: "LaTeX"、"在线工具"、"OCR"、"TTS"

```bash
python3 scripts/sjtu_tools.py list   # 列出所有工具（9个）
```

### 18. 视觉交大

**触发**: "校园照片"、"校园风景"

```bash
python3 scripts/sjtu_visual.py albums          # 相册列表
python3 scripts/sjtu_visual.py search "图书馆"  # 搜索照片
```

---

## 📚 Canvas 高级功能

### 课件下载 + AI 总结

```bash
python3 scripts/canvas_api.py courses              # 列出课程
python3 scripts/canvas_api.py files <course_id>     # 课程文件列表
python3 scripts/canvas_api.py download <cid> <name> # 下载课件
```

下载后用 `file_extractor.py` 提取文本：
```bash
python3 scripts/file_extractor.py path/to/file.pptx
```

### 成绩查询

```bash
python3 scripts/canvas_api.py grades
```

### 提交作业

⚠️ **提交前必须向用户确认课程、作业和文件**

```python
from canvas_api import submit_assignment
submit_assignment(course_id, assignment_id, [file_paths])
```

### 全自动作业流水线

```bash
python3 scripts/auto_homework.py scan               # 扫描未提交
python3 scripts/auto_homework.py urgent 24           # 24h内到期
python3 scripts/auto_homework.py context <cid> <aid> # 构建作业上下文
```

### 手写 PDF 生成

```bash
python3 scripts/handwrite_pdf.py input.txt output.pdf --style casual
# 风格: neat(工整) casual(随意) messy(潦草)
```

字体目录: `skills/sjtu-canvas/fonts/`（12 款手写字体）

---

## 依赖

```bash
pip3 install requests beautifulsoup4 python-pptx pdfplumber handright Pillow reportlab
```

## 注意事项

1. **提交作业**前必须向用户确认
2. Canvas Token 失效时需重新生成（oc.sjtu.edu.cn → 设置 → 新建访问许可证）
3. 选课社区通过浏览器代理调用（CDN 反爬限制）
4. 食堂、教室等部分数据为硬编码，如有变动需更新脚本
5. 校园巴士时刻表以学校最新通知为准
