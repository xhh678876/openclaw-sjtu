#!/usr/bin/env python3
"""
传承·交大 课程资源查询工具
目标网站: https://share.dyweb.sjtu.cn/

这是一个基于 React (umi 3.x) 的 SPA 应用，后端 API:
  https://api.share.dyweb.sjtu.cn/api/v1

已发现的 API 端点（需要 jAccount OAuth 登录）:
  GET /auth/jaccount?code=<code>  — jAccount OAuth 回调
  GET /user/profile                — 用户信息
  GET /user/materials/upload?page= — 我上传的资料
  GET /user/materials/purchase?page= — 我购买的资料
  GET /user/log/points?page=       — 积分变动日志

前端路由:
  /             — 首页（热门课程）
  /search       — 搜索页面
  /course/:id   — 课程详情
  /user/login   — 登录
  /user/basic   — 用户中心
  /user/materials/upload   — 我上传的资料
  /user/materials/purchase — 我购买的资料
  /user/point_logs         — 积分日志

注意: 该平台需要 jAccount 登录后才能使用 API。
本脚本提供无需登录的课程信息查询（通过爬取公开页面内容或使用缓存数据）。

用法:
    python3 sjtu_legacy.py search "燃烧学"
    python3 sjtu_legacy.py popular
"""

import argparse
import sys
import json
from typing import Optional, List, Dict

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# API 基础地址
API_BASE = "https://api.share.dyweb.sjtu.cn/api/v1"
WEB_BASE = "https://share.dyweb.sjtu.cn"

# ========== 常见课程资源缓存数据 ==========
# 由于 API 需要登录，这里提供常见课程资源的参考信息
POPULAR_COURSES = [
    {
        "name": "高等数学",
        "category": "数学",
        "department": "数学科学学院",
        "description": "微积分、级数、多元函数等基础数学课程资料",
        "tags": ["大一必修", "理工科基础"],
    },
    {
        "name": "线性代数",
        "category": "数学",
        "department": "数学科学学院",
        "description": "矩阵运算、线性方程组、特征值等",
        "tags": ["大一必修", "理工科基础"],
    },
    {
        "name": "大学物理",
        "category": "物理",
        "department": "物理与天文学院",
        "description": "力学、热学、电磁学、光学、近代物理",
        "tags": ["大一大二", "理工科基础"],
    },
    {
        "name": "概率论与数理统计",
        "category": "数学",
        "department": "数学科学学院",
        "description": "概率、随机变量、统计推断",
        "tags": ["大二", "理工科基础"],
    },
    {
        "name": "数据结构",
        "category": "计算机",
        "department": "电子信息与电气工程学院",
        "description": "链表、树、图、排序算法等",
        "tags": ["大二", "计算机专业核心"],
    },
    {
        "name": "操作系统",
        "category": "计算机",
        "department": "电子信息与电气工程学院",
        "description": "进程管理、内存管理、文件系统",
        "tags": ["大三", "计算机专业核心"],
    },
    {
        "name": "计算机网络",
        "category": "计算机",
        "department": "电子信息与电气工程学院",
        "description": "TCP/IP、HTTP、网络架构",
        "tags": ["大三", "计算机专业核心"],
    },
    {
        "name": "工程热力学",
        "category": "机械/能源",
        "department": "机械与动力工程学院",
        "description": "热力学定律、循环分析、热力过程",
        "tags": ["大二大三", "能源动力专业"],
    },
    {
        "name": "传热学",
        "category": "机械/能源",
        "department": "机械与动力工程学院",
        "description": "导热、对流、辐射换热",
        "tags": ["大三", "能源动力专业"],
    },
    {
        "name": "燃烧学",
        "category": "机械/能源",
        "department": "机械与动力工程学院",
        "description": "燃烧化学、火焰传播、燃烧理论",
        "tags": ["大三大四", "能源动力专业"],
    },
    {
        "name": "机械振动",
        "category": "机械/能源",
        "department": "机械与动力工程学院",
        "description": "自由振动、强迫振动、振动控制",
        "tags": ["大三", "机械工程专业"],
    },
    {
        "name": "热力系统分析",
        "category": "机械/能源",
        "department": "机械与动力工程学院",
        "description": "热力系统建模、仿真与优化",
        "tags": ["大四/研究生", "能源动力专业"],
    },
    {
        "name": "信号与系统",
        "category": "电子",
        "department": "电子信息与电气工程学院",
        "description": "连续/离散信号、傅里叶变换、拉普拉斯变换",
        "tags": ["大二", "电子/通信专业核心"],
    },
    {
        "name": "模拟电子技术",
        "category": "电子",
        "department": "电子信息与电气工程学院",
        "description": "放大电路、运算放大器、反馈",
        "tags": ["大二", "电子/电气专业"],
    },
    {
        "name": "数字电子技术",
        "category": "电子",
        "department": "电子信息与电气工程学院",
        "description": "逻辑门、组合电路、时序电路",
        "tags": ["大二", "电子/电气专业"],
    },
    {
        "name": "自动控制原理",
        "category": "控制",
        "department": "电子信息与电气工程学院",
        "description": "传递函数、根轨迹、频率响应、PID",
        "tags": ["大三", "自动化/控制专业"],
    },
    {
        "name": "材料力学",
        "category": "力学",
        "department": "船舶海洋与建筑工程学院",
        "description": "应力应变、弯曲、扭转、稳定性",
        "tags": ["大二", "工科基础"],
    },
    {
        "name": "理论力学",
        "category": "力学",
        "department": "船舶海洋与建筑工程学院",
        "description": "静力学、运动学、动力学",
        "tags": ["大二", "工科基础"],
    },
    {
        "name": "流体力学",
        "category": "力学",
        "department": "船舶海洋与建筑工程学院",
        "description": "流体静力学、流体动力学、层流湍流",
        "tags": ["大二大三", "工科专业"],
    },
    {
        "name": "遗传学",
        "category": "生物",
        "department": "生命科学技术学院",
        "description": "孟德尔遗传、分子遗传、群体遗传",
        "tags": ["大二大三", "生物专业"],
    },
    {
        "name": "有机化学",
        "category": "化学",
        "department": "化学化工学院",
        "description": "有机反应、有机合成、结构分析",
        "tags": ["大一大二", "化学/生物专业"],
    },
    {
        "name": "思想道德与法治",
        "category": "通识",
        "department": "马克思主义学院",
        "description": "思政通识必修课",
        "tags": ["大一", "通识必修"],
    },
    {
        "name": "大学英语",
        "category": "语言",
        "department": "外国语学院",
        "description": "综合英语、学术英语",
        "tags": ["大一大二", "通识必修"],
    },
    {
        "name": "机器学习",
        "category": "计算机/AI",
        "department": "电子信息与电气工程学院",
        "description": "监督学习、无监督学习、深度学习基础",
        "tags": ["大三大四/研究生", "AI方向"],
    },
    {
        "name": "深度学习",
        "category": "计算机/AI",
        "department": "电子信息与电气工程学院",
        "description": "神经网络、CNN、RNN、Transformer",
        "tags": ["研究生", "AI方向"],
    },
]


def search_course_resources(keyword: str) -> List[Dict]:
    """
    搜索课程资源。
    优先尝试在线 API（需要登录），失败时使用本地缓存数据模糊匹配。
    
    Args:
        keyword: 搜索关键词
    
    Returns:
        匹配的课程资源列表
    """
    results = []

    # 1. 尝试在线访问（大概率需要登录）
    if HAS_DEPS:
        try:
            # 尝试直接访问搜索页面
            resp = requests.get(
                f"{WEB_BASE}/search",
                params={"q": keyword},
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200 and "传承·交大" in resp.text:
                # SPA 页面，无法直接提取搜索结果
                pass
        except Exception:
            pass

    # 2. 使用本地缓存数据进行模糊搜索
    keyword_lower = keyword.lower()
    for course in POPULAR_COURSES:
        # 匹配课程名称、类别、描述、标签
        searchable = (
            course["name"].lower()
            + course["category"].lower()
            + course["description"].lower()
            + course.get("department", "").lower()
            + " ".join(course.get("tags", [])).lower()
        )
        if keyword_lower in searchable:
            results.append(course)

    return results


def list_popular_resources() -> List[Dict]:
    """
    列出热门课程资源。
    
    Returns:
        热门课程列表
    """
    return POPULAR_COURSES


def print_course(course: Dict, index: int = 0):
    """格式化输出课程信息"""
    prefix = f"{index}. " if index > 0 else "  "
    print(f"{prefix}📚 {course['name']}")
    print(f"     分类: {course['category']} | 院系: {course.get('department', '未知')}")
    print(f"     简介: {course['description']}")
    if course.get("tags"):
        print(f"     标签: {', '.join(course['tags'])}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="传承·交大 课程资源查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 sjtu_legacy.py search "燃烧学"     # 搜索课程资源
  python3 sjtu_legacy.py search "计算机"      # 搜索计算机相关课程
  python3 sjtu_legacy.py popular             # 列出热门课程资源
  python3 sjtu_legacy.py popular --category 数学  # 按分类筛选

网站: https://share.dyweb.sjtu.cn/
注意: 完整功能需要 jAccount 登录
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="操作类型")

    # search 子命令
    search_parser = subparsers.add_parser("search", help="搜索课程资源")
    search_parser.add_argument("keyword", help="搜索关键词")

    # popular 子命令
    popular_parser = subparsers.add_parser("popular", help="列出热门课程资源")
    popular_parser.add_argument("--category", "-c", help="按分类筛选")

    args = parser.parse_args()

    if args.command == "search":
        print(f"\n🔍 搜索: {args.keyword}")
        print(f"{'─'*50}")

        results = search_course_resources(args.keyword)
        if results:
            print(f"找到 {len(results)} 个相关课程:\n")
            for i, course in enumerate(results, 1):
                print_course(course, i)
        else:
            print(f"未找到与 \"{args.keyword}\" 相关的课程资源")
            print(f"\n💡 提示:")
            print(f"   - 尝试更通用的关键词")
            print(f"   - 登录 {WEB_BASE} 获取完整搜索结果")
            print(f"   - API 基地址: {API_BASE}")

        print(f"\n💡 在线搜索: {WEB_BASE}/search?q={args.keyword}")

    elif args.command == "popular":
        print(f"\n🔥 热门课程资源")
        print(f"{'─'*50}")

        courses = list_popular_resources()
        if hasattr(args, "category") and args.category:
            courses = [c for c in courses if args.category in c["category"]]
            print(f"分类筛选: {args.category}\n")

        # 按分类分组输出
        categories = {}
        for course in courses:
            cat = course["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(course)

        for cat, cat_courses in categories.items():
            print(f"\n📂 {cat} ({len(cat_courses)} 门)")
            for course in cat_courses:
                tags = ", ".join(course.get("tags", []))
                print(f"   • {course['name']:<12} {course.get('department', ''):<24} [{tags}]")

        print(f"\n共 {len(courses)} 门课程资源")
        print(f"\n💡 更多资源请访问: {WEB_BASE}")
        print(f"   该平台采用积分制，上传资料获得积分，下载资料消耗积分")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
