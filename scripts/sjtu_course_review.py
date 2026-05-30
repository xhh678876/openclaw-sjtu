#!/usr/bin/env python3
"""SJTU 选课社区 (jCourse, course.sjtu.plus) — 课程评价查询工具

认证：jCourse 开放 API Key（Bearer token），不再依赖 jAccount cookie / 浏览器代理。
配置方式（二选一）：
  1. 在仓库根目录 config.json 设置  "jcourse_api_key": "jc_xxx"
  2. 环境变量  export JCOURSE_API_KEY=jc_xxx
API Key 申请：登录 course.sjtu.plus → 个人中心 → API 密钥。

开放 API（Bearer 认证，分页 ?page=&page_size=，响应信封 {items,total,page,page_size}）：
- GET /api/course?q=<关键词>        搜索课程（搜索词参数为 q；name/search/keyword 不生效）
- GET /api/course/{id}             课程详情（rating + same_code_courses 同课不同老师对比）
- GET /api/course/{id}/review      某门课程的评价列表（total = 该课评价数）
- GET /api/review                  全站最新评价
- GET /api/teacher?q= / /api/teacher/{id}   教师
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://course.sjtu.plus"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")
DEFAULT_TIMEOUT = 15
STAR_MAX = 5
DEFAULT_REVIEW_LIMIT = 10


class CourseReviewError(Exception):
    """选课社区 API 调用失败（认证、网络或资源问题）。"""


# ===== 配置与请求 =====

def load_api_key() -> str:
    """读取 jCourse API Key：优先环境变量，其次 config.json。"""
    env_key = os.environ.get("JCOURSE_API_KEY", "").strip()
    if env_key:
        return env_key
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        key = (cfg.get("jcourse_api_key") or "").strip()
        if key:
            return key
    raise CourseReviewError(
        "未配置 jCourse API Key。\n"
        '  方法1: 在 config.json 设置  "jcourse_api_key": "jc_..."\n'
        "  方法2: export JCOURSE_API_KEY=jc_...\n"
        "  申请:  登录 course.sjtu.plus → 个人中心 → API 密钥"
    )


def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """调用 jCourse 开放 API，返回解析后的 JSON。失败抛 CourseReviewError。"""
    key = load_api_key()
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "openclaw-sjtu/course-review",
    })
    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code in (401, 403):
            raise CourseReviewError(
                f"认证失败 (HTTP {e.code})：API Key 无效或已过期，"
                "请在 course.sjtu.plus 重新生成后更新 config.json。"
            ) from e
        if e.code == 404:
            raise CourseReviewError(f"资源不存在 (HTTP 404): {path}") from e
        raise CourseReviewError(f"请求失败 (HTTP {e.code}): {path}") from e
    except URLError as e:
        raise CourseReviewError(f"网络错误（需校园网或代理？）: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise CourseReviewError("响应不是合法 JSON（可能命中了反爬页面）。") from e


# ===== 数据归一化 =====

def _rating_avg_count(rating: dict[str, Any] | None) -> tuple[float | None, int]:
    """从 rating 对象取 (平均分, 评价数)；无评价时平均分为 None。"""
    rating = rating or {}
    count = rating.get("count") or 0
    avg = rating.get("avg")
    return (avg if count else None), count


def _course_brief(course: dict[str, Any]) -> dict[str, Any]:
    """把一个 course 对象压成统一的精简视图。"""
    teacher = course.get("main_teacher") or {}
    avg, count = _rating_avg_count(course.get("rating"))
    return {
        "id": course.get("id"),
        "code": course.get("code", ""),
        "name": course.get("name", ""),
        "teacher": teacher.get("name", ""),
        "department": course.get("department", ""),
        "credit": course.get("credit", 0),
        "rating_avg": avg,
        "rating_count": count,
    }


# ===== 核心功能 =====

def search_courses(keyword: str, limit: int = 20) -> dict[str, Any]:
    """搜索课程（按课程名 / 课号 / 老师名）。"""
    data = api_get("/api/course", {"q": keyword, "page": 1, "page_size": limit})
    return {
        "total": data.get("total", 0),
        "results": [_course_brief(c) for c in data.get("items", [])],
    }


def get_course_detail(course_id: int) -> dict[str, Any]:
    """课程详情：评分分布 + 同课号其他老师对比。"""
    data = api_get(f"/api/course/{course_id}")
    brief = _course_brief(data)
    rating = data.get("rating") or {}

    others: list[dict[str, Any]] = []
    for c in data.get("same_code_courses") or []:
        ob = _course_brief(c)
        if ob["id"] != brief["id"]:
            others.append(ob)
    others.sort(key=lambda x: (x["rating_avg"] or 0), reverse=True)

    brief.update({
        "last_semester": data.get("last_semester", ""),
        "score": rating.get("score"),
        "distribution": rating.get("distribution") or [],
        "moderator_remark": data.get("moderator_remark") or "",
        "other_teachers": others,
    })
    return brief


def get_course_reviews(course_id: int, limit: int = DEFAULT_REVIEW_LIMIT) -> dict[str, Any]:
    """某门课程的评价列表（按课程聚合，total = 该课评价总数）。"""
    data = api_get(f"/api/course/{course_id}/review", {"page": 1, "page_size": limit})
    reviews = []
    for r in data.get("items", []):
        vote = r.get("vote") or {}
        reviews.append({
            "semester": r.get("semester", ""),
            "rating": r.get("rating"),
            "content": (r.get("content") or "").strip(),
            "like": vote.get("like_count", 0),
            "dislike": vote.get("dislike_count", 0),
            "date": (r.get("created_at") or "")[:10],
        })
    return {"total": data.get("total", 0), "reviews": reviews}


def compare_teachers(course_name: str, limit: int = 30) -> dict[str, Any]:
    """搜索同名课程的不同老师并按评分排序对比。"""
    data = search_courses(course_name, limit=limit)
    results = data["results"]
    exact = [c for c in results if c["name"] == course_name]
    pool = exact or [c for c in results if course_name in c["name"]]
    if not pool:
        return {
            "error": f"未找到课程: {course_name}",
            "suggestions": [c["name"] for c in results[:5]],
        }

    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for c in pool:
        key = (c["teacher"], c["code"])
        existing = seen.get(key)
        if existing is None or (c["rating_count"] or 0) > (existing["rating_count"] or 0):
            seen[key] = c
    teachers = sorted(seen.values(), key=lambda x: (x["rating_avg"] or 0), reverse=True)
    return {"course": pool[0]["name"], "teachers": teachers}


# ===== 格式化输出 =====

def _star_bar(avg: float | None) -> str:
    if not avg:
        return "暂无评价"
    filled = int(round(avg))
    bar = "★" * filled + "☆" * (STAR_MAX - filled)
    return f"{bar} {avg:.2f}"


def print_search_results(data: dict[str, Any]) -> None:
    print(f"\n🔍 搜索到 {data['total']} 门课程（显示前 {len(data['results'])} 门）")
    print("─" * 64)
    for c in data["results"]:
        rating = f"⭐ {c['rating_avg']:.2f} ({c['rating_count']}人)" if c["rating_avg"] else "暂无评价"
        print(f"  #{c['id']} [{c['code']}] {c['name']}")
        print(f"      👨‍🏫 {c['teacher']} | 🏢 {c['department']} | {c['credit']}学分 | {rating}")


def print_course_detail(detail: dict[str, Any]) -> None:
    print(f"\n📚 {detail['name']}（{detail['teacher']}）  #{detail['id']}")
    print("─" * 64)
    print(f"  课号: {detail['code']}   学分: {detail['credit']}   院系: {detail['department']}")
    if detail.get("last_semester"):
        print(f"  最近开课: {detail['last_semester']}")
    print(f"  评分: {_star_bar(detail['rating_avg'])}  ({detail['rating_count']}人评价)")

    dist = detail.get("distribution") or []
    if any(dist):
        print("  分布: " + "  ".join(f"{i + 1}★:{n}" for i, n in enumerate(dist)))
    if detail.get("moderator_remark"):
        print(f"  小黑板: {detail['moderator_remark']}")

    others = detail.get("other_teachers") or []
    if others:
        print("\n  📊 同课号其他老师:")
        for t in others:
            print(f"    {t['teacher']:10s} {_star_bar(t['rating_avg'])} ({t['rating_count']}人)  #{t['id']}")


def print_reviews(course_id: int, data: dict[str, Any]) -> None:
    print(f"\n💬 课程 #{course_id} 的评价（共 {data['total']} 条，显示 {len(data['reviews'])} 条）")
    print("─" * 64)
    for r in data["reviews"]:
        stars = "★" * (r["rating"] or 0) + "☆" * (STAR_MAX - (r["rating"] or 0))
        meta = f"{stars}  {r['semester']}  👍{r['like']} 👎{r['dislike']}  {r['date']}"
        print(f"\n  {meta}")
        for line in r["content"].splitlines():
            print(f"    {line}")


def print_teacher_comparison(data: dict[str, Any]) -> None:
    if "error" in data:
        print(f"❌ {data['error']}")
        if data.get("suggestions"):
            print(f"  💡 你是不是在找: {', '.join(data['suggestions'])}")
        return
    print(f"\n📊 「{data['course']}」不同老师评分对比")
    print("─" * 64)
    medals = ["🥇", "🥈", "🥉"]
    for i, t in enumerate(data["teachers"]):
        medal = medals[i] if i < len(medals) and t["rating_avg"] else "  "
        print(f"  {medal} {t['teacher']:10s} {_star_bar(t['rating_avg'])} "
              f"({t['rating_count']}人) [{t['code']}] #{t['id']}")


# ===== 自检 =====

def _mask(key: str) -> str:
    return f"{key[:8]}…{key[-4:]}" if len(key) > 12 else "***"


def selftest() -> int:
    """探活：验证 API Key 与各端点可用。"""
    try:
        key = load_api_key()
    except CourseReviewError as e:
        print(f"❌ {e}")
        return 1
    print(f"🔑 API Key: {_mask(key)}")
    checks = [
        ("搜索  /api/course?q=", lambda: search_courses("传热学", limit=3)["total"]),
        ("详情  /api/course/{id}", lambda: get_course_detail(6807)["name"]),
        ("评价  /api/course/{id}/review", lambda: get_course_reviews(6807, limit=1)["total"]),
    ]
    ok = True
    for label, fn in checks:
        try:
            print(f"  ✅ {label} -> {fn()}")
        except CourseReviewError as e:
            ok = False
            print(f"  ❌ {label} -> {e}")
    return 0 if ok else 1


# ===== CLI =====

HELP = """
📖 SJTU 选课社区 (jCourse) 课程评价查询
────────────────────────────────────────────
  search  <关键词>          搜索课程（名称/课号/老师）
  detail  <课程ID>          课程详情 + 同课号老师对比
  reviews <课程ID> [条数]   查看某门课程的评价
  compare <课程名>          同名课程不同老师评分对比
  selftest                  检查 API Key 与连通性
  help                      显示帮助

示例:
  python3 sjtu_course_review.py search 传热学
  python3 sjtu_course_review.py detail 6807
  python3 sjtu_course_review.py reviews 6807 5
  python3 sjtu_course_review.py compare 传热学

认证: 在 config.json 设置 "jcourse_api_key"，或环境变量 JCOURSE_API_KEY。
"""


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    cmd = argv[0]
    try:
        if cmd == "help":
            print(HELP)
        elif cmd == "selftest":
            return selftest()
        elif cmd == "search":
            if len(argv) < 2:
                print("用法: search <关键词>")
                return 1
            print_search_results(search_courses(" ".join(argv[1:])))
        elif cmd == "detail":
            if len(argv) < 2 or not argv[1].isdigit():
                print("用法: detail <课程ID>")
                return 1
            print_course_detail(get_course_detail(int(argv[1])))
        elif cmd == "reviews":
            if len(argv) < 2 or not argv[1].isdigit():
                print("用法: reviews <课程ID> [条数]")
                return 1
            limit = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else DEFAULT_REVIEW_LIMIT
            print_reviews(int(argv[1]), get_course_reviews(int(argv[1]), limit))
        elif cmd == "compare":
            if len(argv) < 2:
                print("用法: compare <课程名>")
                return 1
            print_teacher_comparison(compare_teachers(" ".join(argv[1:])))
        else:
            print(f"未知命令: {cmd}")
            print(HELP)
            return 1
    except CourseReviewError as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
