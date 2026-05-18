"""Unified DDL aggregator —— 一次性拉取所有平台的截止日期。

来源参考：kuan-er/sjtu-agent ddl_checker.py 的聚合范式。

用法：
  python -m scripts.unified_ddl                # 文本输出
  python -m scripts.unified_ddl --json         # JSON
  python -m scripts.unified_ddl --notify       # 文本 + macOS 通知（被 launchd 调用）
  python -m scripts.unified_ddl --remind-check # 仅检查最近 70 分钟内即将到期的，发系统通知
  python -m scripts.unified_ddl --skip phycai icourse163
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Iterable

from scripts.platforms import DDLItem
from scripts.platforms.base import CST


def _platforms(skip: Iterable[str] = ()):
    """惰性加载：避免一个平台 import 失败拖累全局。"""
    skip = set(skip)
    out = []
    if "phycai" not in skip:
        try:
            from scripts.platforms.phycai import PhyCaiPlatform
            out.append(("phycai", PhyCaiPlatform()))
        except ImportError as e:
            print(f"[skip] phycai: {e}")
    if "icourse163" not in skip:
        try:
            from scripts.platforms.icourse163 import ICourse163Platform
            out.append(("icourse163", ICourse163Platform()))
        except ImportError as e:
            print(f"[skip] icourse163: {e}")
    if "lcme" not in skip:
        try:
            from scripts.platforms.lcme import LCMEPlatform
            out.append(("lcme", LCMEPlatform()))
        except ImportError as e:
            print(f"[skip] lcme: {e}")
    if "canvas" not in skip:
        # 尝试桥接现有 canvas_api.py（如果有 list_ddls 接口）
        try:
            from scripts import canvas_api  # noqa: F401
            out.append(("canvas", _CanvasAdapter()))
        except Exception:
            pass
    return out


class _CanvasAdapter:
    """适配现有 scripts/canvas_api.py，让它符合 BasePlatform 形态。"""
    name = "canvas"

    def list_ddls(self) -> list[DDLItem]:
        try:
            from scripts.canvas_api import list_ddls as _list  # type: ignore
        except ImportError:
            return []
        try:
            raw = _list()
        except Exception as e:
            print(f"[canvas] 抓取失败：{e}")
            return []
        out = []
        for r in raw or []:
            try:
                due = r["due"] if isinstance(r["due"], datetime) \
                    else datetime.fromisoformat(r["due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=CST)
                out.append(DDLItem(
                    platform="canvas",
                    course=r.get("course") or "",
                    name=r.get("name") or "",
                    due=due,
                    submitted=bool(r.get("submitted")),
                ))
            except Exception:
                continue
        return out


def collect_all(skip: Iterable[str] = ()) -> list[DDLItem]:
    items: list[DDLItem] = []
    for name, p in _platforms(skip):
        try:
            items.extend(p.list_ddls())
        except Exception as e:
            print(f"[{name}] 抓取出错：{e}")
    items.sort(key=lambda x: x.due)
    return items


# ── 输出 ─────────────────────────────────────────────────────────────────────

def fmt_text(items: list[DDLItem]) -> str:
    if not items:
        return "（暂无未来截止任务）"
    now = datetime.now(CST)
    lines = []
    for it in items:
        delta = it.due - now
        if delta.total_seconds() < 0:
            label = "已过期"
        elif delta.total_seconds() < 24 * 3600:
            label = f"今天 +{int(delta.total_seconds() // 3600)}h"
        elif delta.days == 1:
            label = "明天"
        else:
            label = f"{delta.days}天后"
        flag = "✅" if it.submitted else "⏳"
        lines.append(
            f"{flag} [{it.platform:11s}] {it.course[:18]:<18} | "
            f"{it.name[:30]:<30} | {it.due.strftime('%m/%d %H:%M')} | {label}"
        )
    return "\n".join(lines)


def fmt_json(items: list[DDLItem]) -> str:
    return json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2)


def macos_notify(title: str, body: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{body}" with title "{title}"',
        ], check=False, capture_output=True)
    except Exception:
        pass


def remind_check(items: list[DDLItem], window_min: int = 70) -> int:
    """最近 window_min 分钟内的截止任务发系统通知。返回通知数。"""
    now = datetime.now(CST)
    upcoming = [
        it for it in items
        if not it.submitted and timedelta(0) < (it.due - now) <= timedelta(minutes=window_min)
    ]
    for it in upcoming:
        macos_notify(
            f"⏰ {it.platform}：{it.course}",
            f"{it.name} ({it.due.strftime('%H:%M')})",
        )
    return len(upcoming)


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="统一拉取所有 SJTU 平台的截止任务")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--notify", action="store_true",
                    help="启用 macOS 通知摘要（被 launchd daily-report 调用）")
    ap.add_argument("--remind-check", action="store_true",
                    help="仅检查 70 分钟内即将到期任务并通知（被 launchd remind-check 调用）")
    ap.add_argument("--skip", nargs="*", default=[],
                    choices=["canvas", "phycai", "icourse163", "lcme"],
                    help="跳过指定平台")
    args = ap.parse_args()

    items = collect_all(skip=args.skip)

    if args.remind_check:
        n = remind_check(items)
        print(f"[remind] 通知 {n} 条")
        return

    if args.json:
        print(fmt_json(items))
    else:
        print(fmt_text(items))

    if args.notify and items:
        macos_notify(
            f"📚 SJTU DDL：{len(items)} 条任务",
            f"最近：{items[0].course} - {items[0].name}",
        )


if __name__ == "__main__":
    main()
