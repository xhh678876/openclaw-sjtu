#!/usr/bin/env python3
"""视觉交大 (vs.sjtu.edu.cn/jtdx) — 校园官方图库

站点是传统 jQuery 站（非 SPA/WP）。首页列出主题相册（themeId + 名称 + 图片数），
图片列表走 AJAX 接口 POST /jtdx/index/images2。公开浏览/下载，无需登录。

命令:
  themes [--json]              列出主题相册（南洋筑韵/SJTU SCENE/航拍/运动交大…）
  images <themeId> [n] [--json] 列某主题的图片（含原图直链、尺寸、下载数）
  search <关键词> [n] [--json]  全站按关键词搜图
  download <imageId> [路径]     下载单张原图（需先 images/search 拿到 imageId）

实测接口（2026-05）:
  GET  /jtdx/index                            首页(主题列表)
  POST /jtdx/index/images2?type=1&pageSize=&pageNo=   body: themeId,tagId,searchContent
       -> {code:"0000", imageList:[{id,name,photoer,imageUrl,imageWidth,downloadNum,...}]}
  图片直链 = https://vs.sjtu.edu.cn/jtdx + imageUrl(反斜杠转/)
"""
from __future__ import annotations

import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://vs.sjtu.edu.cn/jtdx"
HOME = f"{BASE}/index"
IMAGES_API = f"{BASE}/index/images2"
TIMEOUT = 20
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


class VisualError(Exception):
    """视觉交大接口调用失败。"""


def _get(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        raise VisualError(f"HTTP {e.code}: {url}") from e
    except URLError as e:
        raise VisualError(f"网络错误（需校园网/代理？）: {e.reason}") from e


def _post_json(url: str, form: dict) -> dict:
    body = urlencode(form).encode("utf-8")
    req = Request(url, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except HTTPError as e:
        raise VisualError(f"HTTP {e.code}: {url}") from e
    except URLError as e:
        raise VisualError(f"网络错误（需校园网/代理？）: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise VisualError("响应不是合法 JSON。") from e


# ===== 主题相册 =====

_THEME_RE = re.compile(r'href="/jtdx/index/imagesList\?themeId=(\d+)"(.*?)</a>', re.S)
_COUNT_RE = re.compile(r"图片数量[：:]\s*(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _dedupe_name(name: str) -> str:
    """名称常整段重复两次（"南洋筑韵 南洋筑韵" / "SJTU SCENE SJTU SCENE"）。若前半==后半则取前半。"""
    name = name.strip()
    n = len(name)
    if n >= 2 and n % 2 == 0:
        half = name[: n // 2].strip()
        if half and half == name[n // 2:].strip():
            return half
    return name


def get_themes() -> list[dict]:
    """从首页抽主题相册，按 themeId 去重（取最完整的名称与图片数）。"""
    html = _get(HOME)
    themes: dict[str, dict] = {}
    for tid, inner in _THEME_RE.findall(html):
        text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", inner)).strip()
        count_m = _COUNT_RE.search(text)
        count = int(count_m.group(1)) if count_m else None
        # 去掉"图片数量：N"片段，剩下的是名称（可能整段重复两次，如 "南洋筑韵 ... 南洋筑韵"）
        name = _COUNT_RE.sub("", text).replace("图片数量", "").strip().strip("：:> ").strip()
        name = _dedupe_name(name) or f"主题{tid}"
        cur = themes.get(tid)
        if cur is None:
            themes[tid] = {"themeId": tid, "name": name, "count": count}
        else:
            if count is not None and cur["count"] is None:
                cur["count"] = count
            if len(name) > len(cur["name"]):
                cur["name"] = name
    return list(themes.values())


# ===== 图片列表 =====

def _image_url(rel: str) -> str:
    """imageUrl(/resources/images\\id/..jpg) -> 绝对直链。"""
    return f"{BASE}{rel.replace(chr(92), '/')}" if rel else ""


def _norm_image(img: dict) -> dict:
    return {
        "id": img.get("id"),
        "name": (img.get("name") or "").strip(),
        "photographer": img.get("photoer", ""),
        "url": _image_url(img.get("imageUrl", "")),
        "width": img.get("imageWidth"),
        "height": img.get("imageHeight"),
        "downloads": img.get("downloadNum", 0),
        "likes": img.get("goodNum", 0),
        "keyword": img.get("keyword", ""),
    }


def list_images(theme_id: str, limit: int = 12) -> list[dict]:
    """列某主题的图片。"""
    data = _post_json(f"{IMAGES_API}?type=1&pageSize={limit}&pageNo=1",
                      {"themeId": str(theme_id), "tagId": "", "searchContent": ""})
    if data.get("code") != "0000":
        raise VisualError(f"接口返回失败: {data.get('message', '未知')}")
    return [_norm_image(i) for i in (data.get("imageList") or [])]


def search_images(keyword: str, limit: int = 12) -> list[dict]:
    """全站按关键词搜图（searchContent）。"""
    data = _post_json(f"{IMAGES_API}?type=1&pageSize={limit}&pageNo=1",
                      {"themeId": "", "tagId": "", "searchContent": keyword})
    if data.get("code") != "0000":
        raise VisualError(f"接口返回失败: {data.get('message', '未知')}")
    return [_norm_image(i) for i in (data.get("imageList") or [])]


def download_image(image_url: str, out_path: str) -> int:
    """下载原图到本地，返回字节数。"""
    req = Request(image_url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=TIMEOUT * 3) as resp:
            data = resp.read()
    except (HTTPError, URLError) as e:
        raise VisualError(f"下载失败: {e}") from e
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)


# ===== 输出 =====

def print_themes(themes: list[dict]) -> None:
    print(f"\n🎨 视觉交大 主题相册 ({len(themes)} 个)")
    print("─" * 60)
    for t in themes:
        cnt = f"{t['count']} 张" if t["count"] is not None else "?"
        print(f"  themeId={t['themeId']:<4} {t['name']:<16} {cnt}")
    print("\n💡 看图: images <themeId> [数量]")
    print()


def print_images(heading: str, images: list[dict]) -> None:
    print(f"\n🖼️  {heading} → {len(images)} 张")
    print("─" * 60)
    if not images:
        print("  （无结果）")
        return
    for im in images:
        size = f"{im['width']}×{im['height']}" if im["width"] else ""
        print(f"  #{im['id']} {im['name']}  [{size}]  📷{im['photographer']}  ⬇️{im['downloads']}")
        print(f"      {im['url']}")
    print("\n💡 下载: download <imageId 对应的 url> [路径]，或直接用上面的链接")
    print()


# ===== CLI =====

HELP = """视觉交大 官方图库 (vs.sjtu.edu.cn)
用法:
  python3 sjtu_visual.py themes [--json]               主题相册列表
  python3 sjtu_visual.py images <themeId> [n] [--json] 某主题的图片(含原图直链)
  python3 sjtu_visual.py search <关键词> [n] [--json]   全站搜图
  python3 sjtu_visual.py download <图片直链> [输出路径]  下载原图

示例:
  python3 sjtu_visual.py themes
  python3 sjtu_visual.py images 42 6        # SJTU SCENE 主题前6张
  python3 sjtu_visual.py search 图书馆
"""


def _split_args(rest: list[str]) -> tuple[list[str], bool]:
    as_json = "--json" in rest
    return [a for a in rest if a != "--json"], as_json


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    cmd = argv[0].lower()
    args, as_json = _split_args(argv[1:])
    try:
        if cmd == "themes" or cmd == "albums":  # albums 兼容旧名
            data = get_themes()
            print(json.dumps(data, ensure_ascii=False, indent=2)) if as_json else print_themes(data)
        elif cmd == "images":
            if not args or not args[0].isdigit():
                print("用法: images <themeId> [数量]")
                return 1
            n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 12
            data = list_images(args[0], n)
            print(json.dumps(data, ensure_ascii=False, indent=2)) if as_json else print_images(f"主题 #{args[0]}", data)
        elif cmd == "search":
            if not args:
                print("用法: search <关键词> [数量]")
                return 1
            n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 12
            data = search_images(args[0], n)
            print(json.dumps(data, ensure_ascii=False, indent=2)) if as_json else print_images(f"搜索「{args[0]}」", data)
        elif cmd == "download":
            if not args:
                print("用法: download <图片直链> [输出路径]")
                return 1
            url = args[0]
            out = args[1] if len(args) > 1 else url.split("/")[-1]
            n = download_image(url, out)
            print(f"✅ 已下载 {n} 字节 → {out}")
        elif cmd in ("help", "-h", "--help"):
            print(HELP)
        else:
            print(f"❌ 未知命令: {cmd}")
            print(HELP)
            return 1
    except VisualError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
