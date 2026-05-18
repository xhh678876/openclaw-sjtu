"""macOS launchd 实现。

服务列表：
  daily-report   每天定时（默认 22:00）拉取所有平台 DDL → 写日志 / 推送
  remind-check   每分钟轮询，到期任务发系统通知（osascript）

来源参考：kuan-er/sjtu-agent/sjtu_agent/scheduler/launchd.py。
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path.home() / "openclaw-sjtu" / "data"
LOG_DIR = Path.home() / "openclaw-sjtu" / "logs"
DEFAULT_AGENT_DIR = Path.home() / "Library" / "LaunchAgents"

# 服务规格
SERVICE_SPECS = {
    "daily-report": {
        "label": "com.openclaw.sjtu.daily-report",
        "module": "scripts.unified_ddl",  # python -m scripts.unified_ddl --notify
        "args":   ["--notify"],
        "log":    "daily_report.launchd.log",
        "schedule_type": "calendar",
        "run_at_load": False,
    },
    "remind-check": {
        "label": "com.openclaw.sjtu.remind",
        "module": "scripts.unified_ddl",
        "args":   ["--remind-check"],
        "log":    "remind_check.launchd.log",
        "schedule_type": "interval",
        "run_at_load": True,
    },
}


def _build_plist(name: str, python_executable: Path,
                 daily_time: tuple[int, int],
                 remind_interval: int,
                 working_dir: Path) -> dict:
    spec = SERVICE_SPECS[name]
    log_path = LOG_DIR / spec["log"]
    payload: dict = {
        "Label": spec["label"],
        "ProgramArguments": [str(python_executable), "-m", spec["module"], *spec["args"]],
        "RunAtLoad": spec["run_at_load"],
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
        "WorkingDirectory": str(working_dir),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(working_dir),
        },
    }
    if spec["schedule_type"] == "calendar":
        h, m = daily_time
        payload["StartCalendarInterval"] = {"Hour": h, "Minute": m}
    elif spec["schedule_type"] == "interval":
        payload["StartInterval"] = remind_interval
    return payload


def install(service_names: tuple[str, ...] | None = None,
            python_executable: Path | None = None,
            daily_time: tuple[int, int] = (22, 0),
            remind_interval: int = 60,
            output_dir: Path | None = None,
            working_dir: Path | None = None,
            load: bool = True) -> dict:
    if load and sys.platform != "darwin":
        raise RuntimeError("launchd 仅支持 macOS")

    out_dir = Path(output_dir or DEFAULT_AGENT_DIR).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    work_dir = Path(working_dir or (Path.home() / "openclaw-sjtu")).resolve()

    py = Path(os.path.abspath(python_executable or sys.executable))
    selected = set(service_names or SERVICE_SPECS.keys())

    written: list[dict] = []
    for name in SERVICE_SPECS:
        if name not in selected:
            continue
        plist_path = out_dir / f"{SERVICE_SPECS[name]['label']}.plist"
        payload = _build_plist(name, py, daily_time, remind_interval, work_dir)
        with plist_path.open("wb") as f:
            plistlib.dump(payload, f, sort_keys=False)
        written.append({
            "name": name,
            "label": SERVICE_SPECS[name]["label"],
            "plist_path": str(plist_path),
            "log_path": str(LOG_DIR / SERVICE_SPECS[name]["log"]),
        })

    load_results: list[dict] = []
    if load:
        uid = os.getuid()
        for item in written:
            label = item["label"]
            plist = item["plist_path"]
            for domain in (f"gui/{uid}", f"user/{uid}"):
                subprocess.run(["launchctl", "bootout", f"{domain}/{label}"],
                               capture_output=True)
                r = subprocess.run(
                    ["launchctl", "bootstrap", domain, plist],
                    capture_output=True, text=True,
                )
                if r.returncode == 0:
                    load_results.append({"label": label, "domain": domain})
                    break

    return {
        "platform": "macOS (launchd)",
        "output_dir": str(out_dir),
        "working_dir": str(work_dir),
        "python_executable": str(py),
        "services": written,
        "load_results": load_results,
    }


def uninstall(service_names: tuple[str, ...] | None = None,
              output_dir: Path | None = None) -> dict:
    out_dir = Path(output_dir or DEFAULT_AGENT_DIR).expanduser().resolve()
    selected = set(service_names or SERVICE_SPECS.keys())
    uid = os.getuid()
    removed: list[dict] = []
    for name, spec in SERVICE_SPECS.items():
        if name not in selected:
            continue
        label = spec["label"]
        plist_path = out_dir / f"{label}.plist"
        for domain in (f"gui/{uid}", f"user/{uid}"):
            subprocess.run(["launchctl", "bootout", f"{domain}/{label}"],
                           capture_output=True)
        if plist_path.exists():
            plist_path.unlink()
            removed.append({"name": name, "label": label, "plist_path": str(plist_path)})
    return {"platform": "macOS (launchd)", "removed": removed}


def status(service_names: tuple[str, ...] | None = None,
           output_dir: Path | None = None) -> dict:
    out_dir = Path(output_dir or DEFAULT_AGENT_DIR).expanduser().resolve()
    selected = set(service_names or SERVICE_SPECS.keys())
    services: list[dict] = []
    for name, spec in SERVICE_SPECS.items():
        if name not in selected:
            continue
        plist_path = out_dir / f"{spec['label']}.plist"
        # 查询 launchctl 状态
        r = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{spec['label']}"],
            capture_output=True, text=True,
        )
        running = r.returncode == 0
        services.append({
            "name": name,
            "label": spec["label"],
            "plist_path": str(plist_path),
            "installed": plist_path.exists(),
            "running": running,
        })
    return {
        "platform": "macOS (launchd)",
        "services": services,
    }


def main():
    """CLI: python -m scripts.scheduler.launchd install|uninstall|status"""
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["install", "uninstall", "status"])
    ap.add_argument("--daily-hour", type=int, default=22)
    ap.add_argument("--daily-minute", type=int, default=0)
    ap.add_argument("--remind-interval", type=int, default=60)
    ap.add_argument("--no-load", action="store_true")
    args = ap.parse_args()

    if args.action == "install":
        out = install(daily_time=(args.daily_hour, args.daily_minute),
                      remind_interval=args.remind_interval,
                      load=not args.no_load)
    elif args.action == "uninstall":
        out = uninstall()
    else:
        out = status()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
