#!/usr/bin/env python3
"""
全自动作业流水线 - Auto Homework Pipeline

功能：
1. 巡检所有课程的未提交作业
2. 下载相关课件，提取内容构建知识库
3. 提取作业要求（含题目图片识别）
4. 生成作业上下文（供 AI Agent 生成答案）
5. 支持提交作业

用法：
  python3 auto_homework.py scan                    # 扫描未提交作业
  python3 auto_homework.py context <course_id> <assignment_id>  # 生成作业上下文
  python3 auto_homework.py full <course_id> <assignment_id>     # 完整流水线
  python3 auto_homework.py watch                   # 持续监控模式（配合 cron）
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html.parser import HTMLParser

# 添加当前目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_api import (
    list_courses, list_assignments, get_assignment, get_my_submission,
    list_course_files, download_file, headers, BASE_URL, get_token
)
from file_extractor import extract_file

TZ_SHANGHAI = timezone(timedelta(hours=8))
WORK_DIR = os.path.expanduser("~/Downloads/Canvas课件")
CONTEXT_DIR = os.path.expanduser("~/Downloads/Canvas作业上下文")


class HTMLTextExtractor(HTMLParser):
    """从 HTML 中提取纯文本和图片 URL"""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.image_urls = []
        self._in_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'img' and 'src' in attrs_dict:
            self.image_urls.append(attrs_dict['src'])
            alt = attrs_dict.get('alt', '')
            if alt:
                self.text_parts.append(f"[图片: {alt}]")
            else:
                self.text_parts.append(f"[图片: {attrs_dict['src']}]")
        elif tag == 'br':
            self.text_parts.append('\n')
        elif tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'h4'):
            self.text_parts.append('\n')
        elif tag == 'a' and 'href' in attrs_dict:
            self._in_tag = ('a', attrs_dict['href'])

    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'h4'):
            self.text_parts.append('\n')
        if tag == 'a' and self._in_tag and self._in_tag[0] == 'a':
            self.text_parts.append(f" ({self._in_tag[1]})")
            self._in_tag = None

    def handle_data(self, data):
        self.text_parts.append(data)

    def get_text(self):
        return re.sub(r'\n{3,}', '\n\n', ''.join(self.text_parts).strip())


def parse_html_content(html_str):
    """解析作业描述 HTML，返回纯文本和图片列表"""
    if not html_str:
        return "", []
    parser = HTMLTextExtractor()
    parser.feed(html_str)
    return parser.get_text(), parser.image_urls


def download_image(url, save_dir, index=0):
    """下载作业描述中的图片"""
    try:
        # Canvas 内部链接需要认证
        h = headers() if 'canvas' in url.lower() or BASE_URL in url else {}
        r = requests.get(url, headers=h, stream=True, timeout=30)
        r.raise_for_status()

        # 推断扩展名
        content_type = r.headers.get('content-type', '')
        ext_map = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}
        ext = ext_map.get(content_type.split(';')[0].strip(), '.png')

        save_path = os.path.join(save_dir, f"题目图片_{index+1}{ext}")
        os.makedirs(save_dir, exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return save_path
    except Exception as e:
        return f"[下载失败: {e}]"


def scan_unsubmitted():
    """扫描所有课程的未提交作业"""
    now = datetime.now(TZ_SHANGHAI)
    courses = list_courses()
    unsubmitted = []

    for c in courses:
        course_name = c.get("name", "未知课程")
        course_id = c["id"]
        try:
            assignments = list_assignments(course_id)
        except Exception:
            continue

        for a in assignments:
            due = a.get("due_at")
            if not due:
                continue

            due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(TZ_SHANGHAI)

            # 只看未来的作业
            if due_dt <= now:
                continue

            # 检查提交状态
            sub = a.get("submission", {})
            workflow = sub.get("workflow_state", "") if sub else ""
            if workflow in ["submitted", "graded"]:
                continue

            # 计算剩余时间
            remaining = due_dt - now
            hours_left = remaining.total_seconds() / 3600

            unsubmitted.append({
                "course": course_name,
                "course_id": course_id,
                "assignment": a["name"],
                "assignment_id": a["id"],
                "due_at": due,
                "due_local": due_dt.strftime("%Y-%m-%d %H:%M"),
                "hours_left": round(hours_left, 1),
                "points": a.get("points_possible"),
                "submission_types": a.get("submission_types", []),
                "has_description": bool(a.get("description")),
            })

    unsubmitted.sort(key=lambda x: x["hours_left"])
    return unsubmitted


def get_assignment_detail(course_id, assignment_id):
    """获取作业的完整详情，包括描述解析和图片"""
    a = get_assignment(course_id, assignment_id)
    desc_html = a.get("description", "") or ""
    desc_text, image_urls = parse_html_content(desc_html)

    return {
        "name": a["name"],
        "description_text": desc_text,
        "description_html": desc_html,
        "image_urls": image_urls,
        "due_at": a.get("due_at"),
        "points_possible": a.get("points_possible"),
        "submission_types": a.get("submission_types", []),
        "allowed_extensions": a.get("allowed_extensions", []),
        "lock_at": a.get("lock_at"),
        "unlock_at": a.get("unlock_at"),
    }


def find_relevant_files(course_id, assignment_name, max_files=10):
    """根据作业名称在课程文件中查找相关课件"""
    all_files = list_course_files(course_id)

    # 提取作业中的关键词
    keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', assignment_name.lower())

    scored_files = []
    for f in all_files:
        name = f.get("display_name", "").lower()
        ext = os.path.splitext(name)[1]
        if ext not in [".pptx", ".ppt", ".pdf", ".docx", ".doc"]:
            continue

        score = 0
        for kw in keywords:
            if kw in name:
                score += 2
        # PPT/PDF 优先
        if ext in [".pptx", ".ppt", ".pdf"]:
            score += 1
        # 较新的文件优先
        scored_files.append((score, f))

    scored_files.sort(key=lambda x: -x[0])
    return [f for _, f in scored_files[:max_files]]


def build_homework_context(course_id, assignment_id, download_courseware=True):
    """
    构建作业上下文 — 核心功能

    返回一个包含所有 AI 需要的信息的字典：
    - 作业要求（文本 + 图片路径）
    - 相关课件内容
    - 提交要求
    """
    # 1. 获取课程信息
    courses = list_courses()
    course = next((c for c in courses if c["id"] == course_id), None)
    course_name = course.get("name", "未知") if course else "未知"

    # 2. 获取作业详情
    detail = get_assignment_detail(course_id, assignment_id)

    # 3. 下载作业描述中的图片
    context_dir = os.path.join(CONTEXT_DIR, f"{course_name}_{detail['name']}")
    os.makedirs(context_dir, exist_ok=True)

    downloaded_images = []
    for i, img_url in enumerate(detail["image_urls"]):
        result = download_image(img_url, context_dir, i)
        downloaded_images.append(result)

    # 4. 查找并下载相关课件
    courseware_contents = []
    if download_courseware:
        relevant = find_relevant_files(course_id, detail["name"])
        courseware_dir = os.path.join(WORK_DIR, course_name)
        os.makedirs(courseware_dir, exist_ok=True)

        for f in relevant:
            fname = f.get("display_name", "")
            save_path = os.path.join(courseware_dir, fname)

            # 下载（如不存在）
            if not os.path.exists(save_path):
                try:
                    download_file(f["url"], save_path)
                except Exception as e:
                    courseware_contents.append({
                        "file": fname,
                        "content": f"[下载失败: {e}]",
                        "chars": 0,
                    })
                    continue

            # 提取内容
            try:
                content = extract_file(save_path)
                courseware_contents.append({
                    "file": fname,
                    "content": content[:20000],  # 截断过长的内容
                    "chars": len(content),
                    "path": save_path,
                })
            except Exception as e:
                courseware_contents.append({
                    "file": fname,
                    "content": f"[提取失败: {e}]",
                    "chars": 0,
                })

    # 5. 组装上下文
    context = {
        "course": course_name,
        "course_id": course_id,
        "assignment": detail["name"],
        "assignment_id": assignment_id,
        "due_at": detail["due_at"],
        "points": detail["points_possible"],
        "submission_types": detail["submission_types"],
        "allowed_extensions": detail["allowed_extensions"],
        "description": detail["description_text"],
        "description_images": downloaded_images,
        "courseware": courseware_contents,
        "context_dir": context_dir,
    }

    # 6. 保存上下文摘要
    summary_path = os.path.join(context_dir, "context_summary.json")
    summary = {k: v for k, v in context.items() if k != "courseware"}
    summary["courseware_files"] = [
        {"file": cw["file"], "chars": cw["chars"]} for cw in courseware_contents
    ]
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 7. 生成 AI Prompt 文件
    prompt = generate_ai_prompt(context)
    prompt_path = os.path.join(context_dir, "ai_prompt.md")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    context["summary_path"] = summary_path
    context["prompt_path"] = prompt_path
    return context


def generate_ai_prompt(context):
    """生成给 AI 的作业解答提示"""
    lines = [
        f"# 作业解答请求",
        f"",
        f"## 基本信息",
        f"- **课程**: {context['course']}",
        f"- **作业**: {context['assignment']}",
        f"- **截止时间**: {context.get('due_at', '未知')}",
        f"- **满分**: {context.get('points', '未知')}",
        f"- **提交类型**: {', '.join(context.get('submission_types', []))}",
        f"- **允许格式**: {', '.join(context.get('allowed_extensions', [])) or '未限制'}",
        f"",
        f"## 作业要求",
        f"",
        context.get("description", "(无文字描述)"),
        f"",
    ]

    # 图片提示
    if context.get("description_images"):
        lines.append("### 题目图片")
        for img_path in context["description_images"]:
            if os.path.exists(str(img_path)):
                lines.append(f"- 📷 `{img_path}`（请用视觉模型识别题目内容）")
            else:
                lines.append(f"- ⚠️ {img_path}")
        lines.append("")

    # 课件参考
    if context.get("courseware"):
        lines.append("## 相关课件内容")
        lines.append("")
        for cw in context["courseware"]:
            lines.append(f"### 📄 {cw['file']}（{cw['chars']} 字符）")
            lines.append("")
            # 只放前 5000 字符到 prompt 中
            content = cw.get("content", "")
            if len(content) > 5000:
                lines.append(content[:5000])
                lines.append(f"\n... (已截断，完整内容 {cw['chars']} 字符)")
            else:
                lines.append(content)
            lines.append("")

    lines.extend([
        "## 解答要求",
        "",
        "1. 仔细分析题目要求，识别每一道小题",
        "2. 结合上方课件内容，找到对应的知识点和公式",
        "3. 给出完整的解题步骤和最终答案",
        "4. 如果有计算题，列出详细的计算过程",
        "5. 如果有简答题，给出结构化、有条理的回答",
        "6. 最终输出格式应适合直接提交（PDF 或 Word 格式）",
    ])

    return "\n".join(lines)


def check_new_assignments(state_file=None):
    """
    检查是否有新作业（与上次巡检对比）
    用于 cron / watch 模式
    """
    if state_file is None:
        state_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".homework_state.json"
        )

    # 读取上次状态
    last_known = set()
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
            last_known = set(state.get("known_assignment_ids", []))

    # 扫描当前未提交
    current = scan_unsubmitted()
    current_ids = {f"{a['course_id']}_{a['assignment_id']}" for a in current}

    # 找出新增的
    new_ids = current_ids - last_known
    new_assignments = [a for a in current if f"{a['course_id']}_{a['assignment_id']}" in new_ids]

    # 保存状态
    with open(state_file, "w") as f:
        json.dump({
            "known_assignment_ids": list(current_ids),
            "last_check": datetime.now(TZ_SHANGHAI).isoformat(),
            "total_unsubmitted": len(current),
        }, f, indent=2)

    return {
        "new": new_assignments,
        "all_unsubmitted": current,
        "total_new": len(new_assignments),
        "total_unsubmitted": len(current),
    }


def get_urgent_assignments(hours=48):
    """获取紧急作业（指定小时内到期且未提交的）"""
    all_unsubmitted = scan_unsubmitted()
    return [a for a in all_unsubmitted if a["hours_left"] <= hours]


# ===== CLI =====
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        print("🔍 扫描未提交作业...\n")
        unsubmitted = scan_unsubmitted()
        if not unsubmitted:
            print("✅ 没有未提交的作业！")
        else:
            print(f"📋 共 {len(unsubmitted)} 项未提交:\n")
            for a in unsubmitted:
                urgency = "🔴" if a["hours_left"] < 24 else "🟡" if a["hours_left"] < 72 else "🟢"
                print(f"  {urgency} [{a['course']}] {a['assignment']}")
                print(f"     截止: {a['due_local']} (剩余 {a['hours_left']}h)")
                print(f"     分值: {a['points']} | 类型: {', '.join(a['submission_types'])}")
                print()

    elif cmd == "context":
        if len(sys.argv) < 4:
            print("用法: auto_homework.py context <course_id> <assignment_id>")
            sys.exit(1)
        cid = int(sys.argv[2])
        aid = int(sys.argv[3])
        print(f"📝 构建作业上下文 (course={cid}, assignment={aid})...\n")
        ctx = build_homework_context(cid, aid)
        print(f"✅ 上下文已生成:")
        print(f"   📄 AI Prompt: {ctx['prompt_path']}")
        print(f"   📊 摘要: {ctx['summary_path']}")
        print(f"   📷 图片: {len(ctx['description_images'])} 张")
        print(f"   📚 课件: {len(ctx['courseware'])} 份")

    elif cmd == "watch":
        print("👀 检查新作业...\n")
        result = check_new_assignments()
        if result["new"]:
            print(f"🆕 发现 {result['total_new']} 项新作业:")
            for a in result["new"]:
                print(f"  📌 [{a['course']}] {a['assignment']} → {a['due_local']}")
        else:
            print("没有新作业。")
        print(f"\n📊 当前共 {result['total_unsubmitted']} 项未提交")

    elif cmd == "urgent":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 48
        print(f"🚨 {hours} 小时内到期的紧急作业:\n")
        urgent = get_urgent_assignments(hours)
        if not urgent:
            print("✅ 没有紧急作业！")
        else:
            for a in urgent:
                print(f"  🔴 [{a['course']}] {a['assignment']}")
                print(f"     剩余 {a['hours_left']} 小时 → {a['due_local']}")
                print()

    elif cmd == "full":
        if len(sys.argv) < 4:
            print("用法: auto_homework.py full <course_id> <assignment_id>")
            sys.exit(1)
        cid = int(sys.argv[2])
        aid = int(sys.argv[3])
        print(f"🚀 完整作业流水线 (course={cid}, assignment={aid})...\n")
        ctx = build_homework_context(cid, aid)
        print(f"\n✅ 作业上下文已准备完毕！")
        print(f"   📄 AI Prompt: {ctx['prompt_path']}")
        print(f"   📊 作业: {ctx['assignment']}")
        print(f"   📚 关联课件: {len(ctx['courseware'])} 份")
        print(f"\n💡 下一步: AI Agent 读取 prompt 文件生成解答，确认后调用 submit 提交。")

    else:
        print("用法:")
        print("  auto_homework.py scan                          # 扫描未提交作业")
        print("  auto_homework.py context <cid> <aid>           # 生成作业上下文")
        print("  auto_homework.py full <cid> <aid>              # 完整流水线")
        print("  auto_homework.py watch                         # 新作业检测")
        print("  auto_homework.py urgent [hours]                # 紧急作业")
