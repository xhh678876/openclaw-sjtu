#!/usr/bin/env python3
"""
助教批改助手 - Grading Assistant

功能：
1. 批量拉取学生提交的作业
2. 下载学生提交的文件
3. 提取提交内容，生成批改上下文
4. AI 生成评分建议和评语
5. 支持批量打分（需要助教/教师权限 Token）

用法：
  python3 grading_assistant.py submissions <course_id> <assignment_id>  # 查看提交列表
  python3 grading_assistant.py download <course_id> <assignment_id>     # 下载所有提交
  python3 grading_assistant.py context <course_id> <assignment_id>      # 生成批改上下文
  python3 grading_assistant.py grade <course_id> <assignment_id> <submission_id> <score> [comment]  # 打分

注意：打分功能需要助教/教师权限的 Canvas Token
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_api import (
    headers, BASE_URL, get_token, api_get,
    get_assignment, list_course_files
)
from file_extractor import extract_file

TZ_SHANGHAI = timezone(timedelta(hours=8))
GRADING_DIR = os.path.expanduser("~/Downloads/Canvas批改")


def list_submissions(course_id, assignment_id, include_unsubmitted=False):
    """获取作业的所有学生提交"""
    params = {"per_page": 100, "include[]": ["user", "submission_comments"]}
    submissions = api_get(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        params
    )

    results = []
    for s in submissions:
        workflow = s.get("workflow_state", "")
        if not include_unsubmitted and workflow == "unsubmitted":
            continue

        user = s.get("user", {})
        results.append({
            "submission_id": s["id"],
            "user_id": s.get("user_id"),
            "user_name": user.get("name", "未知"),
            "user_sortable_name": user.get("sortable_name", ""),
            "workflow_state": workflow,
            "submitted_at": s.get("submitted_at"),
            "score": s.get("score"),
            "grade": s.get("grade"),
            "late": s.get("late", False),
            "missing": s.get("missing", False),
            "attempt": s.get("attempt"),
            "submission_type": s.get("submission_type"),
            "attachments": [
                {
                    "id": att.get("id"),
                    "display_name": att.get("display_name", ""),
                    "filename": att.get("filename", ""),
                    "url": att.get("url", ""),
                    "size": att.get("size", 0),
                    "content_type": att.get("content-type", ""),
                }
                for att in s.get("attachments", [])
            ],
            "body": s.get("body"),  # online_text_entry 的内容
            "comments": [
                {
                    "author": c.get("author_name", ""),
                    "comment": c.get("comment", ""),
                    "created_at": c.get("created_at", ""),
                }
                for c in s.get("submission_comments", [])
            ],
        })

    results.sort(key=lambda x: x["user_sortable_name"])
    return results


def download_submission_files(course_id, assignment_id, submission=None, save_dir=None):
    """下载单个或所有学生提交的文件"""
    if save_dir is None:
        save_dir = os.path.join(GRADING_DIR, f"course_{course_id}_assignment_{assignment_id}")

    if submission:
        submissions = [submission]
    else:
        submissions = list_submissions(course_id, assignment_id)

    downloaded = []
    for sub in submissions:
        student_name = sub["user_name"].replace("/", "_").replace(" ", "_")
        student_dir = os.path.join(save_dir, student_name)

        for att in sub.get("attachments", []):
            fname = att.get("display_name", att.get("filename", "unknown"))
            save_path = os.path.join(student_dir, fname)

            if os.path.exists(save_path):
                downloaded.append({"student": sub["user_name"], "file": fname, "path": save_path})
                continue

            try:
                os.makedirs(student_dir, exist_ok=True)
                r = requests.get(att["url"], headers=headers(), stream=True, timeout=60)
                r.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                downloaded.append({"student": sub["user_name"], "file": fname, "path": save_path})
                print(f"  ✅ {sub['user_name']}/{fname}")
            except Exception as e:
                print(f"  ❌ {sub['user_name']}/{fname}: {e}")
                downloaded.append({"student": sub["user_name"], "file": fname, "error": str(e)})

        # online_text_entry
        if sub.get("body"):
            text_path = os.path.join(student_dir, "提交内容.html")
            os.makedirs(student_dir, exist_ok=True)
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(sub["body"])
            downloaded.append({"student": sub["user_name"], "file": "提交内容.html", "path": text_path})

    return downloaded


def build_grading_context(course_id, assignment_id, max_students=50):
    """
    构建批改上下文

    返回：作业要求 + 每个学生的提交内容摘要
    """
    # 1. 获取作业详情
    assignment = get_assignment(course_id, assignment_id)
    assignment_info = {
        "name": assignment["name"],
        "description": assignment.get("description", ""),
        "points_possible": assignment.get("points_possible"),
        "due_at": assignment.get("due_at"),
    }

    # 2. 获取并下载提交
    submissions = list_submissions(course_id, assignment_id)
    save_dir = os.path.join(GRADING_DIR, f"course_{course_id}_assignment_{assignment_id}")
    download_submission_files(course_id, assignment_id, save_dir=save_dir)

    # 3. 提取每份提交的内容
    student_submissions = []
    for sub in submissions[:max_students]:
        student_name = sub["user_name"].replace("/", "_").replace(" ", "_")
        student_dir = os.path.join(save_dir, student_name)

        content_parts = []

        # 提取文件内容
        for att in sub.get("attachments", []):
            fname = att.get("display_name", "")
            fpath = os.path.join(student_dir, fname)
            if os.path.exists(fpath):
                try:
                    text = extract_file(fpath)
                    content_parts.append(f"### 文件: {fname}\n\n{text[:5000]}")
                except:
                    content_parts.append(f"### 文件: {fname}\n\n[无法提取内容]")

        # online_text_entry
        if sub.get("body"):
            content_parts.append(f"### 在线提交\n\n{sub['body'][:5000]}")

        student_submissions.append({
            "user_name": sub["user_name"],
            "user_id": sub["user_id"],
            "submission_id": sub["submission_id"],
            "late": sub["late"],
            "current_score": sub["score"],
            "content": "\n\n".join(content_parts) if content_parts else "[未提交或无可读内容]",
        })

    # 4. 生成批改 prompt
    context = {
        "assignment": assignment_info,
        "submissions": student_submissions,
        "total_submissions": len(submissions),
        "save_dir": save_dir,
    }

    prompt = generate_grading_prompt(context)
    prompt_path = os.path.join(save_dir, "grading_prompt.md")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    context["prompt_path"] = prompt_path
    return context


def generate_grading_prompt(context):
    """生成给 AI 的批改提示"""
    a = context["assignment"]
    lines = [
        "# 作业批改请求",
        "",
        "## 作业信息",
        f"- **作业名称**: {a['name']}",
        f"- **满分**: {a['points_possible']}",
        f"- **截止时间**: {a.get('due_at', '未知')}",
        "",
        "## 作业要求",
        a.get("description", "(无描述)"),
        "",
        "---",
        "",
        f"## 学生提交（共 {len(context['submissions'])} 份）",
        "",
    ]

    for i, sub in enumerate(context["submissions"], 1):
        late_mark = " ⚠️ 迟交" if sub["late"] else ""
        lines.extend([
            f"### 学生 {i}: {sub['user_name']}{late_mark}",
            "",
            sub["content"],
            "",
            "---",
            "",
        ])

    lines.extend([
        "## 批改要求",
        "",
        "请对每位学生的提交进行批改：",
        "1. **评分** — 给出具体分数（满分 {}）".format(a['points_possible']),
        "2. **评语** — 指出优点和不足，给出改进建议",
        "3. **常见问题** — 总结本次作业的共性问题",
        "4. **评分标准** — 根据作业要求制定评分细则",
        "",
        "输出格式：",
        "```",
        "| 学生 | 分数 | 评语摘要 |",
        "|---|---|---|",
        "| 张三 | 85 | 解题思路正确，但计算有误... |",
        "```",
    ])

    return "\n".join(lines)


def grade_submission(course_id, assignment_id, user_id, score, comment=None):
    """
    给学生打分

    需要助教/教师权限
    """
    url = f"{BASE_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
    data = {
        "submission[posted_grade]": str(score),
    }
    if comment:
        data["comment[text_comment]"] = comment

    r = requests.put(url, headers=headers(), data=data)
    r.raise_for_status()
    return r.json()


def batch_grade(course_id, assignment_id, grades):
    """
    批量打分

    grades: list of {"user_id": int, "score": float, "comment": str}
    """
    results = []
    for g in grades:
        try:
            result = grade_submission(
                course_id, assignment_id,
                g["user_id"], g["score"], g.get("comment")
            )
            results.append({"user_id": g["user_id"], "success": True, "score": g["score"]})
            print(f"  ✅ user {g['user_id']}: {g['score']}")
        except Exception as e:
            results.append({"user_id": g["user_id"], "success": False, "error": str(e)})
            print(f"  ❌ user {g['user_id']}: {e}")
    return results


# ===== CLI =====
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "submissions":
        if len(sys.argv) < 4:
            print("用法: grading_assistant.py submissions <course_id> <assignment_id>")
            sys.exit(1)
        cid, aid = int(sys.argv[2]), int(sys.argv[3])
        print(f"📋 获取提交列表 (course={cid}, assignment={aid})...\n")
        subs = list_submissions(cid, aid)
        print(f"共 {len(subs)} 份提交:\n")
        for s in subs:
            status = "✅" if s["score"] is not None else "⏳"
            late = " (迟交)" if s["late"] else ""
            score = f" → {s['score']}/{s.get('grade', '?')}" if s["score"] is not None else ""
            files = ", ".join(a["display_name"] for a in s["attachments"]) or s.get("submission_type", "")
            print(f"  {status} {s['user_name']}{late}{score}")
            if files:
                print(f"     文件: {files}")

    elif cmd == "download":
        if len(sys.argv) < 4:
            print("用法: grading_assistant.py download <course_id> <assignment_id>")
            sys.exit(1)
        cid, aid = int(sys.argv[2]), int(sys.argv[3])
        print(f"📥 下载所有提交...\n")
        results = download_submission_files(cid, aid)
        print(f"\n共下载 {len(results)} 个文件")

    elif cmd == "context":
        if len(sys.argv) < 4:
            print("用法: grading_assistant.py context <course_id> <assignment_id>")
            sys.exit(1)
        cid, aid = int(sys.argv[2]), int(sys.argv[3])
        print(f"📝 构建批改上下文...\n")
        ctx = build_grading_context(cid, aid)
        print(f"\n✅ 批改上下文已生成:")
        print(f"   📄 Prompt: {ctx['prompt_path']}")
        print(f"   👥 提交数: {ctx['total_submissions']}")

    elif cmd == "grade":
        if len(sys.argv) < 6:
            print("用法: grading_assistant.py grade <cid> <aid> <user_id> <score> [comment]")
            sys.exit(1)
        cid, aid = int(sys.argv[2]), int(sys.argv[3])
        uid, score = int(sys.argv[4]), float(sys.argv[5])
        comment = sys.argv[6] if len(sys.argv) > 6 else None
        print(f"📝 打分: user={uid}, score={score}")
        result = grade_submission(cid, aid, uid, score, comment)
        print(f"✅ 完成")

    else:
        print("助教批改助手")
        print()
        print("用法:")
        print("  grading_assistant.py submissions <cid> <aid>           # 查看提交列表")
        print("  grading_assistant.py download <cid> <aid>              # 下载所有提交")
        print("  grading_assistant.py context <cid> <aid>               # 生成批改上下文")
        print("  grading_assistant.py grade <cid> <aid> <uid> <score>   # 打分")
