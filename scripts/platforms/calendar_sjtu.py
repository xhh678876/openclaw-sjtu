"""calendar.sjtu.edu.cn — 学校校历 / 学期周次。

calendar.sjtu.edu.cn 全站需要 jAccount SSO。本模块提供：
  - login()             刷 cookie
  - get_current_term()  当前学期信息（含 week1_monday）
  - get_holidays()      法定假日列表

实现说明：站点是 SPA，没有公开 JSON RPC，因此采用 Playwright 抓 DOM。
本地缓存到 ~/openclaw-sjtu/data/sjtu_calendar.json 减少访问。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scripts.auth import CookieStore, JAccountLogin
from .base import BasePlatform, DDLItem, CST

CALENDAR_HOME = "https://calendar.sjtu.edu.cn/"
CACHE_PATH = Path.home() / "openclaw-sjtu" / "data" / "sjtu_calendar.json"


class CalendarPlatform(BasePlatform):
    name = "calendar"

    def __init__(self, store: CookieStore | None = None):
        self.store = store or CookieStore()

    # ── 登录 ────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        cookies = self.store.get_cookies("calendar_cookies")
        if cookies and self._cookies_alive(cookies):
            return True
        if not HAS_PLAYWRIGHT:
            return False

        login = JAccountLogin(store=self.store, headless=True)
        with login.session() as ctx:
            page = ctx.new_page()
            try:
                page.goto(CALENDAR_HOME, wait_until="domcontentloaded", timeout=25_000)
                if "jaccount.sjtu.edu.cn" in page.url:
                    u, p = self.store.get_credentials()
                    if not u or not p:
                        return False
                    if not login.fill_form(page, u, p):
                        return False
                    page.wait_for_url("**/calendar.sjtu.edu.cn/**", timeout=20_000)
                page.wait_for_load_state("networkidle", timeout=10_000)
            finally:
                page.close()
            self.store.collect_from_playwright(ctx, domains=["calendar.sjtu.edu.cn"])
        return bool(self.store.get_cookies("calendar_cookies"))

    def _cookies_alive(self, cookies: dict) -> bool:
        try:
            r = requests.get(CALENDAR_HOME, cookies=cookies,
                             allow_redirects=False, timeout=10)
            return r.status_code in (200, 302) and \
                "/login" not in (r.headers.get("Location") or "")
        except requests.RequestException:
            return False

    # ── 学期信息 ────────────────────────────────────────────────────────────
    def get_current_term(self, force: bool = False) -> dict | None:
        """返回 {term_name, week1_monday, total_weeks, current_week} 或 None。"""
        cached = self._read_cache()
        today = date.today()
        if not force and cached and cached.get("term_end"):
            end = date.fromisoformat(cached["term_end"])
            if today <= end:
                return self._with_current_week(cached, today)

        # 重新抓取
        if not self.login():
            return cached  # 用缓存兜底

        if not HAS_PLAYWRIGHT:
            return cached

        info = self._scrape_via_playwright()
        if info:
            self._write_cache(info)
            return self._with_current_week(info, today)
        return cached

    def _scrape_via_playwright(self) -> dict | None:
        cookies = self.store.get_cookies("calendar_cookies")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context()
                ctx.add_cookies([
                    {"name": k, "value": v, "domain": ".calendar.sjtu.edu.cn", "path": "/"}
                    for k, v in cookies.items()
                ])
                page = ctx.new_page()
                page.goto(CALENDAR_HOME, wait_until="networkidle", timeout=25_000)
                page.wait_for_timeout(2000)
                # 解析 DOM 中的学期块（页面格式可能变化，抓常见结构）
                html = page.content()
                browser.close()
                return self._parse_calendar_html(html)
        except Exception as e:
            print(f"[calendar] 抓取失败：{e}")
            return None

    @staticmethod
    def _parse_calendar_html(html: str) -> dict | None:
        """粗略解析校历 HTML：找学期名 + 起止日期。"""
        # 匹配模式：2025-2026学年 第二学期  2026-03-02 ~ 2026-07-XX
        m = re.search(
            r"(\d{4}[-－]\d{4})\s*学年.*?(第[一二]学期).*?"
            r"(\d{4}-\d{2}-\d{2})\s*[~～至到\-到]\s*(\d{4}-\d{2}-\d{2})",
            html, re.DOTALL,
        )
        if not m:
            # 兜底：找第一个 <td>YYYY-MM-DD</td>
            dates = re.findall(r"(\d{4}-\d{2}-\d{2})", html)
            if len(dates) < 2:
                return None
            start_str, end_str = dates[0], dates[-1]
            term_name = "Unknown"
        else:
            start_str = m.group(3)
            end_str = m.group(4)
            term_name = f"{m.group(1)} {m.group(2)}"

        start = date.fromisoformat(start_str)
        # week1 monday：取 start 当周或下一个周一
        delta = (7 - start.weekday()) % 7
        week1_monday = start if start.weekday() == 0 else start + timedelta(days=delta)
        end = date.fromisoformat(end_str)
        total_weeks = ((end - week1_monday).days // 7) + 1
        return {
            "term_name": term_name,
            "term_start": start.isoformat(),
            "term_end": end.isoformat(),
            "week1_monday": week1_monday.isoformat(),
            "total_weeks": total_weeks,
        }

    @staticmethod
    def _with_current_week(info: dict, today: date) -> dict:
        wk1 = date.fromisoformat(info["week1_monday"])
        delta_days = (today - wk1).days
        current_week = (delta_days // 7) + 1 if delta_days >= 0 else 0
        return {**info, "current_week": current_week, "today": today.isoformat()}

    # ── 缓存 ────────────────────────────────────────────────────────────────
    @staticmethod
    def _read_cache() -> dict | None:
        if not CACHE_PATH.exists():
            return None
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _write_cache(info: dict) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    # ── 假期 ────────────────────────────────────────────────────────────────
    def get_holidays(self) -> list[dict]:
        """官方法定假日（粗略实现：从 HTML 中匹配带"假"字的条目）。"""
        # 暂未实现细粒度解析，返回空。可后续按 calendar.sjtu.edu.cn 实际 DOM 完善
        return []

    def list_ddls(self) -> list[DDLItem]:
        return []


def main():
    p = CalendarPlatform()
    info = p.get_current_term()
    if not info:
        print("无法获取校历，请先 python -m scripts.auth.jaccount --calendar")
        return
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
