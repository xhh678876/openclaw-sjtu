"""phycai.sjtu.edu.cn — 物理实验排课。

来源参考：kuan-er/sjtu-agent ddl_checker.py 的 phycai 部分。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scripts.auth import CookieStore, JAccountLogin
from .base import BasePlatform, DDLItem, CST

PHYCAI_URL = "http://www.phycai.sjtu.edu.cn/pe/student/select.aspx"
PHYCAI_LOGIN = "http://www.phycai.sjtu.edu.cn/pe/Jlogin.aspx"


class PhyCaiPlatform(BasePlatform):
    name = "phycai"

    def __init__(self, store: CookieStore | None = None):
        self.store = store or CookieStore()

    # ── 登录 ────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        # 已有有效 cookies 直接 OK
        cookies = self.store.get_cookies("phycai_cookies")
        if cookies and self._cookies_alive(cookies):
            return True

        # 否则跑 jAccount SSO
        login = JAccountLogin(store=self.store, headless=True)
        with login.session() as ctx:
            ok = login.sso(ctx, entry_url=PHYCAI_LOGIN,
                           success_url="**/phycai.sjtu.edu.cn/**")
            if ok:
                page = ctx.new_page()
                try:
                    page.goto(PHYCAI_URL, wait_until="networkidle", timeout=20_000)
                finally:
                    page.close()
                self.store.collect_from_playwright(ctx, domains=["phycai.sjtu.edu.cn",
                                                                  "www.phycai.sjtu.edu.cn"])
                return True
        return False

    def _cookies_alive(self, cookies: dict) -> bool:
        try:
            r = requests.get(PHYCAI_URL, cookies=cookies, timeout=10, allow_redirects=False)
            return r.status_code == 200 and "Jlogin" not in (r.headers.get("Location") or "")
        except requests.RequestException:
            return False

    # ── 抓数据 ──────────────────────────────────────────────────────────────
    def fetch_html(self) -> str | None:
        cookies = self.store.get_cookies("phycai_cookies")
        if not cookies:
            return None
        try:
            r = requests.get(PHYCAI_URL, cookies=cookies, timeout=15)
            r.encoding = r.apparent_encoding
            r.raise_for_status()
            if "login" in r.url.lower() or "Jlogin" in r.url:
                return None
            return r.text
        except requests.RequestException:
            return None

    def list_ddls(self) -> list[DDLItem]:
        if not self.login():
            return []
        html = self.fetch_html()
        if html is None:
            return []
        return self._parse_table(html)

    # ── HTML 解析 ───────────────────────────────────────────────────────────
    @staticmethod
    def _cell(cells: list[str], col: dict[str, int], k: str) -> str:
        """从已分割的行 cells 里按列名 k 取值,越界/缺失返回空串。"""
        i = col.get(k)
        return cells[i] if i is not None and i < len(cells) else ""

    def _parse_table(self, html: str) -> list[DDLItem]:
        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        if not tables:
            return []
        table = max(tables, key=lambda t: len(t.find_all("tr")))
        rows = table.find_all("tr")
        if len(rows) < 2:
            return []

        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        col: dict[str, int] = {}
        mappings = {
            "name": ["实验项目", "实验名称", "项目名称", "项目"],
            "date": ["实验日期", "日期", "上课日期"],
            "time": ["实验时间", "时间", "上课时间"],
            "room": ["上课教室", "教室", "地点", "实验室"],
        }
        for key, words in mappings.items():
            for i, h in enumerate(headers):
                if any(w in h for w in words):
                    col[key] = i
                    break

        now = datetime.now(CST)
        out: list[DDLItem] = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if not cells:
                continue
            date_str = self._cell(cells, col, "date")
            time_str = self._cell(cells, col, "time")
            m = re.search(r"\d{1,2}:\d{2}", time_str)
            time_start = m.group() if m else ""
            dt = self._parse_dt(date_str, time_start)
            if dt and dt > now:
                out.append(DDLItem(
                    platform="phycai",
                    course="物理实验",
                    name=self._cell(cells, col, "name"),
                    due=dt,
                    location=self._cell(cells, col, "room"),
                    extra={"time_str": time_str},
                ))
        out.sort(key=lambda x: x.due)
        return out

    @staticmethod
    def _parse_dt(date_str: str, time_str: str) -> datetime | None:
        date_str = date_str.strip()
        time_str = time_str.strip()
        for df in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            for tf in ("%H:%M", "%H时%M分", "%H:%M:%S"):
                try:
                    dt = datetime.strptime(f"{date_str} {time_str}", f"{df} {tf}")
                    return dt.replace(tzinfo=CST)
                except ValueError:
                    continue
        return None


def main():
    """CLI: python -m scripts.platforms.phycai"""
    import json
    p = PhyCaiPlatform()
    items = p.list_ddls()
    if not items:
        print("（无未来实验或登录失败）")
        return
    print(json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
