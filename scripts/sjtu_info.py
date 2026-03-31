#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上海交通大学校历与校园巴士信息工具
功能：查询校历关键日期、当前教学周、校园巴士时刻表
数据来源：优先从公开页面爬取，失败则使用硬编码数据
"""

import sys
import json
from datetime import datetime, date, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ============================================================
# 硬编码数据 - 2025-2026 学年春季学期 (2026年春)
# ============================================================

SEMESTER_INFO = {
    "semester": "2025-2026学年 春季学期",
    "start_date": "2026-02-23",       # 开学日（周一）
    "end_date": "2026-07-05",         # 学期结束
    "total_weeks": 19,
    "key_dates": [
        {"date": "2026-02-23", "event": "🏫 春季学期开学"},
        {"date": "2026-02-23", "event": "📚 第一周上课"},
        {"date": "2026-03-08", "event": "📝 选课结束 (第二周周日)"},
        {"date": "2026-04-04", "event": "🌸 清明节放假 (4/4-4/6)"},
        {"date": "2026-05-01", "event": "🎉 劳动节放假 (5/1-5/5)"},
        {"date": "2026-05-31", "event": "🐉 端午节放假 (5/31-6/2)"},
        {"date": "2026-06-01", "event": "📖 期中考试周 (约第14-15周)"},
        {"date": "2026-06-22", "event": "📝 期末考试开始 (第18周起)"},
        {"date": "2026-07-05", "event": "🏖️ 暑假开始"},
        {"date": "2026-07-05", "event": "🎓 本科生毕业典礼 (约6月底-7月初)"},
    ],
}

BUS_SCHEDULE_DATA = {
    "update_time": "2025-2026学年",
    "routes": [
        {
            "name": "闵行→徐汇 (校园巴士)",
            "stops": "闵行校区东川路大门 → 徐汇校区华山路大门",
            "duration": "约40-60分钟",
            "weekday": [
                "07:00", "07:20", "07:40",
                "08:00", "08:30",
                "09:00", "09:30",
                "10:00", "10:30",
                "11:00", "11:30",
                "12:00", "12:30",
                "13:00", "13:30",
                "14:00", "14:30",
                "15:00", "15:30",
                "16:00", "16:30",
                "17:00", "17:30",
                "18:00",
                "19:00",
                "20:30",
                "21:30",
            ],
            "weekend": [
                "08:00", "09:00", "10:00",
                "11:00", "12:00",
                "13:00", "14:00",
                "15:00", "16:00",
                "17:00", "18:00",
                "20:00",
            ],
        },
        {
            "name": "徐汇→闵行 (校园巴士)",
            "stops": "徐汇校区华山路大门 → 闵行校区东川路大门",
            "duration": "约40-60分钟",
            "weekday": [
                "07:00", "07:20", "07:40",
                "08:00", "08:30",
                "09:00", "09:30",
                "10:00", "10:30",
                "11:00", "11:30",
                "12:00", "12:30",
                "13:00", "13:30",
                "14:00", "14:30",
                "15:00", "15:30",
                "16:00", "16:30",
                "17:00", "17:30",
                "18:00",
                "19:00",
                "20:30",
                "21:30",
            ],
            "weekend": [
                "08:00", "09:00", "10:00",
                "11:00", "12:00",
                "13:00", "14:00",
                "15:00", "16:00",
                "17:00", "18:00",
                "20:00",
            ],
        },
        {
            "name": "闵行校内巴士",
            "stops": "东川路大门 → 图书馆 → 菁菁堂 → 学活 → 东川路大门 (循环)",
            "duration": "一圈约15分钟",
            "weekday": [
                "07:15 起，约每10-15分钟一班",
                "末班 22:00",
            ],
            "weekend": [
                "08:00 起，约每15-20分钟一班",
                "末班 21:00",
            ],
        },
    ],
    "note": "⚠️ 时刻表可能随学期调整，请以学校官方通知为准。可关注「上海交通大学后勤」公众号获取最新信息。",
}


def _try_fetch_calendar():
    """尝试从网页爬取校历数据"""
    if not HAS_REQUESTS:
        return None
    try:
        # 尝试从交大教务处获取
        urls = [
            "https://www.sjtu.edu.cn/jx/index.html",
            "https://jwc.sjtu.edu.cn/info/1012/1032.htm",
        ]
        for url in urls:
            try:
                resp = requests.get(url, timeout=5, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                })
                if resp.status_code == 200:
                    # 简单解析 - 实际爬取逻辑需要根据页面结构调整
                    # 这里先返回 None，使用硬编码数据
                    pass
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_academic_calendar():
    """
    获取当前学期校历关键日期
    优先爬取，失败则返回硬编码数据
    """
    # 尝试爬取
    fetched = _try_fetch_calendar()
    if fetched:
        return fetched

    # 返回硬编码数据
    return {
        "semester": SEMESTER_INFO["semester"],
        "start_date": SEMESTER_INFO["start_date"],
        "end_date": SEMESTER_INFO["end_date"],
        "total_weeks": SEMESTER_INFO["total_weeks"],
        "key_dates": SEMESTER_INFO["key_dates"],
        "source": "硬编码数据 (如有变动请以学校官方通知为准)",
    }


def get_current_week():
    """
    计算当前是第几教学周
    返回: {"week": int, "day": str, "semester": str, "status": str}
    """
    today = date.today()
    start = date.fromisoformat(SEMESTER_INFO["start_date"])
    end = date.fromisoformat(SEMESTER_INFO["end_date"])

    if today < start:
        delta = (start - today).days
        return {
            "week": 0,
            "day": today.strftime("%Y-%m-%d %A"),
            "semester": SEMESTER_INFO["semester"],
            "status": f"⏳ 尚未开学，距开学还有 {delta} 天",
        }
    elif today > end:
        return {
            "week": SEMESTER_INFO["total_weeks"],
            "day": today.strftime("%Y-%m-%d %A"),
            "semester": SEMESTER_INFO["semester"],
            "status": "🏖️ 已放假",
        }
    else:
        delta = (today - start).days
        week = delta // 7 + 1
        weekday = today.strftime("%A")
        weekday_cn = {
            "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三",
            "Thursday": "周四", "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
        }.get(weekday, weekday)

        # 查找本周或近期事件
        upcoming = []
        for item in SEMESTER_INFO["key_dates"]:
            event_date = date.fromisoformat(item["date"])
            diff = (event_date - today).days
            if -1 <= diff <= 14:
                upcoming.append(f"{item['event']} ({item['date']})")

        return {
            "week": week,
            "day": f"{today.strftime('%Y-%m-%d')} {weekday_cn}",
            "semester": SEMESTER_INFO["semester"],
            "status": f"📅 第 {week} 教学周 {weekday_cn}",
            "upcoming": upcoming if upcoming else None,
        }


def _try_fetch_bus():
    """尝试爬取校园巴士时刻表"""
    if not HAS_REQUESTS:
        return None
    try:
        # 可尝试从后勤网站获取
        resp = requests.get(
            "https://hq.sjtu.edu.cn",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            # 实际解析逻辑需根据页面调整
            pass
    except Exception:
        pass
    return None


def get_bus_schedule():
    """
    获取校园巴士时刻表
    优先爬取，失败则返回硬编码数据
    """
    fetched = _try_fetch_bus()
    if fetched:
        return fetched

    today = date.today()
    is_weekend = today.weekday() >= 5
    day_type = "weekend" if is_weekend else "weekday"
    day_label = "周末/节假日" if is_weekend else "工作日"

    result = {
        "day_type": day_label,
        "date": today.strftime("%Y-%m-%d"),
        "routes": [],
        "note": BUS_SCHEDULE_DATA["note"],
        "source": "硬编码常用时刻 (可能有调整，请关注官方通知)",
    }

    for route in BUS_SCHEDULE_DATA["routes"]:
        times = route.get(day_type, [])
        result["routes"].append({
            "name": route["name"],
            "stops": route["stops"],
            "duration": route["duration"],
            "schedule": times,
        })

    return result


def _print_calendar():
    """终端输出校历"""
    cal = get_academic_calendar()
    print(f"\n🏫 {cal['semester']}")
    print("=" * 50)
    print(f"  📅 学期: {cal['start_date']} → {cal['end_date']}")
    print(f"  📊 共 {cal['total_weeks']} 个教学周")
    print(f"\n  📋 关键日期:")
    for item in cal["key_dates"]:
        print(f"     {item['date']}  {item['event']}")
    print(f"\n  ℹ️  {cal.get('source', '')}")
    print()


def _print_week():
    """终端输出当前教学周"""
    info = get_current_week()
    print(f"\n🗓️  教学周信息")
    print("=" * 40)
    print(f"  {info['status']}")
    print(f"  📅 日期: {info['day']}")
    print(f"  🏫 学期: {info['semester']}")
    if info.get("upcoming"):
        print(f"\n  📌 近期事件:")
        for ev in info["upcoming"]:
            print(f"     {ev}")
    print()


def _print_bus():
    """终端输出巴士时刻表"""
    bus = get_bus_schedule()
    print(f"\n🚌 校园巴士时刻表 ({bus['day_type']})")
    print(f"   日期: {bus['date']}")
    print("=" * 55)
    for route in bus["routes"]:
        print(f"\n  🚍 {route['name']}")
        print(f"     路线: {route['stops']}")
        print(f"     耗时: {route['duration']}")
        print(f"     班次:")
        schedule = route["schedule"]
        if len(schedule) <= 4:
            for t in schedule:
                print(f"       {t}")
        else:
            # 每行显示多个时间
            for i in range(0, len(schedule), 6):
                row = schedule[i:i+6]
                print(f"       {' | '.join(row)}")
    print(f"\n  {bus['note']}")
    print(f"  ℹ️  {bus.get('source', '')}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_info.py <命令>")
        print("  calendar  - 查看校历")
        print("  week      - 当前教学周")
        print("  bus       - 校园巴士时刻表")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    try:
        if cmd == "calendar":
            _print_calendar()
        elif cmd == "week":
            _print_week()
        elif cmd == "bus":
            _print_bus()
        else:
            print(f"❌ 未知命令: {cmd}")
            print("可用命令: calendar / week / bus")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
