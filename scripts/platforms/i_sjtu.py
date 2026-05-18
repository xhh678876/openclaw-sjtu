"""i.sjtu.edu.cn — 新教务系统 / 课表 / 成绩。

实测可用接口（已验证）：
  POST /kbcx/xskbcx_cxXsgrkb.html?gnmkdm=N253508
       form: xnm=2025&xqm=12   → 2025-2026 秋
       form: xnm=2025&xqm=3    → 2025-2026 春（XQMMC=2 = 第二学期）
  返回：{xsxx, kbList[...], rqazcList, ...}

节次时间（系统返回 cxRjc 接口）：
  1: 08:00-08:54   2: 08:55-09:50   3: 09:51-10:54   4: 10:55-11:50
  5: 11:51-12:54   6: 12:55-13:50   7: 13:51-14:54   8: 14:55-15:50
  9: 15:51-16:54  10: 16:55-17:50  11: 17:51-18:54  12: 18:55-19:49
 13: 19:50-20:44  14: 20:45-21:30
"""

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Any

import requests

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scripts.auth import CookieStore, JAccountLogin
from .base import BasePlatform, DDLItem, CST

I_SJTU_HOME = "https://i.sjtu.edu.cn/xtgl/index_initMenu.html?jsdm=xs"
KB_API = "https://i.sjtu.edu.cn/kbcx/xskbcx_cxXsgrkb.html?gnmkdm=N253508"

PERIOD_TIMES: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:54"), 2: ("08:55", "09:50"),
    3: ("09:51", "10:54"), 4: ("10:55", "11:50"),
    5: ("11:51", "12:54"), 6: ("12:55", "13:50"),
    7: ("13:51", "14:54"), 8: ("14:55", "15:50"),
    9: ("15:51", "16:54"), 10: ("16:55", "17:50"),
    11: ("17:51", "18:54"), 12: ("18:55", "19:49"),
    13: ("19:50", "20:44"), 14: ("20:45", "21:30"),
}


class ISjtuPlatform(BasePlatform):
    name = "i_sjtu"

    def __init__(self, store: CookieStore | None = None):
        self.store = store or CookieStore()

    # ── 登录 ────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        cookies = self.store.get_cookies("i_sjtu_cookies")
        if cookies and self._cookies_alive(cookies):
            return True
        if not HAS_PLAYWRIGHT:
            print("[i_sjtu] Playwright 不可用")
            return False

        # i.sjtu 的 SSO 流程：访问 home → 跳到 jaccount → 登录后跳回
        login = JAccountLogin(store=self.store, headless=True)
        with login.session() as ctx:
            page = ctx.new_page()
            try:
                page.goto(I_SJTU_HOME, wait_until="domcontentloaded", timeout=25_000)
                if "jaccount.sjtu.edu.cn" in page.url:
                    u, p = self.store.get_credentials()
                    if not u or not p:
                        print("[i_sjtu] 缺少 jAccount 凭据")
                        return False
                    if not login.fill_form(page, u, p):
                        return False
                    page.wait_for_url("**/i.sjtu.edu.cn/xtgl/**", timeout=20_000)
                page.wait_for_load_state("networkidle", timeout=10_000)
            finally:
                page.close()
            self.store.collect_from_playwright(ctx, domains=["i.sjtu.edu.cn"])
        return bool(self.store.get_cookies("i_sjtu_cookies"))

    def _cookies_alive(self, cookies: dict) -> bool:
        try:
            r = requests.get(I_SJTU_HOME, cookies=cookies, allow_redirects=False, timeout=10)
            return r.status_code == 200 and "jaccount" not in (r.headers.get("Location") or "")
        except requests.RequestException:
            return False

    # ── 抓课表 ──────────────────────────────────────────────────────────────
    def fetch_schedule(self, xnm: str = "2025", xqm: str = "12",
                       skip_login: bool = False) -> dict | None:
        """xnm=学年(如 2025 表示 2025-2026)，xqm=12 表示春季 / 3 表示秋季。

        skip_login=True 时跳过自动 SSO，直接用现有 cookies（适合 oneshot 场景）。
        """
        cookies = self.store.get_cookies("i_sjtu_cookies")
        if not skip_login and not (cookies and self._cookies_alive(cookies)):
            if not self.login():
                return None
            cookies = self.store.get_cookies("i_sjtu_cookies")
        try:
            r = requests.post(
                KB_API,
                cookies=cookies,
                data={"xnm": xnm, "xqm": xqm, "kzlx": "ck"},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": I_SJTU_HOME,
                },
                timeout=20,
            )
            if r.status_code != 200:
                return None
            return r.json()
        except (requests.RequestException, ValueError):
            return None

    def list_courses(self, xnm: str = "2025", xqm: str = "12",
                     skip_login: bool = False) -> list[dict]:
        data = self.fetch_schedule(xnm, xqm, skip_login=skip_login)
        if not data or not data.get("kbList"):
            return []
        out = []
        seen = set()
        for k in data["kbList"]:
            key = (k.get("jxb_id"), k.get("xqj"), k.get("jcs"), k.get("zcd"))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "course": k.get("kcmc"),
                "teacher": k.get("xm"),
                "weekday": int(k.get("xqj") or 0),
                "periods": k.get("jcs"),
                "weeks": k.get("zcd"),
                "room": k.get("cdmc"),
                "class_name": k.get("jxbmc"),
                "credits": k.get("xf") or k.get("kcxszc"),
            })
        return out

    def expand_to_events(self, week1_monday: date,
                         xnm: str = "2025", xqm: str = "12") -> list[dict]:
        """展开课表为单次事件列表（包含 start / end datetime）。"""
        courses = self.list_courses(xnm=xnm, xqm=xqm)
        events = []
        for c in courses:
            weeks = self._parse_zcd(c["weeks"])
            s, e = self._parse_jcs(c["periods"])
            wd = c["weekday"]
            for w in weeks:
                day = week1_monday + timedelta(days=(w - 1) * 7 + (wd - 1))
                sh, sm = map(int, PERIOD_TIMES[s][0].split(":"))
                eh, em = map(int, PERIOD_TIMES[e][1].split(":"))
                events.append({
                    "title": f"{c['course']} @ {c['room']}",
                    "course": c["course"],
                    "teacher": c["teacher"],
                    "room": c["room"],
                    "start": datetime(day.year, day.month, day.day, sh, sm, tzinfo=CST),
                    "end": datetime(day.year, day.month, day.day, eh, em, tzinfo=CST),
                    "week": w,
                })
        events.sort(key=lambda e: e["start"])
        return events

    @staticmethod
    def _parse_zcd(zcd: str) -> list[int]:
        import re
        m = re.match(r"(\d+)-(\d+)周(?:\((单|双)\))?", zcd or "")
        if not m:
            single = re.match(r"(\d+)周", zcd or "")
            return [int(single.group(1))] if single else []
        a, b, parity = int(m.group(1)), int(m.group(2)), m.group(3)
        return [w for w in range(a, b + 1)
                if not parity
                or (parity == "单" and w % 2 == 1)
                or (parity == "双" and w % 2 == 0)]

    @staticmethod
    def _parse_jcs(jcs: str) -> tuple[int, int]:
        import re
        m = re.match(r"(\d+)-(\d+)", jcs or "")
        if m:
            return int(m.group(1)), int(m.group(2))
        return int(jcs), int(jcs)

    # ── ddl 接口（教务无 ddl，但实现以满足 BasePlatform） ──────────────────
    def list_ddls(self) -> list[DDLItem]:
        return []


def main():
    """CLI: python -m scripts.platforms.i_sjtu --xnm 2025 --xqm 12"""
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--xnm", default="2025")
    ap.add_argument("--xqm", default="12", help="12=春季, 3=秋季")
    ap.add_argument("--week1", help="第1周周一日期 YYYY-MM-DD（用于展开事件）")
    args = ap.parse_args()

    p = ISjtuPlatform()
    if args.week1:
        from datetime import date as _date
        y, mo, d = map(int, args.week1.split("-"))
        events = p.expand_to_events(_date(y, mo, d), xnm=args.xnm, xqm=args.xqm)
        print(json.dumps([{
            **{k: v for k, v in e.items() if k not in ("start", "end")},
            "start": e["start"].isoformat(),
            "end":   e["end"].isoformat(),
        } for e in events], ensure_ascii=False, indent=2))
    else:
        courses = p.list_courses(xnm=args.xnm, xqm=args.xqm)
        print(json.dumps(courses, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
