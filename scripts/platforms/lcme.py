"""lcme.sjtu.edu.cn/openlab — 机动学院 实验室综合管理系统。

特点：**不是 jAccount SSO**，使用独立的 账号 + 密码（前端 RSA 加密后 POST）。
登录策略：用 Playwright 让浏览器 JS 自然执行 RSA 加密，避免在 Python 里复刻。

config.json 字段：
  lcme_username   学号（默认 = jaccount_username）
  lcme_password   lcme 系统密码（如果同 jAccount 可不填，自动 fallback）
  lcme_cookies    登录后自动写入

页面入口：
  https://lcme.sjtu.edu.cn/openlab/prepare_login    登录表单
  https://lcme.sjtu.edu.cn/openlab/login            POST 目标
  登录成功后通常跳到 /openlab/main.action 或 /openlab/index.action
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scripts.auth import CookieStore
from .base import BasePlatform, DDLItem, CST

LCME_LOGIN_PAGE = "https://lcme.sjtu.edu.cn/openlab/prepare_login"
LCME_BASE = "https://lcme.sjtu.edu.cn/openlab"


class LCMEPlatform(BasePlatform):
    name = "lcme"

    def __init__(self, store: CookieStore | None = None):
        self.store = store or CookieStore()

    # ── 凭据 ────────────────────────────────────────────────────────────────
    def _credentials(self) -> tuple[str | None, str | None]:
        cfg = self.store.load()
        u = cfg.get("lcme_username") or cfg.get("jaccount_username")
        # lcme 密码可能与 jAccount 不同；优先单独存
        p = cfg.get("lcme_password") or cfg.get("jaccount_password")
        return (u.strip() if u else None, p.strip() if p else None)

    def set_credentials(self, username: str, password: str) -> None:
        cfg = self.store.load()
        cfg["lcme_username"] = username
        cfg["lcme_password"] = password
        self.store.save(cfg)

    # ── 登录 ────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        cookies = self.store.get_cookies("lcme_cookies")
        if cookies and self._cookies_alive(cookies):
            return True
        if not HAS_PLAYWRIGHT:
            print("[lcme] Playwright 未安装")
            return False

        username, password = self._credentials()
        if not username or not password:
            print("[lcme] 缺少 lcme_username / lcme_password。"
                  "如果与 jAccount 相同，直接填 jaccount_password 即可")
            return False

        print(f"[lcme] 登录中（用户：{username}）…")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(device_scale_factor=1)
                page = ctx.new_page()
                page.goto(LCME_LOGIN_PAGE, wait_until="networkidle", timeout=25_000)

                # 表单字段在 jsp 里：account / password
                page.fill("input[name='account']", username)
                page.fill("input[name='password']", password)

                # 提交（onsubmit 里的 JS 会把密码 RSA 加密）
                page.evaluate("document.loginForm.submit()")
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass

                # 判断成功：URL 不再是 prepare_login，且页面没有明显错误
                ok = "prepare_login" not in page.url and "login" not in page.url.lower()
                if not ok:
                    # 兜底再看一眼是否有报错
                    body = page.content()
                    if "用户名或密码错误" in body or "登录失败" in body:
                        print("[lcme] ✗ 用户名或密码错误")
                    else:
                        print(f"[lcme] ✗ 登录后仍停留在 {page.url}")
                    browser.close()
                    return False

                cookies_list = ctx.cookies()
                browser.close()

                # 保存 lcme.sjtu.edu.cn 的所有 cookies
                lcme_cookies = {
                    c["name"]: c["value"]
                    for c in cookies_list
                    if "lcme.sjtu.edu.cn" in c.get("domain", "")
                }
                if not lcme_cookies:
                    print("[lcme] ✗ 未拿到 cookies")
                    return False
                self.store.set_cookies("lcme_cookies", lcme_cookies)
                print(f"[lcme] ✓ 登录成功，已保存 {len(lcme_cookies)} 个 cookies")
                return True
        except Exception as e:
            print(f"[lcme] 登录出错：{e}")
            return False

    def _cookies_alive(self, cookies: dict) -> bool:
        try:
            r = requests.get(f"{LCME_BASE}/main.action", cookies=cookies,
                             allow_redirects=False, timeout=10)
            # 200 = 已登录；302 → prepare_login = 过期
            if r.status_code == 200:
                return True
            loc = r.headers.get("Location", "")
            return "prepare_login" not in loc and "login" not in loc.lower()
        except requests.RequestException:
            return False

    # ── 数据抓取 ────────────────────────────────────────────────────────────
    def _session(self) -> requests.Session | None:
        cookies = self.store.get_cookies("lcme_cookies")
        if not cookies:
            return None
        s = requests.Session()
        s.cookies.update(cookies)
        s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": LCME_BASE + "/",
        })
        return s

    def fetch_main(self) -> str | None:
        """登录后的主页 HTML —— 包含菜单/快捷入口，便于发现可用功能。"""
        if not self.login():
            return None
        s = self._session()
        if not s:
            return None
        try:
            r = s.get(f"{LCME_BASE}/main.action", timeout=15)
            r.encoding = r.apparent_encoding
            return r.text if r.status_code == 200 else None
        except requests.RequestException:
            return None

    def list_reservations(self) -> list[dict]:
        """已预约的实验列表。

        注意：lcme/openlab 的具体 endpoint 因模块/角色不同而异。
        本实现尝试常见路径，未命中时返回空（请通过 `fetch_main()`
        查看主页 HTML 中的真实 URL，再按需扩展）。
        """
        if not self.login():
            return []
        s = self._session()
        if not s:
            return []

        # 常见候选路径（按经验排序）
        candidates = [
            f"{LCME_BASE}/student/myReservation_list.action",
            f"{LCME_BASE}/student/booking_list.action",
            f"{LCME_BASE}/exp/exp_listMyExp.action",
            f"{LCME_BASE}/student/student_indexInfo.action",
        ]
        for url in candidates:
            try:
                r = s.get(url, timeout=15, allow_redirects=False)
                if r.status_code == 200 and "<table" in r.text and "prepare_login" not in r.text:
                    items = self._parse_reservation_table(r.text)
                    if items:
                        return items
            except requests.RequestException:
                continue
        return []

    @staticmethod
    def _cell(cells: list[str], col: dict[str, int], k: str) -> str:
        """从已分割的行 cells 里按列名 k 取值,越界/缺失返回空串。"""
        i = col.get(k)
        return cells[i] if i is not None and i < len(cells) else ""

    @classmethod
    def _parse_reservation_table(cls, html: str) -> list[dict]:
        """通用表格解析：找最大表格，按表头映射常见列。"""
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
            "name":  ["实验项目", "实验名称", "项目名称", "项目"],
            "date":  ["实验日期", "日期", "上课日期", "预约日期"],
            "time":  ["实验时间", "时间", "上课时间", "预约时间"],
            "room":  ["上课教室", "实验室", "教室", "地点"],
            "course": ["课程", "课程名称"],
            "status": ["状态", "审核"],
        }
        for key, words in mappings.items():
            for i, h in enumerate(headers):
                if any(w in h for w in words):
                    col[key] = i
                    break

        out: list[dict] = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if not cells:
                continue
            out.append({
                "name":   cls._cell(cells, col, "name"),
                "date":   cls._cell(cells, col, "date"),
                "time":   cls._cell(cells, col, "time"),
                "room":   cls._cell(cells, col, "room"),
                "course": cls._cell(cells, col, "course"),
                "status": cls._cell(cells, col, "status"),
            })
        return out

    def list_ddls(self) -> list[DDLItem]:
        """把已预约且未到来的实验视为 DDL。"""
        items = self.list_reservations()
        out: list[DDLItem] = []
        now = datetime.now(CST)
        for it in items:
            dt = self._parse_dt(it["date"], it["time"])
            if dt and dt > now:
                out.append(DDLItem(
                    platform="lcme",
                    course=it.get("course") or "实验",
                    name=it["name"],
                    due=dt,
                    location=it.get("room"),
                    extra={"status": it.get("status")},
                ))
        out.sort(key=lambda x: x.due)
        return out

    @staticmethod
    def _parse_dt(date_str: str, time_str: str) -> datetime | None:
        m = re.search(r"\d{1,2}:\d{2}", time_str or "")
        time_start = m.group() if m else "08:00"
        for df in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
            for tf in ("%H:%M", "%H:%M:%S"):
                try:
                    dt = datetime.strptime(f"{date_str} {time_start}", f"{df} {tf}")
                    return dt.replace(tzinfo=CST)
                except ValueError:
                    continue
        return None


def main():
    """CLI: python -m scripts.platforms.lcme [--reservations|--main]"""
    import argparse
    import getpass
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--reservations", action="store_true", help="列出已预约实验")
    ap.add_argument("--main", action="store_true", help="dump 主页 HTML（调试用）")
    ap.add_argument("--user", help="设置 lcme 用户名")
    ap.add_argument(
        "--password",
        help="设置 lcme 密码 (⚠ argv 对 ps aux 可见;留空将以 getpass 交互式提示)",
    )
    args = ap.parse_args()

    p = LCMEPlatform()
    if args.user:
        if args.password:
            print("[warn] --password 把密码暴露到 ps aux;建议留空,交互式输入",
                  file=sys.stderr)
            pwd = args.password
        elif sys.stdin.isatty():
            pwd = getpass.getpass(f"lcme password for {args.user}: ")
        else:
            print("[错误] 非 tty 环境必须显式 --password,或直接编辑 config.json",
                  file=sys.stderr)
            sys.exit(1)
        p.set_credentials(args.user, pwd)
        print(f"✓ 凭据已写入 {p.store.path}")

    if args.main:
        html = p.fetch_main()
        if html:
            print(html[:5000])
        else:
            print("（无法获取主页）")
        return

    items = p.list_reservations() if args.reservations else \
            [i.to_dict() for i in p.list_ddls()]
    print(json.dumps(items, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
