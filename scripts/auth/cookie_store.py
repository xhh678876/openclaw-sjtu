"""统一 cookie 持久化（写入 ~/openclaw-sjtu/config.json）。

config.json 顶层 key 约定：
  jaccount_cookies     — *.sjtu.edu.cn 通用（OAuth 跳转后取得）
  phycai_cookies       — phycai.sjtu.edu.cn
  i_sjtu_cookies       — i.sjtu.edu.cn (新教务)
  calendar_cookies     — calendar.sjtu.edu.cn (校历)
  icourse_cookies      — icourse163.org (中国大学MOOC)
  canvas_token         — Canvas LMS Bearer Token（已存在）
  jaccount_username    — jAccount 用户名（用于自动登录）
  jaccount_password    — jAccount 密码（明文，仅本地 600 权限）
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path.home() / "openclaw-sjtu" / "config.json"


# 域名 → config.json 中 cookie key 的映射
DOMAIN_TO_KEY: dict[str, str] = {
    "jaccount.sjtu.edu.cn":    "jaccount_cookies",
    "www.phycai.sjtu.edu.cn":  "phycai_cookies",
    "phycai.sjtu.edu.cn":      "phycai_cookies",
    "i.sjtu.edu.cn":           "i_sjtu_cookies",
    "calendar.sjtu.edu.cn":    "calendar_cookies",
    "lcme.sjtu.edu.cn":        "lcme_cookies",
    "www.icourse163.org":      "icourse_cookies",
    "icourse163.org":          "icourse_cookies",
}


class CookieStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = Path(path)

    # ── 读 ──────────────────────────────────────────────────────────────────
    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def get_cookies(self, key: str) -> dict[str, str]:
        cfg = self.load()
        cookies = cfg.get(key) or {}
        # 过滤掉占位值
        return {k: v for k, v in cookies.items() if not str(v).startswith("YOUR_")}

    # ── 写 ──────────────────────────────────────────────────────────────────
    def save(self, cfg: dict) -> None:
        """原子写入 config.json。

        含明文密码/cookies,所以:
          1) 写到同目录 .tmp(O_CREAT|O_WRONLY|O_TRUNC mode=0o600),保证从一开始
             就是 600 权限,杜绝 write→chmod 之间的 0644 窗口
          2) os.replace() 原子替换 —— 并发写不会损坏文件,中途崩溃也不会留下
             半写状态的 config.json
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        os.replace(tmp, self.path)
        # 防御性:某些文件系统 os.replace 不保留 source mode
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def set_cookies(self, key: str, cookies: dict[str, str]) -> None:
        cfg = self.load()
        cfg[key] = cookies
        self.save(cfg)

    # ── 从 Playwright BrowserContext 收集 ───────────────────────────────────
    def collect_from_playwright(self, ctx, domains: Iterable[str] | None = None) -> list[str]:
        """从 Playwright 的 BrowserContext.cookies() 中按域名归集并写入 config.json。

        Returns: 成功更新的 config key 列表。
        """
        targets = set(domains) if domains else set(DOMAIN_TO_KEY.keys())
        bucket: dict[str, dict[str, str]] = {}
        for c in ctx.cookies():
            domain = c["domain"].lstrip(".")
            for d, key in DOMAIN_TO_KEY.items():
                if d not in targets:
                    continue
                if domain == d or domain.endswith("." + d):
                    bucket.setdefault(key, {})[c["name"]] = c["value"]
                    break

        if not bucket:
            return []

        cfg = self.load()
        updated = []
        for key, cookies in bucket.items():
            cfg[key] = cookies
            updated.append(key)
        self.save(cfg)
        return updated

    # ── jAccount 凭据 ───────────────────────────────────────────────────────
    def get_credentials(self) -> tuple[str | None, str | None]:
        cfg = self.load()
        u = cfg.get("jaccount_username") or os.environ.get("JACCOUNT_USERNAME") or None
        p = cfg.get("jaccount_password") or os.environ.get("JACCOUNT_PASSWORD") or None
        return (u.strip() if u else None, p.strip() if p else None)

    def set_credentials(self, username: str, password: str) -> None:
        cfg = self.load()
        cfg["jaccount_username"] = username
        cfg["jaccount_password"] = password
        self.save(cfg)
