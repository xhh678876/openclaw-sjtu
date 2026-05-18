"""icourse163.org — 中国大学MOOC.

来源参考：kuan-er/sjtu-agent ddl_checker.py 的 icourse163 部分。

config.json 字段：
  icourse_cookies   ← 登录后自动写入
  icourse_courses   ← 课程列表，例如：
    [{"name":"大学物理","term_id":1476751568,"course_id":"SJTU-1449794172"}]

凭据通过 .env：
  MOOC_USERNAME=手机号
  MOOC_PASSWORD=密码
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scripts.auth import CookieStore
from .base import BasePlatform, DDLItem, CST


class ICourse163Platform(BasePlatform):
    name = "icourse163"

    def __init__(self, store: CookieStore | None = None):
        self.store = store or CookieStore()

    # ── 登录 ────────────────────────────────────────────────────────────────
    def login(self) -> bool:
        cookies = self.store.get_cookies("icourse_cookies")
        if cookies.get("NTESSTUDYSI"):
            return True
        new = self._login_with_creds()
        return new is not None

    def _login_with_creds(self) -> dict | None:
        if not HAS_PLAYWRIGHT:
            print("[icourse163] Playwright 不可用，跳过自动登录")
            return None
        username = os.environ.get("MOOC_USERNAME", "").strip()
        password = os.environ.get("MOOC_PASSWORD", "").strip()
        if not username or not password:
            print("[icourse163] 请在 .env 设置 MOOC_USERNAME / MOOC_PASSWORD")
            return None

        print("[icourse163] 用账号密码登录…")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    return self._do_login(browser, username, password)
                finally:
                    # 不论哪条 early-return 分支退出,浏览器始终关闭
                    browser.close()
        except Exception as e:
            print(f"[icourse163] 登录出错：{e}")
            return None

    def _do_login(self, browser, username: str, password: str) -> dict | None:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://www.icourse163.org/", wait_until="networkidle",
                  timeout=40_000)
        page.wait_for_timeout(2000)
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass
        page.get_by_text("登录", exact=False).first.click()
        page.wait_for_selector(
            "iframe[src*='reg.icourse163.org'][src*='index_dl2']",
            timeout=15_000,
        )
        page.wait_for_timeout(1000)

        login_frame = None
        for frame in page.frames:
            if "reg.icourse163.org" in frame.url and "index_dl2" in frame.url:
                if frame.locator("input[type='password']").count() > 0:
                    login_frame = frame
                    break
        if login_frame is None:
            print("[icourse163] 未找到登录 iframe")
            return None

        txt_inputs = login_frame.locator(
            "input[type='text'], input[type='tel']"
        ).all()
        txt_field = next((i for i in txt_inputs if i.is_visible()), None)
        if not txt_field:
            return None
        txt_field.fill(username)
        pwd_inputs = login_frame.locator("input[type='password']").all()
        pwd_field = next((i for i in pwd_inputs if i.is_visible()), None)
        if not pwd_field:
            return None
        pwd_field.fill(password)
        login_frame.get_by_text("登 录", exact=True).click()

        try:
            page.wait_for_function(
                "() => !document.querySelector('iframe[src*=\"reg.icourse163.org\"]')",
                timeout=20_000,
            )
        except Exception:
            pass
        page.wait_for_timeout(2000)

        new_cookies = {
            c["name"]: c["value"]
            for c in ctx.cookies()
            if "icourse163.org" in c.get("domain", "")
        }
        if not new_cookies.get("NTESSTUDYSI"):
            print("[icourse163] 登录失败")
            return None
        self.store.set_cookies("icourse_cookies", new_cookies)
        print("[icourse163] ✓ 登录成功，cookies 已保存")
        return new_cookies

    # ── 抓 ddl ──────────────────────────────────────────────────────────────
    def list_ddls(self) -> list[DDLItem]:
        if not self.login():
            return []
        cookies = self.store.get_cookies("icourse_cookies")
        cfg = self.store.load()
        courses = cfg.get("icourse_courses") or []
        if not courses:
            print("[icourse163] config.json 中 icourse_courses 为空，跳过")
            return []

        s = requests.Session()
        s.cookies.update(cookies)
        s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.icourse163.org/",
            "edu-script-token": cookies.get("NTESSTUDYSI", ""),
        })
        out: list[DDLItem] = []
        for c in courses:
            term_id = c.get("term_id")
            if not term_id:
                continue
            result = self._rpc(s, term_id)
            if result is None:
                continue
            out.extend(self._parse(result, c.get("name") or "MOOC"))
        out.sort(key=lambda x: x.due)
        return out

    @staticmethod
    def _rpc(session: requests.Session, term_id: int) -> dict | None:
        url = "https://www.icourse163.org/web/j/courseBean.getLastLearnedMocTermDto.rpc"
        try:
            r = session.post(
                url,
                data={"csrfKey": session.cookies.get("NTESSTUDYSI", ""),
                      "termId": str(term_id)},
                timeout=15,
            )
            if r.status_code == 200 and "json" in r.headers.get("Content-Type", ""):
                data = r.json()
                if data.get("result"):
                    return data["result"]
        except (requests.RequestException, json.JSONDecodeError):
            pass
        return None

    @staticmethod
    def _parse(result: dict[str, Any], cname: str) -> list[DDLItem]:
        out: list[DDLItem] = []
        moc = result.get("mocTermDto") or result
        now = datetime.now(CST)

        # 章节内 quizs
        for chapter in moc.get("chapters", []):
            for quiz in chapter.get("quizs") or []:
                test = quiz.get("test") or {}
                score = test.get("userScore") or test.get("testScore")
                if score is not None and float(score) > 0:
                    continue
                deadline_ms = test.get("deadline")
                if not deadline_ms:
                    continue
                due = datetime.fromtimestamp(int(deadline_ms) / 1000, tz=CST)
                if due < now:
                    continue
                out.append(DDLItem(
                    platform="icourse163",
                    course=cname,
                    name=quiz.get("name") or "未知测试",
                    due=due,
                    submitted=int(test.get("usedTryCount") or 0) > 0,
                ))

        # exams
        for exam in moc.get("exams") or []:
            score = exam.get("userScore") or exam.get("testScore")
            if score is not None and float(score) > 0:
                continue
            deadline_ms = exam.get("endTime") or exam.get("deadline")
            if not deadline_ms:
                continue
            due = datetime.fromtimestamp(int(deadline_ms) / 1000, tz=CST)
            if due < now:
                continue
            out.append(DDLItem(
                platform="icourse163",
                course=cname,
                name=exam.get("name") or exam.get("title") or "未知考试",
                due=due,
            ))
        return out


def main():
    p = ICourse163Platform()
    items = p.list_ddls()
    if not items:
        print("（无 MOOC ddl 或登录失败）")
        return
    print(json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
