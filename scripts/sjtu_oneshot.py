"""一键登录 + 抓全部信息。

用法（最简）：
  python -m scripts.sjtu_oneshot --user <jaccount> --pass <password>

或先把凭据写入 config.json：
  python -m scripts.sjtu_oneshot --save-creds --user <jaccount> --pass <password>
然后裸跑：
  python -m scripts.sjtu_oneshot

做的事（按顺序，单 Playwright 会话）：
  1. jAccount 登录一次（密码 + 验证码三级识别）
  2. 复用 SSO session 依次访问 i.sjtu / calendar / phycai，全部 cookies 落盘
  3. 关闭浏览器，用纯 requests 调各家 API：
       - i.sjtu      → 课表（当前学期）
       - calendar    → 当前 Week / 学期总周数
       - phycai      → 未来物理实验
       - icourse163  → MOOC 待完成测试（需要 MOOC_USERNAME/PASSWORD）
       - lcme        → 机动学院 openlab 实验预约（独立账号，可用 jaccount 同密码）
       - canvas      → 现有 token 拉作业（如已配置）
  4. 打印统一报告
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from scripts.auth import CookieStore, JAccountLogin
from scripts.auth.jaccount import solve_captcha
from scripts.platforms.base import CST


# ── 单浏览器会话登录全部站点 ────────────────────────────────────────────────

PLATFORM_ENTRIES = [
    # (cookie_key, entry_url, login_failure_substring)
    # i.sjtu 必须先跳 /jaccountlogin（不是 index_initMenu，那是登录后入口）
    ("i_sjtu",   "https://i.sjtu.edu.cn/jaccountlogin",
                 "login_slogin"),
    ("calendar", "https://calendar.sjtu.edu.cn/",
                 "/login"),
    ("phycai",   "http://www.phycai.sjtu.edu.cn/pe/Jlogin.aspx",
                 "Jlogin"),
]


_CAPTCHA_DUMP_DIR = Path.home() / "openclaw-sjtu" / "data" / "captcha_failures"

# jAccount 错误文本指纹 —— 用来区分"验证码错"(可重试)vs"密码错"(白搭再试)
_CAPTCHA_ERR_SIGS = ("验证码", "captcha", "校验码")
_CRED_ERR_SIGS = ("密码错", "账号或密码", "用户名或密码", "incorrect password",
                   "wrong password", "invalid credentials", "用户不存在")


def _extract_error_text(page) -> str:
    """从 jAccount 错误提示中拿到最具诊断价值的文本片段。"""
    try:
        return page.evaluate("""() => {
            const alerts = [...document.querySelectorAll(
                '.alert-danger, [class*=errorMsg], .error-msg, .login-error')];
            const text = alerts.map(a => a.innerText || '').join(' | ').trim();
            return text || (document.body.innerText || '').slice(0, 400);
        }""") or ""
    except Exception:
        return ""


def _classify_login_error(err_text: str) -> str:
    """captcha / cred / unknown"""
    low = err_text.lower()
    if any(s in err_text for s in _CAPTCHA_ERR_SIGS) or "captcha" in low:
        return "captcha"
    if any(s in err_text for s in _CRED_ERR_SIGS):
        return "cred"
    return "unknown"


def _dump_captcha_for_debug(img: bytes, tag: str) -> Path | None:
    try:
        _CAPTCHA_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        p = _CAPTCHA_DUMP_DIR / f"{tag}-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
        p.write_bytes(img)
        p.chmod(0o600)
        return p
    except Exception:
        return None


def _fill_jaccount_form(page, username: str, password: str,
                         twofa_wait_sec: int = 180,
                         max_attempts: int = 5) -> bool:
    """已跳到 jaccount 登录页时填表，自动处理验证码 + 2FA。

    - 验证码：极客协会 ResNet → Claude → 手动
    - 2FA：检测到二步验证页面后，自动勾选"信任设备"复选框，
            然后等待用户扫码或在终端粘贴 SMS/邮件验证码
    - 错误分类:验证码错误→重试到 max_attempts;密码错→立刻放弃
    """
    page.evaluate("if (typeof switchLoginType === 'function') switchLoginType('password')")
    page.wait_for_timeout(400)
    page.fill("#input-login-user", username)
    page.fill("#input-login-pass", password)

    for attempt in range(max_attempts):
        # 验证码 —— 失败时把图存下来便于人工核对 OCR
        captcha_img: bytes | None = None
        try:
            cap = page.locator("#captcha-img")
            if cap.count() and cap.is_visible():
                captcha_img = cap.screenshot()
                code = solve_captcha(captcha_img)
                page.fill("#input-login-captcha", code)
        except Exception:
            pass

        try:
            page.click("#submit-password-button", timeout=8_000)
        except Exception:
            # 表单换页了
            pass

        # 等 1) 离开 jaccount 或 2) 出现 2FA 页面 或 3) 出现错误
        try:
            page.wait_for_function(
                "() => !location.href.includes('jaccount.sjtu.edu.cn') || "
                "document.body.innerText.includes('Two-Step Verification') || "
                "document.body.innerText.includes('两步验证') || "
                "document.body.innerText.includes('二步验证') || "
                "!!document.querySelector('.alert-danger, [class*=errorMsg]')",
                timeout=12_000,
            )
        except Exception:
            pass

        # 已离开 jaccount = 成功
        if "jaccount.sjtu.edu.cn" not in page.url:
            return True

        body = page.evaluate("() => document.body.innerText")
        # 2FA 处理
        if "Two-Step Verification" in body or "两步验证" in body or "二步验证" in body:
            print("\n  [2FA] 检测到二步验证。请：")
            print("    1) 在弹出的浏览器里扫码（My SJTU App / 微信）")
            print("       或点 Mail/Sms 接收验证码并填入")
            print(f"    2) 完成后等待自动检测（最多 {twofa_wait_sec} 秒）")
            print("    （提示：本次「信任设备」会自动勾选，下次免 2FA）\n")

            # 自动勾选"信任设备"
            try:
                page.evaluate("""() => {
                    const cbs = [...document.querySelectorAll('input[type=checkbox]')];
                    for (const cb of cbs) {
                        const lbl = (cb.parentElement?.innerText || '').toLowerCase();
                        if (lbl.includes('trust') || lbl.includes('信任')) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                }""")
            except Exception:
                pass

            try:
                page.wait_for_function(
                    "() => !location.href.includes('jaccount.sjtu.edu.cn')",
                    timeout=twofa_wait_sec * 1000,
                )
                print("  [2FA] ✓ 验证完成")
                return True
            except Exception:
                print("  [2FA] ✗ 等待超时")
                return False

        # 普通错误:分类后决定是否重试
        err_text = _extract_error_text(page)
        category = _classify_login_error(err_text)
        snippet = err_text[:120].replace("\n", " ")
        print(f"  [jAccount] 第 {attempt+1}/{max_attempts} 次失败 [{category}]: {snippet}")

        if category == "cred":
            print("  [jAccount] ✗ 凭据错误,放弃重试(避免触发账号锁定)")
            return False

        # captcha or unknown → 把当前验证码图存档,便于人工对一下 OCR
        if captcha_img:
            dumped = _dump_captcha_for_debug(captcha_img, f"attempt{attempt+1}")
            if dumped:
                print(f"  [debug] 验证码截图: {dumped}")

        try:
            page.evaluate("if (typeof refreshCaptcha === 'function') refreshCaptcha()")
        except Exception:
            pass
        page.wait_for_timeout(700)
    return False


def login_all(username: str, password: str, headless: bool = True,
              store: CookieStore | None = None,
              profile_dir: Path | None = None,
              seed_cookies: dict[str, dict[str, str]] | None = None) -> dict:
    """单 Playwright 会话登录全部平台。返回每个平台的 cookie 收集结果。

    Args:
        seed_cookies: {domain: {name: value}} 启动前注入的 cookies
                      （比如从 Chrome 偷的 JATrustCookie，可让 Playwright 直接跳过 2FA）
        profile_dir : 持久化浏览器配置（含 jAccount 信任设备 cookie），跨运行共享
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright 未安装")
    store = store or CookieStore()
    profile = Path(profile_dir or (Path.home() / "openclaw-sjtu" / "data" /
                                    "playwright_profile"))
    profile.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}
    # 用真实 Chrome 的 User-Agent，让 JATrustCookie 的设备指纹判定通过
    chrome_ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/130.0.0.0 Safari/537.36")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            device_scale_factor=1,
            user_agent=chrome_ua,
            viewport={"width": 1440, "height": 900},
        )
        # 注:launch_persistent_context 返回的 ctx.browser 是 None,所以下面
        # 关闭浏览器只能用 ctx.close() 不能 browser.close()

        # 注入种子 cookies（来自系统 Chrome）—— 关键：JATrustCookie 让 jAccount
        # 直接信任本会话，跳过 2FA 扫码。
        # 注意：不要注入 analytics-only / pollution cookies（_pk_id, _pk_ref 等
        # Matomo 跟踪 cookies），那些会污染 session。只白名单 jAccount 的真正
        # 信任 cookies + 平台真正的 session cookies。
        SEED_WHITELIST = {
            "JATrustCookie", "JAAuthCookie",  # jAccount 真正的 trust cookie
            "JSESSIONID", "ASP.NET_SessionId", "keepalive",
            "NTESSTUDYSI",
            ".PhyEwsProj", "PhyEws_StuName", "PhyEws_StuType", ".ASPXAUTH",
        }
        if seed_cookies:
            inject = []
            for domain, name_to_val in seed_cookies.items():
                for name, value in name_to_val.items():
                    if name not in SEED_WHITELIST:
                        continue
                    inject.append({
                        "name":   name,
                        "value":  value,
                        "domain": domain if domain.startswith(".") else "." + domain,
                        "path":   "/",
                    })
            if inject:
                try:
                    ctx.add_cookies(inject)
                    names = sorted({c["name"] for c in inject})
                    print(f"  [seed] 注入了 {len(inject)} 个 cookies：{names}")
                except Exception as e:
                    print(f"  [seed] cookie 注入失败：{e}")

        for key, entry, fail_substr in PLATFORM_ENTRIES:
            print(f"[*] 登录 {key} …")
            page = ctx.new_page()
            try:
                page.goto(entry, wait_until="networkidle", timeout=30_000)
                # 等所有重定向链 + 客户端 JS 跳转完成
                page.wait_for_timeout(2500)

                # 如果还停在 jaccount 登录页，则填表（首次登录走这里）
                if "jaccount.sjtu.edu.cn" in page.url:
                    # 进一步确认是登录页（有 user 输入框），而不是过渡中的 redirect
                    has_form = page.locator("#input-login-user").count() > 0
                    if has_form:
                        ok = _fill_jaccount_form(page, username, password)
                        if not ok:
                            print(f"  ✗ {key}: jAccount 验证失败")
                            results[key] = "FAILED"
                            page.close()
                            continue
                    else:
                        # 在 jaccount 但没表单 = 正在重定向，再等一下
                        page.wait_for_timeout(3000)

                # 等离开 jaccount + 落到目标站点
                try:
                    page.wait_for_function(
                        "() => !location.href.includes('jaccount.sjtu.edu.cn')",
                        timeout=20_000,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                final = page.url
                if "jaccount.sjtu.edu.cn" in final:
                    print(f"  ✗ {key}: 仍在 jaccount，登录失败（账号或密码可能错误）")
                    results[key] = "STUCK"
                elif fail_substr and fail_substr in final:
                    print(f"  ✗ {key}: 落到 {final[:80]}（未真正登录）")
                    results[key] = "NOT_LOGGED_IN"
                else:
                    results[key] = "OK"
                    print(f"  ✓ {key}: {final[:80]}")
            except Exception as e:
                print(f"  ✗ {key}: {e}")
                results[key] = f"ERR: {e}"
            finally:
                page.close()

        # 一次性收集所有 cookies
        updated = store.collect_from_playwright(ctx)
        ctx.close()

    return {"results": results, "saved": updated}


# ── 抓数据 ───────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def report_calendar(store: CookieStore) -> dict | None:
    from scripts.platforms.calendar_sjtu import CalendarPlatform
    p = CalendarPlatform(store=store)
    info = p.get_current_term()
    _section("📅 校历")
    if not info:
        print("  无法获取校历（可能是 calendar 站点 DOM 结构变化，或登录失败）")
        return None
    print(f"  学期: {info.get('term_name', '?')}")
    print(f"  Week 1 周一: {info.get('week1_monday', '?')}")
    print(f"  当前周: 第 {info.get('current_week', '?')} 周 / 共 {info.get('total_weeks', '?')} 周")
    return info


def report_schedule(store: CookieStore, week1: str | None) -> list[dict]:
    from scripts.platforms.i_sjtu import ISjtuPlatform
    p = ISjtuPlatform(store=store)
    courses = p.list_courses(xnm="2025", xqm="12", skip_login=True)
    _section(f"📚 课表（2025-2026 春季，共 {len(courses)} 门课）")
    if not courses:
        print("  无数据")
        return []
    for c in courses:
        wd = "一二三四五六日"[c["weekday"] - 1] if c["weekday"] else "?"
        print(f"  周{wd} {c['periods']:>5}节 | {c['course']:<14} | "
              f"{c['room']:<12} | {c['teacher']:<8} | {c['weeks']}")
    if week1:
        # 展开未来 1 周课表
        try:
            y, mo, d = map(int, week1.split("-"))
            events = p.expand_to_events(date(y, mo, d), xnm="2025", xqm="12")
            now = datetime.now(CST)
            upcoming = [e for e in events if now <= e["start"] <= now + timedelta(days=7)]
            if upcoming:
                _section(f"⏳ 未来 7 天课程（共 {len(upcoming)} 节）")
                for e in upcoming:
                    print(f"  {e['start'].strftime('%m/%d %H:%M')}-"
                          f"{e['end'].strftime('%H:%M')} | "
                          f"{e['course']:<14} | {e['room']}")
        except Exception:
            pass
    return courses


def report_phycai(store: CookieStore) -> list:
    from scripts.platforms.phycai import PhyCaiPlatform
    p = PhyCaiPlatform(store=store)
    items = p.list_ddls()
    _section(f"🔬 物理实验（{len(items)} 个未来安排）")
    if not items:
        print("  无未来实验或无 phycai 课")
        return []
    for it in items:
        print(f"  {it.due.strftime('%m/%d %H:%M')} | {it.name:<24} | {it.location}")
    return items


def report_icourse163(store: CookieStore) -> list:
    from scripts.platforms.icourse163 import ICourse163Platform
    p = ICourse163Platform(store=store)
    items = p.list_ddls()
    _section(f"🎓 中国大学MOOC（{len(items)} 个未完成 DDL）")
    if not items:
        print("  无 MOOC ddl（或未配置 MOOC_USERNAME/PASSWORD/icourse_courses）")
        return []
    for it in items:
        flag = "✅" if it.submitted else "⏳"
        print(f"  {flag} {it.due.strftime('%m/%d %H:%M')} | {it.course} | {it.name}")
    return items


def report_lcme(store: CookieStore) -> list:
    from scripts.platforms.lcme import LCMEPlatform
    p = LCMEPlatform(store=store)
    if not p.login():
        _section("🧪 LCME 实验室综合管理（机动学院）")
        print("  登录失败 —— 请检查 lcme_password 是否与 jAccount 一致；"
              "若否，跑 `python -m scripts.platforms.lcme --user X --password Y`")
        return []
    items = p.list_ddls()
    _section(f"🧪 LCME 实验预约（{len(items)} 个未来安排）")
    if not items:
        print("  无未来实验 / 解析未命中端点（可用 --main 查看主页 HTML 找真实路径）")
        return []
    for it in items:
        print(f"  {it.due.strftime('%m/%d %H:%M')} | {it.course:<14} | "
              f"{it.name:<24} | {it.location}")
    return items


def report_canvas() -> list:
    """复用现有 canvas_api.py（如已配置）。"""
    try:
        from scripts.canvas_api import list_ddls  # type: ignore
    except Exception:
        _section("📋 Canvas")
        print("  scripts/canvas_api.py 不可用或无 list_ddls，跳过")
        return []
    try:
        items = list_ddls() or []
    except Exception as e:
        _section("📋 Canvas")
        print(f"  Canvas 抓取失败: {e}")
        return []
    _section(f"📋 Canvas（{len(items)} 项）")
    for it in items[:20]:
        due = it.get("due") or "?"
        print(f"  {due} | {it.get('course', '')} | {it.get('name', '')}")
    if len(items) > 20:
        print(f"  ...（还有 {len(items) - 20} 项）")
    return items


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="一键登录所有 SJTU 平台并拉取信息（课表/校历/物理实验/MOOC/Canvas）",
    )
    ap.add_argument("--user", "--username", dest="user", help="jAccount 用户名")
    ap.add_argument(
        "--pass", "--password", dest="pwd",
        help="jAccount 密码 (⚠ argv 对 ps aux 可见;留空将以 getpass 交互式提示)",
    )
    ap.add_argument("--save-creds", action="store_true",
                    help="把 --user/--pass 写入 config.json (0600) 后续无需再传")
    ap.add_argument("--show", action="store_true",
                    help="显示浏览器窗口（默认无头 —— 因为已注入 JATrustCookie）")
    ap.add_argument("--week1", help="第1周周一 YYYY-MM-DD（用于展开未来7天课表）。"
                                     "不填会从校历自动取")
    ap.add_argument("--skip-login", action="store_true",
                    help="跳过登录，直接用现有 cookies 拉取")
    ap.add_argument("--no-chrome-import", action="store_true",
                    help="禁用从系统 Chrome 偷 cookies 的快速路径")
    ap.add_argument("--force-login", action="store_true",
                    help="即使从 Chrome 拿到了 cookies，也强制走一次 Playwright 登录")
    ap.add_argument("--json", action="store_true", help="输出汇总 JSON")
    args = ap.parse_args()

    store = CookieStore()

    # ⚠ 安全:密码走 --pass 会出现在 ps aux 输出里;提醒后续用 --save-creds
    if args.pwd:
        print("[warn] --pass 把密码暴露到 ps aux;建议先 --save-creds 一次,以后裸跑",
              file=sys.stderr)

    # 凭据来源:CLI > config.json > .env > 交互式 getpass
    username = args.user
    password = args.pwd
    if not username or not password:
        u, p = store.get_credentials()
        username = username or u
        password = password or p
    # 仍然缺密码 → 仅当 stdin 是 tty 时交互式问一次
    if username and not password and sys.stdin.isatty():
        try:
            password = getpass.getpass(f"jAccount password for {username}: ")
        except (EOFError, KeyboardInterrupt):
            password = None

    if args.save_creds:
        if not username or not password:
            print("[错误] --save-creds 需要同时给 --user 和 --pass")
            sys.exit(1)
        store.set_credentials(username, password)
        print(f"✓ 凭据已保存到 {store.path}（0600）")
        if not args.skip_login:
            print("  继续登录…")

    # ── 登录 ────────────────────────────────────────────────────────────────
    if not args.skip_login:
        # 步骤 0:收集 seed cookies(用于让 Playwright 跳过 2FA / 复用 session)
        #   来源 A:config.json 已存的 jaccount_cookies / *_cookies(本机历史)
        #   来源 B:系统 Chrome 数据库(浏览器现成 session)
        # 关键 cookie 是 JATrustCookie + JAAuthCookie —— 注入后 jAccount 认为
        # 本次是已经通过 2FA 的可信设备,直接放行。
        chrome_imported: dict = {}
        seed_cookies: dict[str, dict[str, str]] = {}

        # 来源 A: config.json 历史 cookies(优先,即便 chrome 没装也能用)
        _CFG_DOMAIN_MAP = {
            "jaccount_cookies":  "jaccount.sjtu.edu.cn",
            "i_sjtu_cookies":    "i.sjtu.edu.cn",
            "calendar_cookies":  "calendar.sjtu.edu.cn",
            "phycai_cookies":    "www.phycai.sjtu.edu.cn",
            "lcme_cookies":      "lcme.sjtu.edu.cn",
        }
        for cfg_key, domain in _CFG_DOMAIN_MAP.items():
            cookies = store.get_cookies(cfg_key)
            if cookies:
                seed_cookies[domain] = {**seed_cookies.get(domain, {}), **cookies}
        if seed_cookies:
            n_total = sum(len(v) for v in seed_cookies.values())
            print(f"\n[0a/2] config.json 历史 cookies:{n_total} 个,"
                  f"覆盖 {sorted(seed_cookies.keys())}")

        # 来源 B: 系统 Chrome (可选)
        if not args.no_chrome_import:
            print("[0b/2] 从系统浏览器读取 cookies(覆盖/补充上面)…")
            try:
                from scripts.auth.chrome_cookies import (
                    import_from_browser, PLATFORMS as _CC_PLAT,
                )
                chrome_imported = import_from_browser(store=store)
                for plat, cookies in chrome_imported.items():
                    domain = _CC_PLAT[plat]["domain"]
                    seed_cookies[domain] = {**seed_cookies.get(domain, {}), **cookies}
            except Exception as e:
                print(f"  浏览器 cookie 导入失败：{e}")

        # 必须跑 Playwright（除非显式 skip）—— 因为大多数平台需要 SSO 触发才能
        # 拿到真正的 session cookies。但有了 seed_cookies(JATrustCookie)，
        # headless 也能直接通过 2FA
        if not username or not password:
            print("[错误] 需要 jAccount 凭据。请提供 --user / --pass，或先 --save-creds")
            sys.exit(1)
        # 默认走 trusted（headless）—— 因为 JATrustCookie 已注入，无需扫码
        # 用户也可以显式 --show 看浏览器
        use_headless = not args.show
        print(f"\n[1/2] Playwright 登录（headless={use_headless}）…\n")
        try:
            r = login_all(username, password,
                          headless=use_headless,
                          store=store,
                          seed_cookies=seed_cookies)
        except Exception as e:
            print(f"[错误] 登录流程崩溃：{e}")
            sys.exit(1)
        print(f"\n登录结果：{r['results']}")
        print(f"已保存 cookies: {r['saved']}")

    # ── 抓数据 ──────────────────────────────────────────────────────────────
    print("\n[2/2] 拉取信息…")

    cal_info = report_calendar(store)
    week1 = args.week1
    if not week1 and cal_info and cal_info.get("week1_monday"):
        week1 = cal_info["week1_monday"]

    courses = report_schedule(store, week1=week1)
    phys = report_phycai(store)
    lcme = report_lcme(store)
    mooc = report_icourse163(store)
    canvas = report_canvas()

    if args.json:
        print("\n" + "=" * 60)
        print(json.dumps({
            "calendar": cal_info,
            "courses": courses,
            "phycai": [{"due": i.due.isoformat(), "name": i.name, "room": i.location}
                       for i in phys],
            "lcme": [i.to_dict() for i in lcme],
            "icourse163": [i.to_dict() for i in mooc],
            "canvas_count": len(canvas),
        }, ensure_ascii=False, indent=2))

    print("\n✅ 完成")


if __name__ == "__main__":
    main()
