"""从系统 Chrome 本地数据库直接读取 SJTU 各平台 cookies。

加速路径：如果你已经在 Chrome 里完成过 jAccount 2FA 登录，
本模块可一次性把所有相关 cookies 读出来，跳过 Playwright 扫码流程。

来源参考：kuan-er/sjtu-agent setup_config.py 的 browser_cookie3 路径。

支持的浏览器：
  - Chrome（默认）
  - Edge
  - Brave
  - Chromium
  - Firefox / Safari（如果用户用这些）

依赖：pip install browser-cookie3

注意：读取需要 Chrome 处于运行或后台状态（不要完全退出，否则数据库锁文件可能阻塞）。
      Sequoia/macOS 14+ 可能要求 Chrome 至少打开一次再关闭。
"""

from __future__ import annotations

from typing import Iterable

try:
    import browser_cookie3 as bc3
    HAS_BC3 = True
except ImportError:
    HAS_BC3 = False

from .cookie_store import CookieStore


# 各平台 cookie 域名 + 关键 key（与 sjtu-agent 对齐 + 我们扩展的平台）
PLATFORMS: dict[str, dict] = {
    "jaccount": {
        "domain": "jaccount.sjtu.edu.cn",
        "keys": ["JATrustCookie", "JAAuthCookie", "JSESSIONID"],
        "cfg_key": "jaccount_cookies",
    },
    "i_sjtu": {
        "domain": "i.sjtu.edu.cn",
        "keys": ["JSESSIONID", "route"],
        "cfg_key": "i_sjtu_cookies",
    },
    "calendar": {
        "domain": "calendar.sjtu.edu.cn",
        "keys": ["JSESSIONID"],
        "cfg_key": "calendar_cookies",
    },
    "phycai": {
        "domain": "www.phycai.sjtu.edu.cn",
        "keys": ["ASP.NET_SessionId", ".PhyEwsProj",
                 "PhyEws_StuName", "PhyEws_StuType", ".ASPXAUTH"],
        "cfg_key": "phycai_cookies",
    },
    "lcme": {
        "domain": "lcme.sjtu.edu.cn",
        "keys": ["JSESSIONID", "keepalive"],
        "cfg_key": "lcme_cookies",
    },
    "icourse163": {
        "domain": "icourse163.org",
        "keys": ["NTESSTUDYSI", "STUDY_LIVE_LOGIN_INFO",
                 "ux", "p_h5_u", "videoStudyUrl"],
        "cfg_key": "icourse_cookies",
    },
}

# 浏览器加载器优先级（找到一个能用的就停）
_BROWSERS = [
    ("chrome",   lambda d: bc3.chrome(domain_name=d)),
    ("edge",     lambda d: bc3.edge(domain_name=d)),
    ("brave",    lambda d: bc3.brave(domain_name=d)),
    ("chromium", lambda d: bc3.chromium(domain_name=d)),
    ("firefox",  lambda d: bc3.firefox(domain_name=d)),
    ("safari",   lambda d: bc3.safari(domain_name=d)),
]


def _read_one(domain: str, browser: str | None = None) -> tuple[str | None, dict[str, str]]:
    """从浏览器读 cookies，返回 (使用的浏览器, cookies dict)。"""
    if not HAS_BC3:
        return None, {}
    candidates = _BROWSERS if not browser else [b for b in _BROWSERS if b[0] == browser]
    for name, loader in candidates:
        try:
            jar = loader(domain)
            cookies = {c.name: c.value for c in jar if c.value}
            if cookies:
                return name, cookies
        except Exception:
            continue
    return None, {}


def _filter(all_cookies: dict, wanted: list[str]) -> dict[str, str]:
    """优先返回 wanted 里指定的 key；如果都没有，退回全部（避免遗漏）。"""
    out = {k: all_cookies[k] for k in wanted if k in all_cookies and all_cookies[k]}
    return out if out else all_cookies


def import_from_browser(store: CookieStore | None = None,
                         browser: str | None = None,
                         platforms: Iterable[str] | None = None) -> dict[str, dict]:
    """一键从浏览器导入指定平台 cookies 到 config.json。

    Args:
        store     CookieStore 实例（默认全局）
        browser   指定浏览器（chrome/edge/brave/...）。None = 自动尝试
        platforms 要导入的平台 keys（None = 全部）

    Returns:
        {platform_name: cookies_dict} —— 实际成功导入的内容
    """
    if not HAS_BC3:
        print("[Chrome] 缺少 browser_cookie3。请安装：pip install browser-cookie3")
        return {}

    store = store or CookieStore()
    targets = list(platforms) if platforms else list(PLATFORMS.keys())
    cfg = store.load()
    imported: dict[str, dict] = {}

    for plat in targets:
        info = PLATFORMS.get(plat)
        if not info:
            continue
        used_browser, raw = _read_one(info["domain"], browser=browser)
        if not raw:
            print(f"  [Chrome] {info['domain']:<28} ✗ 未找到 cookie（请先在浏览器里登过）")
            continue
        filtered = _filter(raw, info["keys"])
        cfg[info["cfg_key"]] = filtered
        imported[plat] = filtered
        print(f"  [Chrome] {info['domain']:<28} ✓ {used_browser} → "
              f"{len(filtered)} 个 cookie：{list(filtered.keys())}")

    if imported:
        store.save(cfg)
        print(f"\n✅ 已写入 {store.path}")
    else:
        print("\n⚠ 未导入任何 cookie。可能原因：")
        print("  - 还没在浏览器里登过那些站点")
        print("  - 浏览器完全退出导致数据库锁不可读（启动一次再 Cmd+H 隐藏即可）")
        print("  - 系统未安装 Chrome/Edge/Firefox")

    return imported


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse, json
    ap = argparse.ArgumentParser(
        description="从系统浏览器读取 SJTU 平台 cookies → config.json"
    )
    ap.add_argument("--browser", choices=["chrome", "edge", "brave", "chromium",
                                          "firefox", "safari"],
                    help="指定浏览器（默认按优先级自动尝试）")
    ap.add_argument("--only", nargs="*",
                    choices=list(PLATFORMS.keys()),
                    help="只导入指定平台")
    ap.add_argument("--list", action="store_true",
                    help="列出受支持的平台/域名")
    args = ap.parse_args()

    if args.list:
        print(json.dumps(
            {k: {"domain": v["domain"], "keys": v["keys"]}
             for k, v in PLATFORMS.items()},
            ensure_ascii=False, indent=2,
        ))
        return

    print("正在从浏览器本地数据库读取 cookies …\n")
    import_from_browser(browser=args.browser, platforms=args.only)


if __name__ == "__main__":
    main()
