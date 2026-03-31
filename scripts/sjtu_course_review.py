#!/usr/bin/env python3
"""SJTU 选课社区 (course.sjtu.plus) — 课程评价查询工具

功能：搜索课程、查看评分、获取课程评价、对比不同老师
认证：需要 jAccount 登录后的 session cookie（通过浏览器自动化获取）

API 端点（逆向自前端 JS）：
- GET /api/search/?q=关键词 — 搜索课程
- GET /api/course/{id}/ — 课程详情（评分、学分、院系、其他老师对比）
- GET /api/course-filter/ — 课程分类和院系列表
- GET /api/review/?course_id={id} — 课程评价列表
- GET /api/me/ — 当前用户信息
- GET /api/lesson/ — 课程信息
- GET /api/statistic/ — 统计信息
"""

import os
import sys
import json
import requests
from datetime import datetime

BASE_URL = "https://course.sjtu.plus"
CONFIG_PATH = os.path.expanduser("~/.openclaw/workspace/skills/sjtu-canvas/config.json")

# ===== 配置 =====
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def get_session():
    """获取带认证的 session。
    
    选课社区使用 jAccount OAuth 登录，cookie 需要通过浏览器自动化获取。
    这里尝试从 config.json 读取已保存的 cookie，
    如果没有则提示用户通过浏览器登录。
    """
    config = load_config()
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': BASE_URL,
        'Accept': 'application/json',
    })
    
    # 尝试从 config 读取 cookie
    cookie_str = config.get("course_sjtu_cookie", "")
    if cookie_str:
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                s.cookies.set(k.strip(), v.strip(), domain="course.sjtu.plus")
    
    # 也尝试从 cookie 文件读取（浏览器自动化导出的）
    cookie_file = os.path.join(os.path.dirname(CONFIG_PATH), "course_sjtu_cookies.txt")
    if not cookie_str and os.path.exists(cookie_file):
        try:
            with open(cookie_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        s.cookies.set(k.strip(), v.strip(), domain="course.sjtu.plus")
        except Exception:
            pass
    
    return s

def _try_browser_fetch(url):
    """尝试通过本地浏览器代理调 API（利用浏览器已登录的 session cookie）
    
    依赖 OpenClaw browser 工具在 localhost 开的 CDP 端口。
    如果浏览器不可用或未登录，返回 None。
    """
    try:
        import subprocess
        # 用 curl 通过 CDP 获取页面列表
        result = subprocess.run(
            ['curl', '-s', '--connect-timeout', '2', 'http://localhost:9222/json'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        tabs = json.loads(result.stdout)
        # 找 course.sjtu.plus 的 tab
        target = None
        for t in tabs:
            if 'course.sjtu.plus' in t.get('url', ''):
                target = t
                break
        if not target:
            return None
        # 不走 CDP websocket（太复杂），直接用浏览器已有的 cookie 文件
        return None
    except Exception:
        return None


def api_get(path, params=None):
    """调用选课社区 API。
    
    优先使用 config.json 中的 cookie，
    如果 cookie 无效或未配置，提示用户登录并提取 cookie。
    """
    s = get_session()
    url = f"{BASE_URL}{path}"
    try:
        r = s.get(url, params=params, timeout=15)
        if r.status_code == 403:
            return {"error": "未登录。course.sjtu.plus 有 CDN 反爬机制，Python requests 无法直接获取 session。\n"
                    "✅ 解决方案: 让小灰灰通过浏览器代理调 API（浏览器已登录，直接可用）\n"
                    "💡 用法: 直接跟小灰灰说「帮我查一下传热学的课程评价」，小灰灰会自动用浏览器调 API"}
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"请求失败: {e}"}
    except json.JSONDecodeError:
        return {"error": f"响应不是 JSON: {r.text[:200]}"}

# ===== 核心功能 =====

def search_courses(keyword, page_size=20):
    """搜索课程
    
    Args:
        keyword: 搜索关键词（课程名、课号、老师名）
        page_size: 返回数量
    
    Returns:
        课程列表，每项包含 id, code, name, teacher, department, rating
    """
    data = api_get("/api/search/", {"q": keyword, "page_size": page_size})
    if "error" in data:
        return data
    
    results = []
    for c in data.get("results", []):
        rating = c.get("rating", {})
        results.append({
            "id": c["id"],
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "teacher": c.get("teacher", ""),
            "department": c.get("department", ""),
            "credit": c.get("credit", 0),
            "rating_avg": rating.get("avg"),
            "rating_count": rating.get("count", 0),
        })
    
    return {
        "total": data.get("count", 0),
        "results": results,
    }

def get_course_detail(course_id):
    """获取课程详情，包含评分和其他老师对比
    
    Args:
        course_id: 课程 ID（从搜索结果中获取）
    
    Returns:
        课程详情，包含 name, code, teacher, rating, related_teachers 等
    """
    data = api_get(f"/api/course/{course_id}/")
    if "error" in data:
        return data
    
    related = []
    for t in data.get("related_teachers", []):
        related.append({
            "id": t.get("id"),
            "teacher": t.get("tname", ""),
            "rating_avg": t.get("avg"),
            "rating_count": t.get("count", 0),
        })
    # 按评分降序排列
    related.sort(key=lambda x: (x["rating_avg"] or 0), reverse=True)
    
    main_teacher = data.get("main_teacher", {})
    rating = data.get("rating", {})
    
    return {
        "id": data["id"],
        "code": data.get("code", ""),
        "name": data.get("name", ""),
        "teacher": main_teacher.get("name", ""),
        "department": data.get("department", ""),
        "credit": data.get("credit", 0),
        "rating_avg": rating.get("avg"),
        "rating_count": rating.get("count", 0),
        "related_teachers": related,
        "moderator_remark": data.get("moderator_remark"),
    }

def get_course_filters():
    """获取课程分类和院系列表，用于筛选"""
    data = api_get("/api/course-filter/")
    if "error" in data:
        return data
    
    categories = [{"id": c["id"], "name": c["name"], "count": c["count"]} 
                  for c in data.get("categories", [])]
    departments = [{"id": d["id"], "name": d["name"], "count": d["count"]}
                   for d in data.get("departments", [])]
    
    # 按课程数降序
    categories.sort(key=lambda x: x["count"], reverse=True)
    departments.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "categories": categories,
        "departments": departments,
    }

def compare_teachers(course_name):
    """搜索某门课程的所有老师并对比评分
    
    Args:
        course_name: 课程名称
    
    Returns:
        各老师的评分对比
    """
    search_result = search_courses(course_name)
    if "error" in search_result:
        return search_result
    
    # 按课程名精确匹配
    exact_matches = [c for c in search_result["results"] if c["name"] == course_name]
    if not exact_matches:
        # 模糊匹配
        exact_matches = [c for c in search_result["results"] if course_name in c["name"]]
    
    if not exact_matches:
        return {"error": f"未找到课程: {course_name}", "suggestions": [c["name"] for c in search_result["results"][:5]]}
    
    # 获取第一个匹配课程的详情（包含其他老师对比）
    first = exact_matches[0]
    detail = get_course_detail(first["id"])
    if "error" in detail:
        return detail
    
    # 合并当前老师和其他老师
    all_teachers = [{
        "teacher": detail["teacher"],
        "rating_avg": detail["rating_avg"],
        "rating_count": detail["rating_count"],
        "is_current": True,
    }]
    
    for t in detail.get("related_teachers", []):
        if t["teacher"] != detail["teacher"]:
            all_teachers.append({
                "teacher": t["teacher"],
                "rating_avg": t["rating_avg"],
                "rating_count": t["rating_count"],
                "is_current": False,
                "course_id": t.get("id"),
            })
    
    # 按评分降序
    all_teachers.sort(key=lambda x: (x["rating_avg"] or 0), reverse=True)
    
    return {
        "course": detail["name"],
        "code": detail["code"],
        "department": detail["department"],
        "credit": detail["credit"],
        "teachers": all_teachers,
    }

# ===== 格式化输出 =====

def print_search_results(results):
    """格式化打印搜索结果"""
    if "error" in results:
        print(f"❌ {results['error']}")
        return
    
    print(f"\n🔍 搜索到 {results['total']} 门课程")
    print("─" * 60)
    
    for c in results["results"]:
        rating_str = f"⭐ {c['rating_avg']:.1f} ({c['rating_count']}人)" if c['rating_avg'] else "暂无评价"
        print(f"  [{c['code']}] {c['name']}")
        print(f"    👨‍🏫 {c['teacher']} | 🏢 {c['department']} | 💯 {c['credit']}学分 | {rating_str}")
        print()

def print_course_detail(detail):
    """格式化打印课程详情"""
    if "error" in detail:
        print(f"❌ {detail['error']}")
        return
    
    rating_str = f"⭐ {detail['rating_avg']:.1f} ({detail['rating_count']}人)" if detail['rating_avg'] else "暂无评价"
    
    print(f"\n📚 {detail['name']}（{detail['teacher']}）")
    print("─" * 60)
    print(f"  课号: {detail['code']}")
    print(f"  学分: {detail['credit']}")
    print(f"  院系: {detail['department']}")
    print(f"  评分: {rating_str}")
    
    if detail.get("related_teachers"):
        print(f"\n  📊 其他老师对比:")
        for t in detail["related_teachers"]:
            if t["rating_avg"] and t["rating_count"] > 0:
                bar = "█" * int(t["rating_avg"]) + "░" * (5 - int(t["rating_avg"]))
                print(f"    {t['teacher']:8s} {bar} {t['rating_avg']:.1f} ({t['rating_count']}人)")
            else:
                print(f"    {t['teacher']:8s} 暂无评价")

def print_teacher_comparison(comparison):
    """格式化打印老师对比"""
    if "error" in comparison:
        print(f"❌ {comparison['error']}")
        if "suggestions" in comparison:
            print(f"  💡 你是不是在找: {', '.join(comparison['suggestions'])}")
        return
    
    print(f"\n📊 {comparison['course']}（{comparison['code']}）老师评分对比")
    print(f"  {comparison['department']} | {comparison['credit']}学分")
    print("─" * 60)
    
    for i, t in enumerate(comparison["teachers"], 1):
        name = t["teacher"]
        if t.get("is_current"):
            name += " ← 你的老师"
        
        if t["rating_avg"] and t["rating_count"] > 0:
            bar = "█" * int(t["rating_avg"]) + "░" * (5 - int(t["rating_avg"]))
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            print(f"  {emoji} {name:15s} {bar} {t['rating_avg']:.1f}/5 ({t['rating_count']}人评价)")
        else:
            print(f"     {name:15s} 暂无评价")

# ===== CLI =====

def print_help():
    print("""
📖 SJTU 选课社区查询工具
────────────────────────────────────
用法:
  python3 sjtu_course_review.py search <关键词>     搜索课程
  python3 sjtu_course_review.py detail <课程ID>     查看课程详情
  python3 sjtu_course_review.py compare <课程名>    对比不同老师评分
  python3 sjtu_course_review.py filters             查看课程分类和院系
  python3 sjtu_course_review.py help                显示帮助

示例:
  python3 sjtu_course_review.py search 燃烧学
  python3 sjtu_course_review.py detail 7052
  python3 sjtu_course_review.py compare 传热学
  
⚠️  需要先通过浏览器登录 course.sjtu.plus（jAccount 认证）
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "help":
        print_help()
    
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("用法: python3 sjtu_course_review.py search <关键词>")
            sys.exit(1)
        keyword = " ".join(sys.argv[2:])
        results = search_courses(keyword)
        print_search_results(results)
    
    elif cmd == "detail":
        if len(sys.argv) < 3:
            print("用法: python3 sjtu_course_review.py detail <课程ID>")
            sys.exit(1)
        course_id = int(sys.argv[2])
        detail = get_course_detail(course_id)
        print_course_detail(detail)
    
    elif cmd == "compare":
        if len(sys.argv) < 3:
            print("用法: python3 sjtu_course_review.py compare <课程名>")
            sys.exit(1)
        course_name = " ".join(sys.argv[2:])
        comparison = compare_teachers(course_name)
        print_teacher_comparison(comparison)
    
    elif cmd == "filters":
        filters = get_course_filters()
        if "error" in filters:
            print(f"❌ {filters['error']}")
        else:
            print("\n📁 课程分类:")
            for c in filters["categories"]:
                print(f"  {c['name']:15s} ({c['count']}门)")
            print(f"\n🏢 开课院系 (前20):")
            for d in filters["departments"][:20]:
                print(f"  {d['name']:20s} ({d['count']}门)")
    
    else:
        print(f"未知命令: {cmd}")
        print_help()
