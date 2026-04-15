#!/usr/bin/env python3
"""SJTU Canvas API 核心模块 - 课程/文件/作业/成绩/讨论区"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_SHANGHAI = timezone(timedelta(hours=8))
BASE_URL = "https://oc.sjtu.edu.cn"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATHS = [
    os.path.join(SKILL_DIR, "config.json"),
    os.path.expanduser("~/.openclaw/workspace/skills/sjtu-canvas/config.json"),
]
PROFILE_ENV_VAR = "OPENCLAW_SJTU_CANVAS_PROFILE"


def load_config():
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def get_canvas_profile(profile_name=None):
    config = load_config()
    requested = profile_name or os.environ.get(PROFILE_ENV_VAR) or config.get("canvas_default_profile")
    profiles = config.get("canvas_profiles") or {}

    if requested and requested in profiles:
        profile = dict(profiles[requested])
        profile.setdefault("name", requested)
        profile.setdefault("base_url", config.get("base_url", BASE_URL))
        return profile

    token = config.get("canvas_token", "")
    if token:
        return {
            "name": requested or "default",
            "token": token,
            "base_url": config.get("base_url", BASE_URL),
        }

    if requested and requested not in profiles:
        print(f"ERROR: Canvas profile '{requested}' not found in config.json")
        sys.exit(1)

    print("ERROR: Canvas token not configured. Set canvas_token or canvas_profiles in config.json")
    sys.exit(1)


def get_token(profile_name=None):
    profile = get_canvas_profile(profile_name)
    token = profile.get("token", "")
    if not token:
        print(f"ERROR: Canvas token missing for profile '{profile.get('name', 'default')}'")
        sys.exit(1)
    return token


def get_base_url(profile_name=None):
    profile = get_canvas_profile(profile_name)
    return profile.get("base_url", BASE_URL)


def headers(profile_name=None):
    return {"Authorization": f"Bearer {get_token(profile_name)}"}


def api_get(path, params=None, profile_name=None):
    url = f"{get_base_url(profile_name)}{path}"
    items = []
    while url:
        r = requests.get(url, headers=headers(profile_name), params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            items.extend(data)
        else:
            return data
        # 分页
        links = r.headers.get("Link", "")
        url = None
        for link in links.split(","):
            if 'rel="next"' in link:
                url = link.split("<")[1].split(">")[0]
        params = None  # 后续页面 URL 已包含参数
    return items

# ===== 用户 =====
def get_me(profile_name=None):
    return api_get("/api/v1/users/self", profile_name=profile_name)

# ===== 课程 =====
def list_courses(profile_name=None):
    return api_get("/api/v1/courses", {"enrollment_state": "active", "per_page": 50}, profile_name=profile_name)

# ===== 文件 =====
def list_course_files(course_id, search_term=None, profile_name=None):
    params = {"per_page": 100}
    if search_term:
        params["search_term"] = search_term
    return api_get(f"/api/v1/courses/{course_id}/files", params, profile_name=profile_name)

def list_course_folders(course_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/folders", {"per_page": 100}, profile_name=profile_name)

def download_file(file_url, save_path, profile_name=None):
    r = requests.get(file_url, headers=headers(profile_name), stream=True)
    r.raise_for_status()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return save_path

def download_course_files(course_id, course_name, save_dir, extensions=None, profile_name=None):
    """批量下载课程文件，可按扩展名过滤"""
    files = list_course_files(course_id, profile_name=profile_name)
    downloaded = []
    for f in files:
        name = f.get("display_name", "")
        if extensions:
            ext = os.path.splitext(name)[1].lower()
            if ext not in extensions:
                continue
        save_path = os.path.join(save_dir, course_name, name)
        if os.path.exists(save_path):
            downloaded.append(save_path)
            continue
        try:
            download_file(f["url"], save_path, profile_name=profile_name)
            downloaded.append(save_path)
            print(f"  ✅ {name}")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    return downloaded

# ===== 作业 =====
def list_assignments(course_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/assignments", {"per_page": 50, "order_by": "due_at"}, profile_name=profile_name)

def get_assignment(course_id, assignment_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}", profile_name=profile_name)

def get_my_submission(course_id, assignment_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self", profile_name=profile_name)

def submit_assignment(course_id, assignment_id, file_paths, profile_name=None):
    """上传文件并提交作业"""
    h = headers(profile_name)
    base_url = get_base_url(profile_name)
    uploaded_ids = []
    for fp in file_paths:
        fname = os.path.basename(fp)
        fsize = os.path.getsize(fp)
        # Step 1: 请求上传
        r = requests.post(
            f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self/files",
            headers=h,
            data={"name": fname, "size": fsize}
        )
        r.raise_for_status()
        upload_info = r.json()
        # Step 2: 上传文件
        with open(fp, "rb") as f:
            r2 = requests.post(
                upload_info["upload_url"],
                data=upload_info.get("upload_params", {}),
                files={"file": (fname, f)}
            )
            r2.raise_for_status()
            uploaded_ids.append(r2.json()["id"])
    # Step 3: 提交
    r3 = requests.post(
        f"{base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
        headers=h,
        data={
            "submission[submission_type]": "online_upload",
            **{f"submission[file_ids][{i}]": fid for i, fid in enumerate(uploaded_ids)}
        }
    )
    r3.raise_for_status()
    return r3.json()

# ===== 成绩 =====
def get_course_grades(course_id, profile_name=None):
    assignments = list_assignments(course_id, profile_name=profile_name)
    results = []
    for a in assignments:
        sub = a.get("submission", {})
        results.append({
            "name": a["name"],
            "points_possible": a.get("points_possible"),
            "score": sub.get("score") if sub else None,
            "grade": sub.get("grade") if sub else None,
            "workflow_state": sub.get("workflow_state", "") if sub else "",
            "due_at": a.get("due_at"),
        })
    return results

# ===== 讨论区 =====
def list_discussions(course_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/discussion_topics", {"per_page": 50}, profile_name=profile_name)

def get_full_discussion(course_id, topic_id, profile_name=None):
    return api_get(f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/view", profile_name=profile_name)

# ===== DDL 汇总 =====
def get_all_upcoming_ddls(profile_name=None):
    """获取所有未来DDL（仅未交的）"""
    ddls = get_all_ddls_via_planner(profile_name=profile_name)
    now = datetime.now(TZ_SHANGHAI)
    return [d for d in ddls if d["due_dt"] > now and not d["submitted"]]

def get_all_ddls_via_planner(start_date=None, include_past=False, profile_name=None):
    """通过 Planner API 一次性获取所有DDL，信息更丰富，速度更快。
    
    优势（vs 旧的逐课程遍历）：
    - 1次API调用 vs N次（每门课一次）
    - 自带详细提交状态：submitted/graded/late/missing/feedback
    - 包含老师反馈评语
    - 包含公告等其他待办事项
    
    Args:
        start_date: 起始日期字符串 (YYYY-MM-DD)，默认本学期开始 (2026-02-17)
        include_past: 是否包含已过期的DDL
    """
    if not start_date:
        start_date = "2026-02-17"  # 本学期开始日期
    
    items = api_get("/api/v1/planner/items", {
        "start_date": start_date,
        "per_page": 100,
    }, profile_name=profile_name)
    
    now = datetime.now(TZ_SHANGHAI)
    ddls = []
    
    for item in items:
        if item.get("plannable_type") != "assignment":
            continue
        
        plannable = item.get("plannable", {})
        submissions = item.get("submissions", {})
        due = plannable.get("due_at")
        
        if not due:
            continue
        
        due_dt = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(TZ_SHANGHAI)
        
        if not include_past and due_dt < now:
            # 仍然保留已过期的，由调用方决定是否过滤
            pass
        
        # 提取老师反馈
        feedback = None
        if submissions and submissions.get("has_feedback"):
            fb = submissions.get("feedback", {})
            if fb:
                feedback = {
                    "comment": fb.get("comment", ""),
                    "author": fb.get("author_name", ""),
                }
        
        ddls.append({
            "course": item.get("context_name", ""),
            "course_id": item.get("course_id"),
            "assignment": plannable.get("title", ""),
            "assignment_id": plannable.get("id"),
            "due_at": due,
            "due_dt": due_dt,
            "due_local": due_dt.strftime("%Y-%m-%d %H:%M"),
            "submitted": bool(submissions and submissions.get("submitted")),
            "graded": bool(submissions and submissions.get("graded")),
            "late": bool(submissions and submissions.get("late")),
            "missing": bool(submissions and submissions.get("missing")),
            "needs_grading": bool(submissions and submissions.get("needs_grading")),
            "has_feedback": bool(submissions and submissions.get("has_feedback")),
            "feedback": feedback,
            "points": plannable.get("points_possible"),
            "html_url": get_base_url(profile_name) + item.get("html_url", ""),
            "is_new": item.get("new_activity", False),
        })
    
    ddls.sort(key=lambda x: x["due_at"])
    return ddls

def get_semester_ddl_summary(start_date=None, profile_name=None):
    """获取本学期完整DDL报告，含统计信息"""
    ddls = get_all_ddls_via_planner(start_date=start_date, include_past=True, profile_name=profile_name)
    now = datetime.now(TZ_SHANGHAI)
    
    total = len(ddls)
    submitted = sum(1 for d in ddls if d["submitted"])
    graded = sum(1 for d in ddls if d["graded"])
    late = sum(1 for d in ddls if d["late"])
    missing = sum(1 for d in ddls if not d["submitted"] and d["due_dt"] < now)
    upcoming = [d for d in ddls if d["due_dt"] > now and not d["submitted"]]
    with_feedback = [d for d in ddls if d["has_feedback"]]
    
    return {
        "ddls": ddls,
        "stats": {
            "total": total,
            "submitted": submitted,
            "graded": graded,
            "late": late,
            "missing": missing,
            "upcoming_count": len(upcoming),
        },
        "upcoming": upcoming,
        "feedback": with_feedback,
    }

# ===== 日历事件 =====
def list_calendar_events(course_ids, start_date, end_date, profile_name=None):
    context_codes = [f"course_{cid}" for cid in course_ids]
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "per_page": 100,
    }
    for i, cc in enumerate(context_codes):
        params[f"context_codes[{i}]"] = cc
    return api_get("/api/v1/calendar_events", params, profile_name=profile_name)

def _parse_cli_args(argv):
    profile_name = None
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--profile" and i + 1 < len(argv):
            profile_name = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    return args, profile_name


if __name__ == "__main__":
    cli_args, profile_name = _parse_cli_args(sys.argv[1:])
    cmd = cli_args[0] if cli_args else "courses"

    if cmd == "courses":
        for c in list_courses(profile_name=profile_name):
            role = ((c.get("enrollments") or [{}])[0].get("role") or "").replace("Enrollment", "")
            role_suffix = f" [{role}]" if role else ""
            print(f"[{c['id']}] {c['name']}{role_suffix}")
    elif cmd == "ddls":
        upcoming = get_all_upcoming_ddls(profile_name=profile_name)
        if not upcoming:
            print("🎉 没有未交的作业！")
        else:
            print(f"📋 {len(upcoming)} 个未交作业：")
            for d in upcoming:
                hours_left = (d["due_dt"] - datetime.now(TZ_SHANGHAI)).total_seconds() / 3600
                urgency = "🔴" if hours_left < 24 else "🟡" if hours_left < 72 else "🟢"
                print(f"  {urgency} [{d['course']}] {d['assignment']} → {d['due_local']} ({hours_left:.0f}h)")
    elif cmd == "ddls-all":
        report = get_semester_ddl_summary(profile_name=profile_name)
        s = report["stats"]
        print(f"📊 本学期DDL全景：共{s['total']}个 | 已交{s['submitted']} | 已批{s['graded']} | 迟交{s['late']} | 未交{s['missing']}")
        print(f"\n⏰ 待交 ({s['upcoming_count']}个)：")
        for d in report["upcoming"]:
            hours_left = (d["due_dt"] - datetime.now(TZ_SHANGHAI)).total_seconds() / 3600
            urgency = "🔴" if hours_left < 24 else "🟡" if hours_left < 72 else "🟢"
            print(f"  {urgency} [{d['course']}] {d['assignment']} → {d['due_local']} ({hours_left:.0f}h)")
        if report["feedback"]:
            print(f"\n💬 老师反馈 ({len(report['feedback'])}条)：")
            for d in report["feedback"]:
                fb = d["feedback"]
                print(f"  [{d['course']}] {d['assignment']} — {fb['author']}: {fb['comment']}")
    elif cmd == "grades":
        for c in list_courses(profile_name=profile_name):
            grades = get_course_grades(c["id"], profile_name=profile_name)
            scored = [g for g in grades if g["score"] is not None]
            if scored:
                print(f"\n📚 {c['name']}:")
                for g in scored:
                    print(f"  {g['name']}: {g['score']}/{g['points_possible']}")
    elif cmd == "me":
        profile = get_canvas_profile(profile_name)
        me = get_me(profile_name=profile_name)
        print(f"用户: {me['name']} (ID: {me['id']}) | Profile: {profile.get('name', 'default')}")
