---
name: sjtu-canvas
description: |
  SJTU Canvas 课程助手。管理上海交通大学 Canvas (oc.sjtu.edu.cn) 课程数据。
  触发场景:
  (1) 查看/下载课程文件(PPT/PDF)、批量下载课件
  (2) 查看作业列表、DDL、提交状态、提交作业
  (3) 同步作业DDL到Apple日历(Mac+iPhone)
  (4) PPT/PDF内容提取和AI总结、课件学习
  (5) 作业辅导(提取作业要求+课件内容→给思路)
  (6) 查看成绩、计算均分
  (7) 课程讨论区摘要
  (8) 视频字幕总结
  (9) DDL预警提醒
  (10) 期末复习包生成(所有课件→Markdown→NotebookLM)
  (11) 一键提交作业
  (12) 全自动作业流水线(扫描→课件RAG→生成答案→提交)
  (13) 助教批改模式(拉取提交→提取内容→AI评分建议→批量打分)
  触发词: Canvas, 课程, 作业, DDL, 截止, 成绩, 课件, PPT, 总结, 复习, 提交作业, 讨论区, 传热学, 机械振动, 燃烧学, 热力系统, 遗传学, 自动做作业, 批改, 打分, 助教
---

# SJTU Canvas 课程助手

## 配置

- Token 和设置: `skills/sjtu-canvas/config.json`
- Canvas 基础 URL: `https://oc.sjtu.edu.cn`
- 用户 ID: 415063 (谢豪辉)

## 当前课程 (2025-2026 学期)

| ID | 课程名 |
|---|---|
| 87891 | 传热学 |
| 87838 | 机械振动学 |
| 87905 | 燃烧学 |
| 87878 | 热力系统设计与实践 |
| 86731 | 遗传学与社会 |

## 核心脚本

所有脚本位于 `skills/sjtu-canvas/scripts/`，用 python3 执行。

### canvas_api.py — Canvas API 交互

```bash
# 列出课程
python3 scripts/canvas_api.py courses

# 查看所有未来DDL
python3 scripts/canvas_api.py ddls

# 查看已出成绩
python3 scripts/canvas_api.py grades
```

Python 中调用:
```python
import sys; sys.path.insert(0, "skills/sjtu-canvas/scripts")
from canvas_api import *

list_courses()                          # 课程列表
list_assignments(course_id)             # 作业列表
get_all_upcoming_ddls()                 # 所有未来DDL
get_course_grades(course_id)            # 成绩
list_course_files(course_id)            # 课程文件
download_course_files(cid, name, dir)   # 批量下载
list_discussions(course_id)             # 讨论区
get_full_discussion(cid, topic_id)      # 讨论详情
submit_assignment(cid, aid, [paths])    # 提交作业
```

### file_extractor.py — 课件内容提取

```bash
# 提取单个文件
python3 scripts/file_extractor.py path/to/file.pptx

# 批量提取目录 → Markdown
python3 scripts/file_extractor.py ~/Downloads/Canvas课件/传热学 ~/Downloads/Canvas课件/传热学_md
```

支持格式: `.pptx` `.pdf` `.docx` `.txt` `.md`

### calendar_sync.py — DDL → Apple 日历

```bash
cd skills/sjtu-canvas && python3 scripts/calendar_sync.py
```

自动创建「Canvas作业」日历分类，已存在的事件不会重复创建。通过 iCloud 同步到 iPhone。

### auto_homework.py — 全自动作业流水线 🆕

```bash
# 扫描所有未提交作业（按紧急程度排序）
python3 scripts/auto_homework.py scan

# 查看 N 小时内到期的紧急作业
python3 scripts/auto_homework.py urgent 24

# 检测新增作业（与上次巡检对比，适合 cron）
python3 scripts/auto_homework.py watch

# 为指定作业构建完整上下文（下载课件 + 提取内容 + 生成 AI prompt）
python3 scripts/auto_homework.py context <course_id> <assignment_id>

# 完整流水线（构建上下文 + 准备提交）
python3 scripts/auto_homework.py full <course_id> <assignment_id>
```

Python 中调用:
```python
from auto_homework import *

scan_unsubmitted()                              # 扫描未提交作业列表
get_urgent_assignments(hours=48)                # 紧急作业
check_new_assignments()                         # 新作业检测（有状态）
build_homework_context(course_id, assignment_id) # 构建作业上下文
get_assignment_detail(course_id, assignment_id)  # 作业详情（含图片解析）
```

**全自动作业流水线工作流：**
1. `scan` 扫描未提交作业
2. `context` 自动下载相关课件 → 提取内容 → 解析题目图片 → 生成 AI prompt
3. Agent 读取 prompt 文件 + 课件上下文，生成解答
4. 用户确认后 → `submit_assignment()` 提交
5. 可设置 `watch` 配合 cron 自动巡检新作业

### grading_assistant.py — 助教批改助手 🆕

```bash
# 查看作业的所有学生提交
python3 scripts/grading_assistant.py submissions <course_id> <assignment_id>

# 下载所有学生提交的文件
python3 scripts/grading_assistant.py download <course_id> <assignment_id>

# 生成批改上下文（下载 + 提取 + AI prompt）
python3 scripts/grading_assistant.py context <course_id> <assignment_id>

# 给学生打分（需要助教/教师权限）
python3 scripts/grading_assistant.py grade <cid> <aid> <user_id> <score> [comment]
```

Python 中调用:
```python
from grading_assistant import *

list_submissions(course_id, assignment_id)          # 提交列表
download_submission_files(course_id, assignment_id)  # 下载所有提交
build_grading_context(course_id, assignment_id)      # 构建批改上下文
grade_submission(cid, aid, user_id, score, comment)  # 单个打分
batch_grade(cid, aid, grades_list)                   # 批量打分
```

**助教批改工作流：**
1. `submissions` 查看提交列表和状态
2. `context` 自动下载所有提交 → 提取内容 → 生成批改 prompt
3. Agent 读取 prompt 文件，根据作业要求和提交内容生成评分建议
4. 助教审阅确认后 → `grade` 或 `batch_grade` 批量打分

> ⚠️ 打分功能需要助教/教师权限的 Canvas Token，学生 Token 无法使用。

## 工作流

### 1. 课件下载 + 总结

1. 用 `canvas_api.download_course_files()` 下载指定课程的 PPT/PDF
2. 用 `file_extractor.extract_file()` 提取文本内容
3. 直接在对话中总结要点（小灰灰作为LLM）

### 2. 作业辅导

1. 用 `canvas_api.get_assignment()` 获取作业详情和要求
2. 如果作业描述包含图片（题目截图），下载图片并用 `Read` 工具识别题目内容
3. 用 `canvas_api.list_course_files()` 找到相关课件
4. 下载并提取课件内容
5. 结合作业要求和课件内容，给出完整解题思路
6. **必须用 `feishu_create_doc` 生成飞书云文档**，标题格式：`📝 {课程名}{作业名} 解题思路`
   - 使用 Lark-flavored Markdown，包含公式（LaTeX `$$` 块级 / `<equation>` 行内）、表格、callout 高亮框
   - 文档结构：题意概述 → 分步解题 → 最终结果
7. 将文档链接发送给用户

### 3. DDL 管理

1. 用 `canvas_api.get_all_upcoming_ddls()` 获取所有未来DDL
2. 用 `calendar_sync.sync_ddls()` 同步到 Apple 日历
3. 可设置 cron 定时巡检

### 4. 成绩追踪

1. 用 `canvas_api.get_course_grades()` 获取各科成绩
2. 计算加权均分

### 5. 期末复习包

1. 用 `canvas_api.download_course_files()` 下载全部课件
2. 用 `file_extractor.batch_extract()` 批量提取为 Markdown
3. 将 Markdown 文件上传到 NotebookLM

### 6. 提交作业

1. 确认课程 ID 和作业 ID
2. 确认要提交的本地文件路径
3. 调用 `canvas_api.submit_assignment()` 提交
4. **提交前必须向用户确认**

### 7. DDL 预警 (cron)

设置 cron 定时任务，每天检查 24h 内到期的作业，通过飞书通知。

### 8. 全自动作业流水线 🆕

1. cron 定时执行 `auto_homework.py watch` 检测新作业
2. 发现新作业 → 自动执行 `context` 构建上下文
3. AI Agent 读取上下文 + 课件 → 生成解答
4. 推送给用户审阅 → 确认后自动提交
5. 支持 `urgent` 模式，优先处理即将到期的作业

### 9. 助教批改 🆕

1. 用 `grading_assistant.py submissions` 查看学生提交
2. 用 `context` 自动下载 + 提取所有提交内容
3. AI 根据作业要求生成评分建议和评语
4. 助教审阅后用 `batch_grade` 批量打分
5. 需要助教权限 Token

### handwrite_pdf.py — 手写风格 PDF 生成器 🆕

```bash
# 从文本文件生成手写 PDF
python3 scripts/handwrite_pdf.py input.txt output.pdf --style casual

# 直接传入文本
python3 scripts/handwrite_pdf.py --text "解题过程..." output.pdf

# 三种风格: neat(工整) casual(随意) messy(潦草)
python3 scripts/handwrite_pdf.py input.txt output.pdf --style neat

# 添加信纸横线
python3 scripts/handwrite_pdf.py input.txt output.pdf --ruled
```

Python 中调用:
```python
from handwrite_pdf import text_to_handwrite_pdf

text_to_handwrite_pdf("解题内容...", "output.pdf", style="casual", ruled=False)
```

**手写作业完整工作流：**
1. `auto_homework.py context` 获取作业要求和课件上下文
2. AI Agent 生成解答文本
3. `handwrite_pdf.py` 将解答渲染为手写风格 PDF
4. 用户确认后 → `submit_assignment()` 提交

## 依赖

```bash
pip3 install python-pptx pdfplumber requests handright Pillow reportlab
```

## 注意事项

- 提交作业前**必须**向用户确认课程、作业和文件
- Canvas Token 有效期可能有限，失效时需重新生成
- Apple 日历操作需要 macOS 授权终端访问日历权限
- 助教批改功能需要助教/教师角色的 Token
- 全自动作业流水线生成的答案**必须**经用户审阅后才能提交
