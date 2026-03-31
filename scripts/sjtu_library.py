#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上海交通大学图书馆信息与座位查询工具

功能：
  - 查询各图书馆基本信息（位置、开放时间、楼层功能）
  - 查询座位预约状态（需 jAccount 认证，当前为信息指引）

座位预约系统调研结果：
  - 预约系统地址: https://libseat.lib.sjtu.edu.cn
  - 认证方式: 需通过 jAccount (https://jaccount.sjtu.edu.cn) 统一身份认证登录
  - 移动端入口: 交我办App → 图书馆座位预约 / 图书馆微信公众号
  - 预约规则:
    * 每日22:00开放次日座位预约
    * 预约生效后须30分钟内到馆刷卡签到
    * 超时未签到自动取消并计违约
  - 技术方案:
    * 接口未公开，需 jAccount OAuth2 认证后获取 session
    * 可参考 SJTU 开发者平台 (https://developer.sjtu.edu.cn) 的 OAuth2 流程
    * 或使用 selenium/playwright 模拟登录后抓取

数据来源：
  - 图书馆官网: https://www.lib.sjtu.edu.cn
  - 开放时间公告: https://www.lib.sjtu.edu.cn/f/content/content.shtml?id=7206
"""

import sys
import json
from datetime import date, datetime

# ============================================================
# 图书馆数据 - 2025-2026 学年
# 数据来源: 图书馆官网 + 公开资料
# ============================================================

LIBRARIES = [
    {
        "name": "闵行校区主馆（新图书馆）",
        "short_name": "主馆",
        "campus": "闵行",
        "location": "闵行校区中心位置，思源湖畔",
        "floors": {
            "1F": "总服务台、新书展示、自助借还、无障碍阅览室",
            "2F": "社科阅览区、研讨室",
            "3F": "自然科学阅览区、研讨室",
            "4F": "特藏与校史展览",
            "B1": "密集书库",
        },
        "hours": {
            "normal": "周一至周日 8:00-22:30",
            "exam": "考试季(第15-18周) 7:30-23:30",
            "vacation": "寒暑假另行通知",
        },
        "seats": "约 2000 个",
        "features": ["自助借还机", "研讨室预约", "打印复印", "饮水机", "无线网络全覆盖"],
    },
    {
        "name": "包玉刚图书馆",
        "short_name": "包图",
        "campus": "闵行",
        "location": "闵行校区西区，靠近第一餐饮大楼",
        "floors": {
            "1F": "自然科学借阅区",
            "2F": "社会科学借阅区、电子阅览室",
            "3F": "外文期刊阅览、研讨室",
            "联楼": "24小时自习空间（独立入口）",
        },
        "hours": {
            "normal": "周一至周日 8:00-22:30",
            "联楼": "24小时开放（全年）",
            "exam": "考试季(第15-18周) 7:30-23:30",
        },
        "seats": "约 1500 个（含联楼约200个）",
        "features": ["24小时自习区(联楼)", "电子阅览室", "研讨室", "安静学习区"],
    },
    {
        "name": "李政道图书馆",
        "short_name": "李图",
        "campus": "闵行",
        "location": "闵行校区东区，靠近第四餐饮大楼和理科群楼",
        "floors": {
            "1F": "李政道生平展览（对公众开放）",
            "2F": "阅览区、自习空间",
            "3F": "阅览区、学术交流空间",
        },
        "hours": {
            "展览区": "周二至周日 9:00-17:00（16:30停止入馆）",
            "阅览区": "按学期安排，详见图书馆通知",
        },
        "seats": "约 500 个",
        "features": ["李政道生平展", "安静学习环境", "学术讲座厅"],
    },
    {
        "name": "徐汇校区图书馆",
        "short_name": "徐汇馆",
        "campus": "徐汇",
        "location": "徐汇校区华山路1954号校内",
        "floors": {
            "1F": "社科阅览室",
            "2F": "图书阅览空间",
            "3F": "自习空间",
        },
        "hours": {
            "normal": "周一至周日 8:00-22:30",
            "exam": "考试季(第15-18周) 7:30-23:30",
        },
        "seats": "约 800 个",
        "features": ["自助借还", "安静学习区"],
    },
    {
        "name": "张江校区图书馆",
        "short_name": "张江馆",
        "campus": "张江",
        "location": "张江高科技园区校区内",
        "hours": {
            "normal": "周一至周五 8:30-17:00",
        },
        "seats": "约 200 个",
        "features": ["小型阅览室"],
    },
]

SEAT_RESERVATION_INFO = {
    "system_url": "https://libseat.lib.sjtu.edu.cn",
    "auth_method": "jAccount 统一身份认证 (https://jaccount.sjtu.edu.cn)",
    "mobile_access": [
        "交我办App → 图书馆 → 座位预约",
        "微信搜索「上海交通大学图书馆」公众号 → 座位预约",
    ],
    "rules": [
        "每日 22:00 开放次日座位预约",
        "可预约全天学习时长",
        "预约生效后 30 分钟内须到馆签到（刷一卡通/校园V卡/思源码）",
        "超时未签到自动取消并计违约",
        "离馆需在系统中释放座位",
    ],
    "tips": [
        "考试季座位紧张，建议提前预约",
        "包图联楼 24 小时开放，适合通宵学习",
        "主馆考试季延长至 23:30",
        "临时离开可使用「暂离」功能（最长30分钟）",
    ],
    "api_status": "⚠️ 座位预约系统无公开API，需 jAccount 认证后访问",
    "future_plan": (
        "如需实现实时座位查询，可通过以下方案：\n"
        "1. jAccount OAuth2 登录后调用 libseat 接口（需抓包分析）\n"
        "2. 使用 Playwright/Selenium 模拟浏览器登录\n"
        "3. 接入 SJTU 开发者平台 (developer.sjtu.edu.cn) 的 OAuth2"
    ),
}


def get_library_info(campus=None):
    """
    获取图书馆基本信息

    Args:
        campus: 校区过滤 ('闵行', '徐汇', '张江')，None 则返回全部

    Returns:
        list[dict]: 图书馆信息列表
    """
    libs = LIBRARIES
    if campus:
        libs = [lib for lib in libs if lib.get("campus", "") == campus]
    return libs


def get_seat_status():
    """
    获取座位预约状态

    当前实现: 返回预约系统信息和使用指引
    未来接入: 需 jAccount 认证后可实现实时座位余量查询

    Returns:
        dict: 座位预约系统信息
    """
    # 由于座位系统需要 jAccount 认证，当前返回使用指引
    today = date.today()
    is_weekend = today.weekday() >= 5

    return {
        "date": today.strftime("%Y-%m-%d"),
        "day_type": "周末" if is_weekend else "工作日",
        "realtime_available": False,
        "message": "座位预约系统需通过 jAccount 认证登录，暂无法提供实时数据",
        "reservation_info": SEAT_RESERVATION_INFO,
        "recommendation": _get_seat_recommendation(is_weekend),
    }


def _get_seat_recommendation(is_weekend=False):
    """根据时间给出座位选择建议"""
    now = datetime.now()
    hour = now.hour

    suggestions = []

    if hour < 8:
        suggestions.append("⏰ 各馆尚未开放，包图联楼24小时可用")
    elif hour < 10:
        suggestions.append("🌅 早间时段，各馆座位相对充裕")
        suggestions.append("📚 建议: 主馆2-3F、包图2F 都是不错的选择")
    elif hour < 14:
        suggestions.append("☀️ 上午/午间时段，座位开始紧张")
        suggestions.append("📚 建议: 主馆高楼层或李政道图书馆通常人少一些")
    elif hour < 18:
        suggestions.append("🌤️ 下午时段，热门区域座位可能紧张")
        suggestions.append("📚 建议: 避开主馆1-2F，尝试3F或包图")
    elif hour < 22:
        suggestions.append("🌙 晚间时段，考试季各馆较满")
        suggestions.append("📚 建议: 包图联楼24h区域是最后的选择")
    else:
        suggestions.append("🌃 已过22:00，仅包图联楼24小时区域开放")

    if is_weekend:
        suggestions.append("📌 周末人流相对工作日少，可直接去主馆或包图")

    return suggestions


def _print_library_info():
    """终端输出图书馆信息"""
    libs = get_library_info()
    print(f"\n📚 上海交通大学图书馆信息")
    print("=" * 60)
    for lib in libs:
        print(f"\n🏛️  {lib['name']}")
        print(f"   📍 位置: {lib['location']}")
        if isinstance(lib.get("hours"), dict):
            for label, time in lib["hours"].items():
                print(f"   🕐 {label}: {time}")
        if lib.get("seats"):
            print(f"   💺 座位: {lib['seats']}")
        if lib.get("features"):
            print(f"   ✨ 特色: {', '.join(lib['features'])}")
        if lib.get("floors"):
            print(f"   🏢 楼层:")
            for floor, desc in lib["floors"].items():
                print(f"      {floor}: {desc}")
    print()


def _print_seat_status():
    """终端输出座位信息"""
    info = get_seat_status()
    print(f"\n💺 座位预约信息 ({info['date']} {info['day_type']})")
    print("=" * 60)

    if not info["realtime_available"]:
        print(f"\n⚠️  {info['message']}")

    res = info["reservation_info"]
    print(f"\n🔗 预约系统: {res['system_url']}")
    print(f"🔐 认证方式: {res['auth_method']}")
    print(f"\n📱 移动端入口:")
    for entry in res["mobile_access"]:
        print(f"   • {entry}")
    print(f"\n📋 预约规则:")
    for rule in res["rules"]:
        print(f"   • {rule}")
    print(f"\n💡 小贴士:")
    for tip in res["tips"]:
        print(f"   • {tip}")

    print(f"\n🎯 当前建议:")
    for sug in info["recommendation"]:
        print(f"   {sug}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_library.py <命令>")
        print()
        print("命令:")
        print("  info    - 查看各图书馆基本信息")
        print("  seats   - 查看座位预约信息")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    try:
        if cmd == "info":
            _print_library_info()
        elif cmd == "seats":
            _print_seat_status()
        else:
            print(f"❌ 未知命令: {cmd}")
            print("可用命令: info / seats")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
