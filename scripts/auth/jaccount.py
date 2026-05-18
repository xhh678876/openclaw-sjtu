"""jAccount SSO 登录（Playwright + 三级验证码识别）。

来源参考：kuan-er/sjtu-agent/login.py。改造为面向对象 + 任意 entry_url。

用法：
  from scripts.auth import JAccountLogin, CookieStore
  login = JAccountLogin()
  with login.session() as ctx:
      ok = login.sso(ctx, entry_url="http://www.phycai.sjtu.edu.cn/pe/Jlogin.aspx",
                     success_url="**/phycai.sjtu.edu.cn/**")
      if ok:
          CookieStore().collect_from_playwright(ctx)

验证码识别优先级：
  1. 思源极客协会 ResNet API (geek.sjtu.edu.cn)
  2. Claude Haiku Vision API (需 ANTHROPIC_API_KEY)
  3. 手动打开图片输入
"""

from __future__ import annotations

import base64
import io
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import BrowserContext, Page, sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from .cookie_store import CookieStore

GEEK_CAPTCHA_API = "https://geek.sjtu.edu.cn/captcha-solver/"


# ── 验证码识别 ───────────────────────────────────────────────────────────────

def _png_to_jpeg(png_bytes: bytes) -> bytes:
    try:
        from PIL import Image  # type: ignore
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB").resize((110, 40))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except ImportError:
        return png_bytes


def solve_captcha_geek(img_bytes: bytes) -> str | None:
    try:
        jpeg = _png_to_jpeg(img_bytes)
        r = requests.post(
            GEEK_CAPTCHA_API,
            files={"image": ("captcha.jpg", jpeg, "image/jpeg")},
            timeout=10,
        )
        r.raise_for_status()
        result = r.json().get("result", "").strip()
        return result if result else None
    except Exception as e:
        print(f"  [CAPTCHA] 极客协会 API 失败：{e}")
        return None


def solve_captcha_claude(img_bytes: bytes) -> str | None:
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        client = anthropic.Anthropic()
        b64 = base64.standard_b64encode(img_bytes).decode()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{"role": "user", "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text",
                 "text": "这是一个登录验证码图片。请只输出图中的字符（通常是4个字母或数字），不要有任何其他文字。"},
            ]}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  [CAPTCHA] Claude 识别失败：{e}")
        return None


def solve_captcha(img_bytes: bytes) -> str:
    code = solve_captcha_geek(img_bytes)
    if code:
        print(f"  [CAPTCHA] 极客协会识别：{code}")
        return code
    code = solve_captcha_claude(img_bytes)
    if code:
        print(f"  [CAPTCHA] Claude 识别：{code}")
        return code
    # 手动兜底
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(img_bytes)
        tmp = f.name
    try:
        if platform.system() == "Darwin":
            subprocess.Popen(["open", tmp])
        elif platform.system() == "Windows":
            os.startfile(tmp)  # type: ignore
        else:
            subprocess.Popen(["xdg-open", tmp])
    except Exception:
        pass
    code = input(f"  [CAPTCHA] 自动识别失败，请手动输入（图片：{tmp}）：").strip()
    try:
        os.unlink(tmp)
    except Exception:
        pass
    return code


# ── jAccount 登录 ────────────────────────────────────────────────────────────

class JAccountLogin:
    """jAccount SSO 登录器。"""

    def __init__(self, store: CookieStore | None = None, headless: bool = True):
        self.store = store or CookieStore()
        self.headless = headless
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright 未安装。请：pip install playwright && playwright install chromium"
            )

    @contextmanager
    def session(self):
        """启动 Playwright，yield BrowserContext。退出时自动关闭。"""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(device_scale_factor=1)
            try:
                yield ctx
            finally:
                browser.close()

    def fill_form(self, page: "Page", username: str, password: str) -> bool:
        """在已跳转到 jAccount 登录页的 page 上填表单，最多 3 次验证码重试。

        成功（URL 离开 jaccount.sjtu.edu.cn）→ True
        """
        page.evaluate("if (typeof switchLoginType === 'function') switchLoginType('password')")
        page.wait_for_timeout(400)
        page.fill("#input-login-user", username)
        page.fill("#input-login-pass", password)

        for attempt in range(3):
            cap = page.locator("#captcha-img")
            if cap.count() and cap.is_visible():
                code = solve_captcha(cap.screenshot())
                page.fill("#input-login-captcha", code)
            page.click("#submit-password-button")
            try:
                page.wait_for_function(
                    "() => !location.href.includes('jaccount.sjtu.edu.cn') || "
                    "!!document.querySelector('.alert-danger, [class*=errorMsg]')",
                    timeout=12_000,
                )
            except Exception:
                pass
            if "jaccount.sjtu.edu.cn" not in page.url:
                return True
            print(f"  [jAccount] 第 {attempt + 1} 次验证码错误，刷新重试…")
            page.evaluate("if (typeof refreshCaptcha === 'function') refreshCaptcha()")
            page.wait_for_timeout(700)

        print("  [jAccount] 验证码 3 次失败，请检查账号密码")
        return False

    def sso(self, ctx: "BrowserContext", entry_url: str,
            success_url: str | None = None,
            username: str | None = None,
            password: str | None = None) -> bool:
        """通用 jAccount SSO 流程。

        entry_url     — 触发跳转到 jaccount 的入口 URL
        success_url   — 期望最终落地的 URL pattern (Playwright glob)
                        None = 只要离开 jaccount 即视为成功
        """
        if not username or not password:
            username, password = self.store.get_credentials()
        if not username or not password:
            print("[jAccount] 未配置凭据。请通过 CookieStore.set_credentials() 或 .env 提供。")
            return False

        page = ctx.new_page()
        try:
            page.goto(entry_url, wait_until="networkidle", timeout=25_000)
            if "jaccount.sjtu.edu.cn" not in page.url:
                # 已有有效 session
                if success_url:
                    try:
                        page.wait_for_url(success_url, timeout=8_000)
                    except Exception:
                        pass
                return True
            if not self.fill_form(page, username, password):
                return False
            if success_url:
                try:
                    page.wait_for_url(success_url, timeout=20_000)
                except Exception:
                    print(f"  [jAccount] 等待 {success_url} 超时，但 jaccount 已通过")
            page.wait_for_load_state("networkidle", timeout=10_000)
            return True
        except Exception as e:
            print(f"  [jAccount] SSO 失败：{e}")
            return False
        finally:
            page.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="刷新指定 SJTU 平台的 cookies")
    p.add_argument("--phycai", action="store_true", help="刷新 phycai cookies")
    p.add_argument("--i-sjtu", action="store_true", help="刷新 i.sjtu (教务) cookies")
    p.add_argument("--calendar", action="store_true", help="刷新 calendar (校历) cookies")
    p.add_argument("--all", action="store_true", help="刷新所有")
    p.add_argument("--save-creds", action="store_true",
                   help="把 .env 里的 JACCOUNT_USERNAME/PASSWORD 写入 config.json")
    args = p.parse_args()

    store = CookieStore()
    if args.save_creds:
        u = os.environ.get("JACCOUNT_USERNAME", "").strip()
        pw = os.environ.get("JACCOUNT_PASSWORD", "").strip()
        if not u or not pw:
            print("[错误] 请先设置 .env 中的 JACCOUNT_USERNAME / JACCOUNT_PASSWORD")
            sys.exit(1)
        store.set_credentials(u, pw)
        print(f"✓ 凭据已写入 {store.path}")
        return

    targets = []
    if args.all or args.phycai:
        targets.append(("phycai", "http://www.phycai.sjtu.edu.cn/pe/Jlogin.aspx",
                        "**/phycai.sjtu.edu.cn/**"))
    if args.all or args.i_sjtu:
        targets.append(("i.sjtu", "https://i.sjtu.edu.cn/xtgl/index_initMenu.html?jsdm=xs",
                        "**/i.sjtu.edu.cn/xtgl/**"))
    if args.all or args.calendar:
        targets.append(("calendar", "https://calendar.sjtu.edu.cn/",
                        "**/calendar.sjtu.edu.cn/**"))
    if not targets:
        p.print_help()
        return

    login = JAccountLogin(store=store, headless=True)
    with login.session() as ctx:
        for name, entry, success in targets:
            print(f"\n[*] 登录 {name}…")
            ok = login.sso(ctx, entry_url=entry, success_url=success)
            print(f"  {'✓' if ok else '✗'} {name}")
        print("\n[*] 收集 cookies…")
        updated = store.collect_from_playwright(ctx)
        for k in updated:
            print(f"  ✓ {k}")
        if not updated:
            print("  （未收集到任何 cookies）")


if __name__ == "__main__":
    main()
