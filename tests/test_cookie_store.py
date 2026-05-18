"""CookieStore 单元测试。

覆盖:
  - get_cookies() 的 "YOUR_" 占位过滤
  - set_cookies() / get_credentials() 圆环写读
  - save() 0600 权限 + 原子写(tmp 中途崩溃不留半写文件)
  - collect_from_playwright() 按域名归集 + 跳过未声明域名
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.auth.cookie_store import CookieStore, DOMAIN_TO_KEY


@pytest.fixture
def tmp_store(tmp_path: Path) -> CookieStore:
    return CookieStore(path=tmp_path / "config.json")


# ── get_cookies: YOUR_ 占位过滤 ────────────────────────────────────────────

def test_get_cookies_filters_placeholder(tmp_store: CookieStore) -> None:
    tmp_store.save({"phycai_cookies": {
        "real": "abc123",
        "ASP.NET_SessionId": "YOUR_SESSION_ID_HERE",
        ".ASPXAUTH": "YOUR_AUTH_TOKEN",
    }})
    cookies = tmp_store.get_cookies("phycai_cookies")
    assert cookies == {"real": "abc123"}


def test_get_cookies_missing_key_returns_empty(tmp_store: CookieStore) -> None:
    tmp_store.save({"other_key": {"x": "y"}})
    assert tmp_store.get_cookies("nonexistent") == {}


def test_get_cookies_when_no_config_returns_empty(tmp_store: CookieStore) -> None:
    # path 不存在
    assert tmp_store.get_cookies("anything") == {}


# ── 凭据读写圆环 ───────────────────────────────────────────────────────────

def test_set_credentials_round_trip(tmp_store: CookieStore) -> None:
    tmp_store.set_credentials("alice", "s3cret")
    u, p = tmp_store.get_credentials()
    assert u == "alice"
    assert p == "s3cret"


def test_get_credentials_strips_whitespace(tmp_store: CookieStore) -> None:
    tmp_store.save({"jaccount_username": "  bob  \n", "jaccount_password": " pw "})
    u, p = tmp_store.get_credentials()
    assert u == "bob"
    assert p == "pw"


def test_get_credentials_falls_back_to_env(tmp_store: CookieStore,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JACCOUNT_USERNAME", "env_user")
    monkeypatch.setenv("JACCOUNT_PASSWORD", "env_pw")
    u, p = tmp_store.get_credentials()
    assert u == "env_user"
    assert p == "env_pw"


# ── save() 权限 + 原子性 ───────────────────────────────────────────────────

def test_save_writes_0600(tmp_store: CookieStore) -> None:
    tmp_store.save({"k": "v"})
    mode = stat.S_IMODE(os.stat(tmp_store.path).st_mode)
    # 仅 owner 读写,no group/world
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_save_overwrites_existing(tmp_store: CookieStore) -> None:
    tmp_store.save({"a": 1})
    tmp_store.save({"b": 2})
    loaded = tmp_store.load()
    assert loaded == {"b": 2}


def test_save_atomic_on_crash(tmp_store: CookieStore,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟写 .tmp 期间崩溃 —— config.json 必须保持上次内容,不会出现 0 字节文件。"""
    tmp_store.save({"committed": "old"})
    orig_dump = json.dump

    def boom(*args, **kwargs):
        raise RuntimeError("disk full simulated")

    monkeypatch.setattr(json, "dump", boom)
    with pytest.raises(RuntimeError):
        tmp_store.save({"committed": "new"})

    # config.json 仍是上次的内容,完整未损坏
    monkeypatch.setattr(json, "dump", orig_dump)
    loaded = tmp_store.load()
    assert loaded == {"committed": "old"}
    # .tmp 已经被清理
    tmp_path = tmp_store.path.with_suffix(tmp_store.path.suffix + ".tmp")
    assert not tmp_path.exists()


# ── collect_from_playwright ───────────────────────────────────────────────

def test_collect_from_playwright_groups_by_domain(tmp_store: CookieStore) -> None:
    fake_ctx = MagicMock()
    fake_ctx.cookies.return_value = [
        {"domain": "phycai.sjtu.edu.cn", "name": "PHPSESSID", "value": "p1"},
        {"domain": ".phycai.sjtu.edu.cn", "name": ".ASPXAUTH", "value": "p2"},
        {"domain": "i.sjtu.edu.cn", "name": "JSESSIONID", "value": "j1"},
        {"domain": "example.com", "name": "ignored", "value": "x"},  # 非白名单域名
    ]

    updated = tmp_store.collect_from_playwright(fake_ctx)
    assert set(updated) == {"phycai_cookies", "i_sjtu_cookies"}

    saved = tmp_store.load()
    assert saved["phycai_cookies"] == {"PHPSESSID": "p1", ".ASPXAUTH": "p2"}
    assert saved["i_sjtu_cookies"] == {"JSESSIONID": "j1"}
    assert "ignored" not in json.dumps(saved)


def test_collect_from_playwright_merges_by_default(tmp_store: CookieStore) -> None:
    """回归测试:失败的 Playwright 会话只拿到 JSESSIONID,不能把上次的
    JATrustCookie 替换没了 —— 否则下次必须重新 2FA。"""
    tmp_store.save({"jaccount_cookies": {
        "JATrustCookie": "trust_value_from_prev_2fa",
        "JAAuthCookie": "auth_value",
        "JSESSIONID": "old_session",
    }})
    # 模拟一次"半截"的 Playwright session —— 只有 JSESSIONID
    fake_ctx = MagicMock()
    fake_ctx.cookies.return_value = [
        {"domain": "jaccount.sjtu.edu.cn", "name": "JSESSIONID", "value": "new_session"},
    ]
    tmp_store.collect_from_playwright(fake_ctx)

    saved = tmp_store.get_cookies("jaccount_cookies")
    # JATrustCookie 必须保留,否则下次走不过 2FA
    assert saved["JATrustCookie"] == "trust_value_from_prev_2fa"
    assert saved["JAAuthCookie"] == "auth_value"
    # JSESSIONID 应该被新值覆盖
    assert saved["JSESSIONID"] == "new_session"


def test_collect_from_playwright_replace_when_merge_false(tmp_store: CookieStore) -> None:
    """显式 merge=False 时是老行为:整组替换。"""
    tmp_store.save({"jaccount_cookies": {"JATrustCookie": "keep_me_no"}})
    fake_ctx = MagicMock()
    fake_ctx.cookies.return_value = [
        {"domain": "jaccount.sjtu.edu.cn", "name": "JSESSIONID", "value": "s"},
    ]
    tmp_store.collect_from_playwright(fake_ctx, merge=False)
    saved = tmp_store.get_cookies("jaccount_cookies")
    assert "JATrustCookie" not in saved
    assert saved == {"JSESSIONID": "s"}
