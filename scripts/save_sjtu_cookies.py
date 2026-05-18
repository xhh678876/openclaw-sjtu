#!/usr/bin/env python3
"""SJTU 站点 cookie 抓取工具 — 一次性手动登录, 之后 gateway 用 cookie 调 API。

用法：
    ~/openclaw-sjtu/.venv/bin/python ~/openclaw-sjtu/scripts/save_sjtu_cookies.py [site]

site 可选 (默认全跑):
    course     — 选课社区 course.sjtu.plus
    legacy     — 传承交大 share.dyweb.sjtu.cn
    all        — 跑全部

流程：
    1. 自动开 Chromium 窗口
    2. 跳到目标站, 你点登录 → jAccount 输账号密码/扫码
    3. 登录完成后**回到终端按回车**, 脚本自动 dump cookies 到本地 json
    4. gateway 的 sjtu_course_review / sjtu_legacy 工具读 cookie 调 API

cookie 存放：
    ~/.openclaw/skills-data/sjtu-credentials/
        course-sjtu-plus.json
        share-dyweb-sjtu-cn.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CRED_DIR = Path.home() / ".openclaw" / "skills-data" / "sjtu-credentials"
CRED_DIR.mkdir(parents=True, exist_ok=True)

SITES = {
    "course": {
        "name": "选课社区 (course.sjtu.plus)",
        "url": "https://course.sjtu.plus/",
        "success_marker": "course.sjtu.plus",  # 域名留在 URL 上 = 没被踢到 jaccount
        "verify_path": "/api/me/",  # 200 才算真登录
        "cookie_file": CRED_DIR / "course-sjtu-plus.json",
    },
    "legacy": {
        "name": "传承·交大 (share.dyweb.sjtu.cn)",
        "url": "https://share.dyweb.sjtu.cn/",
        "success_marker": "share.dyweb.sjtu.cn",
        "verify_path": "/api/v1/user/profile",
        "cookie_file": CRED_DIR / "share-dyweb-sjtu-cn.json",
    },
}


def grab_one(playwright, site_key: str) -> bool:
    cfg = SITES[site_key]
    print(f"\n{'='*60}")
    print(f"🦞 抓取: {cfg['name']}")
    print(f"{'='*60}")

    browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    try:
        print(f"  正在打开: {cfg['url']}")
        page.goto(cfg["url"], wait_until="load", timeout=30000)

        print()
        print("  👉 接下来请你手动:")
        print("     1. 点页面上的登录按钮")
        print("     2. 在 jAccount 页面输账号密码 / 扫码")
        print("     3. 登录完成 → 回到这个终端按 [Enter]")
        print()
        input("  ↪ 登录完成后按 Enter 继续 (Ctrl+C 取消): ")

        # 验证登录是否真成功
        cur_url = page.url
        print(f"\n  当前页面: {cur_url}")
        if "jaccount" in cur_url:
            print("  ⚠ 还在 jAccount 页面, 登录可能没完成。放弃这站。")
            return False

        # 试一下 API 看看
        verify_url = cfg["url"].rstrip("/") + cfg["verify_path"]
        try:
            resp = page.request.get(verify_url, timeout=10000)
            print(f"  验证 {cfg['verify_path']}: HTTP {resp.status}")
            if resp.status not in (200, 201):
                print(f"  ⚠ 验证非 2xx, 但还是保存 cookie 让你后面试")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ 验证请求失败: {e}, 但还是保存 cookie")

        # Dump cookies
        cookies = ctx.cookies()
        payload: dict[str, Any] = {
            "site": cfg["url"],
            "saved_at_iso": _now_iso(),
            "verify_path": cfg["verify_path"],
            "cookies": cookies,
            "user_agent": page.evaluate("navigator.userAgent"),
        }
        cfg["cookie_file"].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
        cfg["cookie_file"].chmod(0o600)
        print(f"  ✅ 已保存 {len(cookies)} 个 cookie → {cfg['cookie_file']}")
        return True

    finally:
        try:
            ctx.close()
            browser.close()
        except Exception:  # noqa: BLE001
            pass


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target not in ("all", "course", "legacy"):
        print(f"未知 site: {target}. 可选: course / legacy / all", file=sys.stderr)
        sys.exit(2)

    sites = ["course", "legacy"] if target == "all" else [target]

    from playwright.sync_api import sync_playwright

    results: dict[str, bool] = {}
    with sync_playwright() as pw:
        for s in sites:
            try:
                results[s] = grab_one(pw, s)
            except KeyboardInterrupt:
                print(f"\n  ⏸ 取消 {s}, 跳到下一个")
                results[s] = False

    print(f"\n{'='*60}\n汇总:")
    for s, ok in results.items():
        emoji = "✅" if ok else "❌"
        print(f"  {emoji} {SITES[s]['name']}: {'已保存 cookie' if ok else '失败/跳过'}")
    print(f"\n  cookie 目录: {CRED_DIR}\n")
    if any(results.values()):
        print("接下来:")
        print("  1. 重启 gateway:  launchctl kickstart -k gui/$(id -u)/com.dahui.lobster-gateway")
        print("  2. 扫码 chat.clawsjtu.com 试问课评 / 课程资料\n")


if __name__ == "__main__":
    main()
