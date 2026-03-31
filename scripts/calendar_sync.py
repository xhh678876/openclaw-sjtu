#!/usr/bin/env python3
"""DDL → Apple Calendar 同步工具"""

import subprocess
import sys
import json
from datetime import datetime, timezone, timedelta

TZ_SHANGHAI = timezone(timedelta(hours=8))
CALENDAR_NAME = "Canvas作业"

def ensure_calendar():
    """确保 Canvas作业 日历存在"""
    script = f'''
tell application "Calendar"
    set calNames to name of every calendar
    if calNames does not contain "{CALENDAR_NAME}" then
        make new calendar with properties {{name:"{CALENDAR_NAME}"}}
    end if
end tell
'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    return r.returncode == 0

def create_event(summary, due_dt, description=""):
    """在 Apple Calendar 创建事件"""
    script = f'''
tell application "Calendar"
    tell calendar "{CALENDAR_NAME}"
        set startDate to current date
        set year of startDate to {due_dt.year}
        set month of startDate to {due_dt.month}
        set day of startDate to {due_dt.day}
        set hours of startDate to {max(0, due_dt.hour - 1)}
        set minutes of startDate to 0
        set seconds of startDate to 0
        
        set endDate to current date
        set year of endDate to {due_dt.year}
        set month of endDate to {due_dt.month}
        set day of endDate to {due_dt.day}
        set hours of endDate to {due_dt.hour}
        set minutes of endDate to {due_dt.minute}
        set seconds of endDate to 0
        
        make new event with properties {{summary:"{summary}", start date:startDate, end date:endDate, description:"{description}"}}
    end tell
end tell
'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    return r.returncode == 0

def list_existing_events():
    """列出 Canvas作业 日历中的现有事件"""
    script = f'''
tell application "Calendar"
    tell calendar "{CALENDAR_NAME}"
        set eventList to {{}}
        repeat with e in events
            set end of eventList to summary of e
        end repeat
        return eventList
    end tell
end tell
'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        return [s.strip() for s in r.stdout.strip().split(",")]
    return []

def sync_ddls(ddls):
    """同步 DDL 列表到 Apple Calendar（跳过已存在的）"""
    # 启动日历
    subprocess.run(["open", "-a", "Calendar"], capture_output=True)
    import time; time.sleep(2)
    
    ensure_calendar()
    existing = list_existing_events()
    
    synced = 0
    skipped = 0
    for d in ddls:
        summary = f"📝 [{d['course']}] {d['assignment']}"
        if summary in existing:
            skipped += 1
            continue
        
        due_str = d["due_at"]
        due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00")).astimezone(TZ_SHANGHAI)
        desc = f"课程: {d['course']}\\n作业: {d['assignment']}\\nDDL: {d['due_local']}\\n满分: {d.get('points', '?')}"
        
        if create_event(summary, due_dt, desc):
            print(f"✅ {summary} → {d['due_local']}")
            synced += 1
        else:
            print(f"❌ {summary}")
    
    print(f"\n同步完成: {synced} 新增, {skipped} 已存在")
    return synced

if __name__ == "__main__":
    from canvas_api import get_all_upcoming_ddls
    ddls = get_all_upcoming_ddls()
    if not ddls:
        print("没有未来的DDL")
    else:
        print(f"找到 {len(ddls)} 个未来DDL:")
        sync_ddls(ddls)
