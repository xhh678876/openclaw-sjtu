#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SJTU 课表 & DDL ICS 导出工具
功能：将 Canvas 作业DDL和日历事件导出为标准 ICS 文件，可导入 Apple 日历/Google Calendar
依赖：canvas_api.py（同目录）
"""

import os
import sys
import hashlib
from datetime import datetime, timezone, timedelta

# 同目录导入 canvas_api
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_api import (
    get_all_ddls_via_planner,
    list_courses,
    list_calendar_events,
    TZ_SHANGHAI,
)

DEFAULT_OUTPUT = os.path.expanduser("~/Downloads/sjtu_timetable.ics")


def _ics_datetime(dt_str_or_obj):
    """将 ISO 时间字符串或 datetime 对象转为 ICS 格式的 UTC 时间 (YYYYMMDDTHHMMSSZ)"""
    if isinstance(dt_str_or_obj, str):
        dt = datetime.fromisoformat(dt_str_or_obj.replace("Z", "+00:00"))
    else:
        dt = dt_str_or_obj
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _escape_ics(text):
    """转义 ICS 特殊字符"""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_line(line):
    """ICS 规范：每行不超过75字节，超出部分折行（以空格开头续行）"""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    # 按字节切分，注意不要切断多字节字符
    result = []
    current = b""
    for char in line:
        char_bytes = char.encode("utf-8")
        limit = 75 if not result else 74  # 续行以空格开头，实际内容少1字节
        if len(current) + len(char_bytes) > limit:
            result.append(current.decode("utf-8"))
            current = char_bytes
        else:
            current += char_bytes
    if current:
        result.append(current.decode("utf-8"))
    return "\r\n ".join(result)


def _make_uid(prefix, identifier):
    """生成稳定的 UID"""
    h = hashlib.md5(f"{prefix}:{identifier}".encode()).hexdigest()[:12]
    return f"{prefix}-{h}@sjtu-canvas"


def _build_ics(events):
    """从事件列表构建完整 ICS 文件内容"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SJTU Canvas//DDL Export//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SJTU Canvas",
        "X-WR-TIMEZONE:Asia/Shanghai",
        # 时区定义
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev['uid']}")
        lines.append(f"DTSTAMP:{_ics_datetime(datetime.now(timezone.utc))}")

        if ev.get("dtstart"):
            lines.append(f"DTSTART:{_ics_datetime(ev['dtstart'])}")
        if ev.get("dtend"):
            lines.append(f"DTEND:{_ics_datetime(ev['dtend'])}")

        lines.append(f"SUMMARY:{_escape_ics(ev.get('summary', ''))}")

        if ev.get("description"):
            lines.append(f"DESCRIPTION:{_escape_ics(ev['description'])}")
        if ev.get("url"):
            lines.append(f"URL:{ev['url']}")
        if ev.get("location"):
            lines.append(f"LOCATION:{_escape_ics(ev['location'])}")
        if ev.get("categories"):
            lines.append(f"CATEGORIES:{_escape_ics(ev['categories'])}")

        # DDL 用红色提醒
        if ev.get("is_ddl"):
            lines.append("BEGIN:VALARM")
            lines.append("TRIGGER:-PT1H")
            lines.append("ACTION:DISPLAY")
            lines.append(f"DESCRIPTION:⏰ {_escape_ics(ev.get('summary', ''))} 即将截止!")
            lines.append("END:VALARM")
            # 再加一个24小时前的提醒
            lines.append("BEGIN:VALARM")
            lines.append("TRIGGER:-PT24H")
            lines.append("ACTION:DISPLAY")
            lines.append(f"DESCRIPTION:📋 {_escape_ics(ev.get('summary', ''))} 明天截止")
            lines.append("END:VALARM")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # 折行处理
    folded = [_fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def export_ddls_to_ics(output_path=None):
    """
    将 Canvas 所有作业 DDL 导出为 ICS 文件
    每个 DDL 作为一个 VEVENT，截止时间为事件时间

    Args:
        output_path: 输出文件路径，默认 ~/Downloads/sjtu_ddls.ics

    Returns:
        dict: {"path": str, "count": int, "events": list}
    """
    if not output_path:
        output_path = os.path.expanduser("~/Downloads/sjtu_ddls.ics")

    print("📡 正在获取 Canvas DDL 数据...")
    ddls = get_all_ddls_via_planner(include_past=False)
    now = datetime.now(TZ_SHANGHAI)

    events = []
    for d in ddls:
        due_dt = d["due_dt"]
        # 仅导出未来的DDL
        if due_dt < now:
            continue

        # DDL 作为一个30分钟的事件（截止时间前30分钟到截止时间）
        dtend = due_dt
        dtstart = due_dt - timedelta(minutes=30)

        status = ""
        if d["submitted"]:
            status = "✅ 已提交"
        elif d["missing"]:
            status = "❌ 缺交"
        else:
            status = "⏳ 待提交"

        description_parts = [
            f"课程: {d['course']}",
            f"状态: {status}",
            f"截止: {d['due_local']}",
        ]
        if d.get("points"):
            description_parts.append(f"分值: {d['points']}")
        if d.get("html_url"):
            description_parts.append(f"链接: {d['html_url']}")

        events.append({
            "uid": _make_uid("ddl", f"{d['course_id']}-{d['assignment_id']}"),
            "dtstart": dtstart,
            "dtend": dtend,
            "summary": f"📋 [DDL] {d['assignment']}",
            "description": "\n".join(description_parts),
            "url": d.get("html_url", ""),
            "categories": d["course"],
            "is_ddl": True,
        })

    if not events:
        print("ℹ️  没有未来的DDL需要导出")
        return {"path": output_path, "count": 0, "events": []}

    # 写入 ICS 文件
    ics_content = _build_ics(events)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"✅ 已导出 {len(events)} 个DDL到: {output_path}")
    return {"path": output_path, "count": len(events), "events": events}


def export_calendar_to_ics(output_path=None):
    """
    将 Canvas 课程日历事件导出为 ICS 文件

    Args:
        output_path: 输出文件路径，默认 ~/Downloads/sjtu_calendar.ics

    Returns:
        dict: {"path": str, "count": int, "events": list}
    """
    if not output_path:
        output_path = os.path.expanduser("~/Downloads/sjtu_calendar.ics")

    print("📡 正在获取课程列表...")
    courses = list_courses()
    if not courses:
        print("❌ 未获取到课程列表")
        return {"path": output_path, "count": 0, "events": []}

    course_ids = [c["id"] for c in courses]
    course_map = {c["id"]: c.get("name", f"Course {c['id']}") for c in courses}

    # 获取当前学期的日历事件（约一学期范围）
    now = datetime.now(TZ_SHANGHAI)
    start_date = "2026-02-17"  # 学期开始
    end_date = "2026-07-15"    # 学期结束 + buffer

    print(f"📡 正在获取日历事件 ({start_date} → {end_date})...")
    try:
        cal_events = list_calendar_events(course_ids, start_date, end_date)
    except Exception as e:
        print(f"⚠️ 获取日历事件失败: {e}")
        cal_events = []

    events = []
    for ev in cal_events:
        ev_id = ev.get("id", "")
        title = ev.get("title", "未命名事件")
        start = ev.get("start_at")
        end = ev.get("end_at")

        if not start:
            continue

        # 如果没有结束时间，默认1小时
        if not end:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end = (start_dt + timedelta(hours=1)).isoformat()

        # 获取课程名
        context_code = ev.get("context_code", "")
        course_name = ""
        if context_code.startswith("course_"):
            try:
                cid = int(context_code.split("_")[1])
                course_name = course_map.get(cid, "")
            except (ValueError, IndexError):
                pass

        description_parts = []
        if course_name:
            description_parts.append(f"课程: {course_name}")
        if ev.get("description"):
            # 简单去除 HTML 标签
            desc = ev["description"]
            import re
            desc = re.sub(r"<[^>]+>", "", desc).strip()
            if desc:
                description_parts.append(desc)
        if ev.get("html_url"):
            description_parts.append(f"链接: {ev['html_url']}")

        location = ev.get("location_name", "") or ""

        summary = title
        if course_name and course_name not in title:
            summary = f"[{course_name}] {title}"

        events.append({
            "uid": _make_uid("cal", str(ev_id)),
            "dtstart": start,
            "dtend": end,
            "summary": summary,
            "description": "\n".join(description_parts) if description_parts else "",
            "url": ev.get("html_url", ""),
            "location": location,
            "categories": course_name,
            "is_ddl": False,
        })

    if not events:
        print("ℹ️  没有日历事件需要导出")
        return {"path": output_path, "count": 0, "events": []}

    # 写入 ICS 文件
    ics_content = _build_ics(events)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"✅ 已导出 {len(events)} 个日历事件到: {output_path}")
    return {"path": output_path, "count": len(events), "events": events}


def export_all_to_ics(output_path=None):
    """
    将 DDL 和日历事件合并导出为一个 ICS 文件

    Args:
        output_path: 输出文件路径，默认 ~/Downloads/sjtu_timetable.ics
    """
    if not output_path:
        output_path = DEFAULT_OUTPUT

    print("📡 正在获取所有数据...")

    # 获取 DDL
    ddls = get_all_ddls_via_planner(include_past=False)
    now = datetime.now(TZ_SHANGHAI)
    all_events = []

    for d in ddls:
        due_dt = d["due_dt"]
        if due_dt < now:
            continue
        dtend = due_dt
        dtstart = due_dt - timedelta(minutes=30)
        status = "✅ 已提交" if d["submitted"] else "⏳ 待提交"
        all_events.append({
            "uid": _make_uid("ddl", f"{d['course_id']}-{d['assignment_id']}"),
            "dtstart": dtstart,
            "dtend": dtend,
            "summary": f"📋 [DDL] {d['assignment']}",
            "description": f"课程: {d['course']}\n状态: {status}\n截止: {d['due_local']}",
            "url": d.get("html_url", ""),
            "categories": d["course"],
            "is_ddl": True,
        })

    # 获取日历事件
    try:
        courses = list_courses()
        course_ids = [c["id"] for c in courses]
        course_map = {c["id"]: c.get("name", "") for c in courses}
        cal_events = list_calendar_events(course_ids, "2026-02-17", "2026-07-15")

        for ev in cal_events:
            start = ev.get("start_at")
            if not start:
                continue
            end = ev.get("end_at")
            if not end:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end = (start_dt + timedelta(hours=1)).isoformat()
            context_code = ev.get("context_code", "")
            course_name = ""
            if context_code.startswith("course_"):
                try:
                    cid = int(context_code.split("_")[1])
                    course_name = course_map.get(cid, "")
                except (ValueError, IndexError):
                    pass
            title = ev.get("title", "")
            summary = f"[{course_name}] {title}" if course_name and course_name not in title else title
            all_events.append({
                "uid": _make_uid("cal", str(ev.get("id", ""))),
                "dtstart": start,
                "dtend": end,
                "summary": summary,
                "location": ev.get("location_name", "") or "",
                "url": ev.get("html_url", ""),
                "categories": course_name,
                "is_ddl": False,
            })
    except Exception as e:
        print(f"⚠️ 获取日历事件失败（仅导出DDL）: {e}")

    if not all_events:
        print("ℹ️  没有事件需要导出")
        return

    ics_content = _build_ics(all_events)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    ddl_count = sum(1 for e in all_events if e.get("is_ddl"))
    cal_count = len(all_events) - ddl_count
    print(f"✅ 已导出到: {output_path}")
    print(f"   📋 DDL: {ddl_count} 个  |  📅 日历事件: {cal_count} 个")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_timetable_ics.py <命令> [输出路径]")
        print()
        print("命令:")
        print("  ddls      - 导出作业DDL为ICS")
        print("  calendar  - 导出课程日历事件为ICS")
        print("  all       - 合并导出所有事件")
        print()
        print(f"默认输出: {DEFAULT_OUTPUT}")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    output = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        if cmd == "ddls":
            result = export_ddls_to_ics(output)
            if result["count"] > 0:
                print(f"\n💡 提示: 双击 .ics 文件即可导入 Apple 日历")
        elif cmd == "calendar":
            result = export_calendar_to_ics(output)
            if result["count"] > 0:
                print(f"\n💡 提示: 双击 .ics 文件即可导入 Apple 日历")
        elif cmd == "all":
            export_all_to_ics(output)
            print(f"\n💡 提示: 双击 .ics 文件即可导入 Apple 日历")
        else:
            print(f"❌ 未知命令: {cmd}")
            print("可用命令: ddls / calendar / all")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
