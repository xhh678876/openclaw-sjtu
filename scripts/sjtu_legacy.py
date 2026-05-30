#!/usr/bin/env python3
"""传承·交大 (share.dyweb.sjtu.cn) — 往年课程资料 / 试卷查询工具

新站后端 API：https://api.beta.share.dyweb.sjtu.cn/api/v1  （Go，信封 {code,data,message,success}）
认证：jAccount OAuth 登录后拿到的 token，放在 HTTP header  `Auth: <token>`（不是 Bearer）。
      传承**没有免登录读接口**——所有 /course、/material 端点都返回 401 login required。

token 来源（按优先级）：
  1. 环境变量  DYWEB_TOKEN
  2. config.json 的  "dyweb_token"
  3. cookie-saver 抓的 dump：~/.openclaw/skills-data/sjtu-credentials/share-dyweb-sjtu-cn.json
     （字段 token；由 scripts/save_sjtu_cookies.py legacy 登录后写入）

拿 token 的方式：
  - 跑  python3 scripts/save_sjtu_cookies.py legacy  → 浏览器登 jAccount → 自动抓 token
  - 或 浏览器 F12 → Application → Local Storage / Cookies 里复制 token，填进 config.json

已实测端点（需 token）：
  POST /course/search          body {keyword}            搜课程
  GET  /course/get/{id}                                  课程详情
  GET  /course/get/{id}/classes                          开课班级
  GET  /material?course_id={id}                          课程的资料列表
  GET  /material/get/{id}                                资料详情
  GET  /material-type                                    资料类型字典
  GET  /prompt/course?keyword=                           搜索补全
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.beta.share.dyweb.sjtu.cn/api/v1"
WEB_BASE = "https://beta.share.dyweb.sjtu.cn"
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.json"
CRED_FILE = Path.home() / ".openclaw" / "skills-data" / "sjtu-credentials" / "share-dyweb-sjtu-cn.json"
DEFAULT_TIMEOUT = 15


class LegacyError(Exception):
    """传承 API 调用失败（认证 / 网络 / 资源）。"""


class LoginRequired(LegacyError):
    """缺 token 或 token 失效——需要 jAccount 登录。"""


# ===== token 加载 =====

def load_token() -> str:
    """按优先级取传承 token：env → config.json → cookie-saver dump。"""
    env = os.environ.get("DYWEB_TOKEN", "").strip()
    if env:
        return env
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        tok = (cfg.get("dyweb_token") or "").strip()
        if tok:
            return tok
    if CRED_FILE.exists():
        try:
            dump = json.loads(CRED_FILE.read_text(encoding="utf-8"))
            tok = (dump.get("token") or "").strip()
            if tok:
                return tok
        except (json.JSONDecodeError, OSError):
            pass
    raise LoginRequired(
        "未找到传承 token（需 jAccount 登录）。\n"
        "  方法1: python3 scripts/save_sjtu_cookies.py legacy   # 浏览器登一次，自动抓 token\n"
        '  方法2: 在 config.json 设置  "dyweb_token": "..."（F12→Application 里复制）\n'
        "  方法3: export DYWEB_TOKEN=..."
    )


# ===== 请求 =====

def api_request(path: str, method: str = "GET",
                params: dict[str, Any] | None = None,
                body: dict[str, Any] | None = None) -> Any:
    """调用传承 API，返回信封里的 data。失败抛 LegacyError / LoginRequired。"""
    token = load_token()
    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {"Auth": token, "Accept": "application/json", "User-Agent": "openclaw-sjtu/legacy"}
    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")

    req = Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        if e.code == 401:
            raise LoginRequired(
                "token 失效或缺失（401 login required）。请重新登录抓 token："
                "python3 scripts/save_sjtu_cookies.py legacy"
            ) from e
        raise LegacyError(f"请求失败 (HTTP {e.code}): {raw[:200]}") from e
    except URLError as e:
        raise LegacyError(f"网络错误（需校园网/代理？）: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise LegacyError("响应不是合法 JSON。") from e

    if not envelope.get("success"):
        msg = envelope.get("message", "未知错误")
        if envelope.get("code") == 401:
            raise LoginRequired(f"需要登录: {msg}")
        raise LegacyError(f"接口返回失败: {msg}")
    return envelope.get("data")


# ===== 功能 =====

def search_courses(keyword: str) -> list[dict[str, Any]]:
    """搜课程（POST /course/search）。返回原始 data（list 或含 list 的 dict）。"""
    data = api_request("/course/search", method="POST", body={"keyword": keyword})
    return _as_list(data)


def get_course(course_id: int | str) -> Any:
    """课程详情（含资源概况）。"""
    return api_request(f"/course/get/{course_id}")


def list_materials(course_id: int | str) -> list[dict[str, Any]]:
    """某课程的资料列表。"""
    return _as_list(api_request("/material", params={"course_id": course_id}))


def get_material(material_id: int | str) -> Any:
    """资料详情。"""
    return api_request(f"/material/get/{material_id}")


def material_types() -> Any:
    """资料类型字典。"""
    return api_request("/material-type")


def _as_list(data: Any) -> list[dict[str, Any]]:
    """API 的 data 可能是 list，或 {items/list/results/data: [...]}，统一成 list。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "list", "results", "data", "courses", "materials"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


# ===== 输出 =====

def _g(d: dict[str, Any], *keys: str, default: Any = "") -> Any:
    """容错取字段：返回第一个存在的 key（适配未定字段名）。"""
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def print_search(keyword: str, courses: list[dict[str, Any]]) -> None:
    print(f"\n🔍 传承·交大 搜索「{keyword}」→ {len(courses)} 个课程")
    print("─" * 60)
    if not courses:
        print("  无结果。换个关键词，或确认 token 有效。")
        return
    for c in courses:
        cid = _g(c, "id", "ID", "course_id")
        name = _g(c, "name", "course_name", "title")
        code = _g(c, "code", "course_code")
        teacher = _g(c, "teacher", "teacher_name", "main_teacher")
        if isinstance(teacher, dict):
            teacher = _g(teacher, "name")
        count = _g(c, "material_count", "count", "resource_count", default="?")
        print(f"  #{cid} [{code}] {name}")
        print(f"      👨‍🏫 {teacher}  📎 资料 {count}")


def print_materials(course_id: str, materials: list[dict[str, Any]]) -> None:
    print(f"\n📎 课程 #{course_id} 的资料 → {len(materials)} 份")
    print("─" * 60)
    if not materials:
        print("  暂无资料，或无权限查看。")
        return
    for m in materials:
        mid = _g(m, "id", "ID", "material_id")
        title = _g(m, "title", "name", "file_name", "fileName")
        mtype = _g(m, "type", "type_name", "material_type", default="?")
        price = _g(m, "price", "points", "cost", default="?")
        size = _g(m, "size", "file_size", "fileSize", default="")
        print(f"  #{mid} {title}")
        print(f"      类型 {mtype} | 积分 {price}{' | ' + str(size) if size else ''}")


def print_raw(label: str, data: Any) -> None:
    print(f"\n📦 {label}")
    print("─" * 60)
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])


# ===== 自检 =====

def selftest() -> int:
    """探活：有 token 则验证端点；无 token 则诚实报告。"""
    try:
        token = load_token()
    except LoginRequired as e:
        print(f"⚠️  {e}")
        print("\n（这是预期内的：传承交大没有免登录接口。抓到 token 后再 selftest。）")
        return 1
    print(f"🔑 token: {token[:6]}…{token[-4:] if len(token) > 10 else ''}")
    try:
        courses = search_courses("高等数学")
        print(f"  ✅ /course/search -> {len(courses)} 个课程")
        types = material_types()
        n = len(types) if isinstance(types, list) else len(_as_list(types))
        print(f"  ✅ /material-type -> {n} 种类型")
        return 0
    except LegacyError as e:
        print(f"  ❌ {e}")
        return 1


# ===== CLI =====

HELP = """
📖 传承·交大 (share.dyweb.sjtu.cn) 往年资料查询
────────────────────────────────────────────
  search   <关键词>          搜课程
  course   <课程ID>          课程详情
  materials <课程ID>         某课程的资料列表
  material <资料ID>          资料详情
  types                      资料类型字典
  selftest                   检查 token / 连通性
  help                       显示帮助

认证：需 jAccount 登录拿 token（传承无免登录接口）。
  python3 scripts/save_sjtu_cookies.py legacy   # 抓 token
  或在 config.json 设置 "dyweb_token"，或 export DYWEB_TOKEN=...

注意：下载资料 (/material/download) 会消耗积分，本工具不自动下载。
网页版：https://beta.share.dyweb.sjtu.cn/
"""


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    cmd = argv[0]
    try:
        if cmd == "help":
            print(HELP)
        elif cmd == "selftest":
            return selftest()
        elif cmd == "search":
            if len(argv) < 2:
                print("用法: search <关键词>")
                return 1
            print_search(" ".join(argv[1:]), search_courses(" ".join(argv[1:])))
        elif cmd == "course":
            if len(argv) < 2:
                print("用法: course <课程ID>")
                return 1
            print_raw(f"课程 #{argv[1]} 详情", get_course(argv[1]))
        elif cmd == "materials":
            if len(argv) < 2:
                print("用法: materials <课程ID>")
                return 1
            print_materials(argv[1], list_materials(argv[1]))
        elif cmd == "material":
            if len(argv) < 2:
                print("用法: material <资料ID>")
                return 1
            print_raw(f"资料 #{argv[1]} 详情", get_material(argv[1]))
        elif cmd == "types":
            print_raw("资料类型字典", material_types())
        else:
            print(f"未知命令: {cmd}")
            print(HELP)
            return 1
    except LoginRequired as e:
        print(f"🔒 {e}")
        return 1
    except LegacyError as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
