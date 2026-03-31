#!/usr/bin/env python3
"""
SJTU 空教室查询工具
目标网站: https://ids.sjtu.edu.cn/
注意: ids.sjtu.edu.cn 是 JS 渲染的 SPA，无公开 API，需要 jAccount 登录。
本脚本提供闵行校区教学楼信息查询及课表辅助功能。

已发现的相关端点（需要登录）:
- https://ids.sjtu.edu.cn/build/goSearchRoomPage?type=HDJS  (教室查询页面)
- https://i.sjtu.edu.cn/jxzxjhgl/kcapjsgl_cxKcapjsxxIndex.html (教务系统课程安排)
- https://developer.sjtu.edu.cn/api/education.html (开发者平台教育API)

用法:
    python3 sjtu_classroom.py empty [--building 东上院] [--date 2024-03-25]
    python3 sjtu_classroom.py info [--building 东上院]
"""

import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

# ========== 闵行校区教学楼硬编码数据 ==========

BUILDINGS = {
    "东上院": {
        "code": "DSY",
        "full_name": "东上院（理科楼群）",
        "location": "闵行校区东区",
        "floors": 4,
        "rooms": [
            # 格式: (教室编号, 容量, 类型)
            ("101", 120, "阶梯教室"),
            ("102", 120, "阶梯教室"),
            ("103", 80, "多媒体教室"),
            ("104", 80, "多媒体教室"),
            ("105", 60, "普通教室"),
            ("200", 200, "大阶梯教室"),
            ("201", 60, "多媒体教室"),
            ("202", 60, "多媒体教室"),
            ("203", 60, "多媒体教室"),
            ("204", 60, "多媒体教室"),
            ("301", 60, "多媒体教室"),
            ("302", 60, "多媒体教室"),
            ("303", 60, "多媒体教室"),
            ("304", 60, "多媒体教室"),
            ("401", 45, "小教室"),
            ("402", 45, "小教室"),
            ("403", 45, "小教室"),
            ("404", 45, "小教室"),
        ],
        "description": "主要用于理工科课程教学"
    },
    "东中院": {
        "code": "DZY",
        "full_name": "东中院",
        "location": "闵行校区东区",
        "floors": 4,
        "rooms": [
            ("1-101", 120, "阶梯教室"),
            ("1-102", 80, "多媒体教室"),
            ("1-201", 60, "多媒体教室"),
            ("1-202", 60, "多媒体教室"),
            ("1-301", 60, "多媒体教室"),
            ("1-302", 60, "多媒体教室"),
            ("2-101", 120, "阶梯教室"),
            ("2-102", 80, "多媒体教室"),
            ("2-201", 60, "多媒体教室"),
            ("2-202", 60, "多媒体教室"),
            ("2-301", 60, "多媒体教室"),
            ("2-302", 60, "多媒体教室"),
            ("3-101", 80, "多媒体教室"),
            ("3-201", 60, "多媒体教室"),
            ("3-301", 60, "多媒体教室"),
            ("4-101", 80, "多媒体教室"),
            ("4-201", 60, "多媒体教室"),
        ],
        "description": "综合教学楼，含多种教室类型"
    },
    "东下院": {
        "code": "DXY",
        "full_name": "东下院",
        "location": "闵行校区东区",
        "floors": 3,
        "rooms": [
            ("101", 200, "大阶梯教室"),
            ("102", 120, "阶梯教室"),
            ("103", 80, "多媒体教室"),
            ("201", 60, "多媒体教室"),
            ("202", 60, "多媒体教室"),
            ("203", 60, "多媒体教室"),
            ("301", 60, "多媒体教室"),
            ("302", 60, "多媒体教室"),
            ("303", 45, "小教室"),
        ],
        "description": "历史悠久的教学楼"
    },
    "陈瑞球楼": {
        "code": "CRQ",
        "full_name": "陈瑞球楼",
        "location": "闵行校区东区",
        "floors": 5,
        "rooms": [
            ("101", 200, "报告厅"),
            ("102", 120, "阶梯教室"),
            ("201", 80, "多媒体教室"),
            ("202", 80, "多媒体教室"),
            ("203", 60, "多媒体教室"),
            ("204", 60, "多媒体教室"),
            ("301", 80, "多媒体教室"),
            ("302", 80, "多媒体教室"),
            ("303", 60, "多媒体教室"),
            ("304", 60, "多媒体教室"),
            ("401", 60, "多媒体教室"),
            ("402", 60, "多媒体教室"),
            ("501", 45, "研讨室"),
            ("502", 45, "研讨室"),
        ],
        "description": "现代化教学楼，配备先进多媒体设备"
    },
    "上院": {
        "code": "SY",
        "full_name": "上院",
        "location": "闵行校区中心区域",
        "floors": 3,
        "rooms": [
            ("100", 300, "大礼堂"),
            ("101", 120, "阶梯教室"),
            ("102", 80, "多媒体教室"),
            ("201", 60, "多媒体教室"),
            ("202", 60, "多媒体教室"),
            ("301", 60, "多媒体教室"),
            ("302", 45, "小教室"),
        ],
        "description": "标志性教学建筑"
    },
    "中院": {
        "code": "ZY",
        "full_name": "中院",
        "location": "闵行校区中心区域",
        "floors": 3,
        "rooms": [
            ("101", 80, "多媒体教室"),
            ("102", 80, "多媒体教室"),
            ("201", 60, "多媒体教室"),
            ("202", 60, "多媒体教室"),
            ("301", 60, "多媒体教室"),
            ("302", 60, "多媒体教室"),
        ],
        "description": "综合教学楼"
    },
    "下院": {
        "code": "XY",
        "full_name": "下院",
        "location": "闵行校区中心区域",
        "floors": 3,
        "rooms": [
            ("101", 120, "阶梯教室"),
            ("102", 80, "多媒体教室"),
            ("201", 60, "多媒体教室"),
            ("202", 60, "多媒体教室"),
            ("301", 45, "小教室"),
            ("302", 45, "小教室"),
        ],
        "description": "综合教学楼"
    },
}

# 课程时间段定义（上海交大标准时间表）
TIME_SLOTS = {
    1: ("08:00", "08:45"),
    2: ("08:55", "09:40"),
    3: ("10:00", "10:45"),
    4: ("10:55", "11:40"),
    5: ("12:00", "12:45"),
    6: ("12:55", "13:40"),
    7: ("14:00", "14:45"),
    8: ("14:55", "15:40"),
    9: ("16:00", "16:45"),
    10: ("16:55", "17:40"),
    11: ("18:00", "18:45"),
    12: ("18:55", "19:40"),
    13: ("19:50", "20:35"),
    14: ("20:45", "21:30"),
}


def get_empty_classrooms(building: Optional[str] = None, date: Optional[str] = None):
    """
    查询空闲教室（基于硬编码数据的模拟查询）。
    
    注意: 由于 ids.sjtu.edu.cn 需要 jAccount 登录，此处返回教学楼的教室列表。
    真实的空闲教室查询需要登录后访问:
    https://ids.sjtu.edu.cn/build/goSearchRoomPage?type=HDJS
    
    Args:
        building: 教学楼名称（如 "东上院"），None 则查询所有
        date: 日期字符串 YYYY-MM-DD，默认今天
    
    Returns:
        包含教室信息的列表
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    target_buildings = {}
    if building:
        # 模糊匹配教学楼名称
        for name, info in BUILDINGS.items():
            if building in name or building in info.get("full_name", ""):
                target_buildings[name] = info
        if not target_buildings:
            print(f"⚠️  未找到教学楼: {building}")
            print(f"可用的教学楼: {', '.join(BUILDINGS.keys())}")
            return []
    else:
        target_buildings = BUILDINGS

    results = []
    print(f"\n📅 查询日期: {date}")
    print(f"⚠️  注意: 以下为教学楼教室列表，非实时空闲数据")
    print(f"💡 实时空教室查询请登录: https://ids.sjtu.edu.cn/build/goSearchRoomPage?type=HDJS\n")

    for bname, binfo in target_buildings.items():
        print(f"🏫 {binfo['full_name']} ({binfo['location']})")
        print(f"   📍 {binfo['description']}")
        print(f"   🏢 共 {binfo['floors']} 层, {len(binfo['rooms'])} 间教室")
        print(f"   {'教室编号':<12} {'容量':>6}  {'类型':<12}")
        print(f"   {'─'*35}")
        for room_id, capacity, room_type in binfo["rooms"]:
            room_str = f"{bname} {room_id}"
            print(f"   {room_str:<12} {capacity:>4}人  {room_type:<12}")
            results.append({
                "building": bname,
                "room": room_id,
                "capacity": capacity,
                "type": room_type,
                "full_name": f"{bname} {room_id}",
            })
        print()

    print(f"共 {len(results)} 间教室")
    return results


def get_classroom_schedule(building: str, room: Optional[str] = None):
    """
    查询某教室的课程安排信息。
    
    注意: 需要 jAccount 登录才能获取实时课表。
    
    Args:
        building: 教学楼名称
        room: 教室编号（可选）
    """
    # 查找教学楼
    target = None
    for name, info in BUILDINGS.items():
        if building in name or building in info.get("full_name", ""):
            target = (name, info)
            break

    if not target:
        print(f"⚠️  未找到教学楼: {building}")
        print(f"可用的教学楼: {', '.join(BUILDINGS.keys())}")
        return

    bname, binfo = target
    print(f"\n🏫 {binfo['full_name']} 教室信息")
    print(f"📍 位置: {binfo['location']}")
    print(f"📝 描述: {binfo['description']}")

    if room:
        # 查找特定教室
        found = False
        for room_id, capacity, room_type in binfo["rooms"]:
            if room == room_id:
                print(f"\n📋 {bname} {room_id}")
                print(f"   容量: {capacity} 人")
                print(f"   类型: {room_type}")
                found = True
                break
        if not found:
            print(f"\n⚠️  未找到教室: {bname} {room}")
            print(f"该楼可用教室:")
            for r_id, _, _ in binfo["rooms"]:
                print(f"  - {r_id}")
    else:
        print(f"\n📋 所有教室:")
        for room_id, capacity, room_type in binfo["rooms"]:
            print(f"   {bname} {room_id}: {capacity}人, {room_type}")

    print(f"\n⏰ 上海交大课程时间表:")
    print(f"   {'节次':>4}  {'时间段':<14}")
    print(f"   {'─'*22}")
    for slot, (start, end) in TIME_SLOTS.items():
        label = ""
        if slot == 1:
            label = " ← 上午"
        elif slot == 5:
            label = " ← 中午"
        elif slot == 7:
            label = " ← 下午"
        elif slot == 11:
            label = " ← 晚上"
        print(f"   第{slot:>2}节  {start}-{end}{label}")

    print(f"\n💡 查看实时课表请登录:")
    print(f"   https://ids.sjtu.edu.cn/build/goSearchRoomPage?type=HDJS")
    print(f"   https://i.sjtu.edu.cn/jxzxjhgl/kcapjsgl_cxKcapjsxxIndex.html")


def main():
    parser = argparse.ArgumentParser(
        description="SJTU 空教室查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 sjtu_classroom.py empty                     # 查看所有教学楼教室
  python3 sjtu_classroom.py empty --building 东上院     # 查看东上院教室
  python3 sjtu_classroom.py info --building 东上院      # 查看教学楼详细信息
  python3 sjtu_classroom.py info --building 陈瑞球楼 --room 101  # 查看特定教室
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="操作类型")

    # empty 子命令
    empty_parser = subparsers.add_parser("empty", help="查询空闲教室")
    empty_parser.add_argument("--building", "-b", help="教学楼名称")
    empty_parser.add_argument("--date", "-d", help="日期 (YYYY-MM-DD)")

    # info 子命令
    info_parser = subparsers.add_parser("info", help="查看教学楼/教室信息")
    info_parser.add_argument("--building", "-b", help="教学楼名称")
    info_parser.add_argument("--room", "-r", help="教室编号")

    args = parser.parse_args()

    if args.command == "empty":
        get_empty_classrooms(building=args.building, date=args.date)
    elif args.command == "info":
        if args.building:
            get_classroom_schedule(args.building, room=args.room)
        else:
            # 列出所有教学楼概览
            print("\n🏫 闵行校区教学楼概览")
            print(f"{'─'*50}")
            for name, info in BUILDINGS.items():
                print(f"  {name:<8} | {info['full_name']:<16} | {len(info['rooms']):>2}间教室 | {info['location']}")
            print(f"\n共 {len(BUILDINGS)} 栋教学楼, "
                  f"{sum(len(b['rooms']) for b in BUILDINGS.values())} 间教室")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
