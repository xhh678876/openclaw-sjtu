#!/usr/bin/env python3
"""上海交通大学生存手册 (SurviveSJTUManual) 查询工具

目标: https://survivesjtu.gitbook.io/survivesjtumanual (GitBook，公开无需登录)

目录来自 GitBook 官方 sitemap-pages.xml（真实 URL，不再硬编码——旧版硬编码 slug 已与站点
不符，导致 read/search 拼出 404）。命令:
  toc [关键词]          列目录（可选按关键词过滤）
  read <章节路径或关键词> 读某章正文
  search <关键词>        在目录标题中搜索（命中后可 read 看正文）
"""
from __future__ import annotations

import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TIMEOUT = 12
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SITE = "https://survivesjtu.gitbook.io"
SITEMAP = f"{SITE}/sitemap-pages.xml"
BASE = f"{SITE}/survivesjtumanual"


class SurviveError(Exception):
    """抓取失败。"""


def _fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        raise SurviveError(f"HTTP {e.code}: {url}") from e
    except URLError as e:
        raise SurviveError(f"网络错误（gitbook 可能需代理）: {e.reason}") from e


# ===== 目录（来自 sitemap）=====

def _slug_to_title(url: str) -> str:
    """把 .../sheng-cun-ji-qiao/jiao-da-zhuan-zhuan-ye-zhi-nan 末段转成可读标题。"""
    slug = url.rstrip("/").split("/")[-1]
    # GitBook 的拼音 slug 无法可靠还原中文，原样展示末段（去 TODO 占位噪声）
    return slug.replace("-", " ")


def get_pages() -> list[dict]:
    """从 sitemap 拉全部页面 URL（含层级路径）。"""
    xml = _fetch(SITEMAP)
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    pages = []
    seen = set()
    for url in locs:
        if not url.startswith(BASE) or url in seen:
            continue
        seen.add(url)
        # 用 BASE 之后的路径做层级展示
        rel = url[len(BASE):].strip("/")
        if not rel:
            continue
        pages.append({"url": url, "path": rel, "title": _slug_to_title(url), "depth": rel.count("/")})
    return pages


def search_pages(keyword: str) -> list[dict]:
    """在页面路径/末段里匹配关键词（拼音或 slug 片段）。"""
    kw = keyword.lower()
    return [p for p in get_pages() if kw in p["path"].lower()]


# ===== 正文 =====

def _strip_tags(html: str) -> str:
    """从 GitBook 页面粗提正文：去 script/style/nav，转纯文本。"""
    html = re.sub(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_page(target: str, max_chars: int = 5000) -> tuple[str, str]:
    """读某页正文。target 可以是完整 URL、路径片段或关键词。返回 (url, 正文)。"""
    if target.startswith("http"):
        url = target
    else:
        matches = search_pages(target)
        if not matches:
            raise SurviveError(f"未找到匹配「{target}」的章节，先用 toc/search 查路径。")
        url = matches[0]["url"]
    text = _strip_tags(_fetch(url))
    return url, text[:max_chars]


# ===== 输出 =====

def print_toc(keyword: str | None = None) -> None:
    pages = get_pages()
    if keyword:
        kw = keyword.lower()
        pages = [p for p in pages if kw in p["path"].lower()]
    print(f"\n📖 上海交通大学生存手册  ({len(pages)} 页)")
    print(f"   {BASE}")
    print("─" * 64)
    for p in pages:
        indent = "  " + "  " * min(p["depth"], 4)
        print(f"{indent}• {p['path']}")
    print(f"\n💡 read <路径片段>  读正文，如: read zhuan-zhuan-ye")
    print()


def print_search(keyword: str) -> None:
    results = search_pages(keyword)
    print(f"\n🔍 搜索「{keyword}」→ {len(results)} 个章节")
    print("─" * 64)
    if not results:
        print(f"  无匹配。在线全文搜索: {BASE}")
    for r in results:
        print(f"  • {r['path']}")
        print(f"    🔗 {r['url']}")
    print()


def print_read(target: str) -> None:
    url, text = read_page(target)
    print(f"\n📖 {url}")
    print("─" * 64)
    print(text if text else "（正文为空或解析失败，请直接访问上方链接）")
    print()


# ===== CLI =====

HELP = """上海交通大学生存手册
用法:
  python3 sjtu_survive.py toc [关键词]       列目录(可过滤)
  python3 sjtu_survive.py search <关键词>    搜章节
  python3 sjtu_survive.py read <路径片段>    读正文

示例:
  python3 sjtu_survive.py search zhuan-zhuan-ye
  python3 sjtu_survive.py read bao-yan
注: GitBook slug 为拼音，搜索用拼音片段(如 gpa/bao-yan/xuan-ke)更准。
"""


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    cmd = argv[0].lower()
    try:
        if cmd == "toc":
            print_toc(argv[1] if len(argv) > 1 else None)
        elif cmd == "search":
            if len(argv) < 2:
                print("用法: search <关键词>")
                return 1
            print_search(argv[1])
        elif cmd == "read":
            if len(argv) < 2:
                print("用法: read <路径片段>")
                return 1
            print_read(argv[1])
        elif cmd in ("help", "-h", "--help"):
            print(HELP)
        else:
            print(f"❌ 未知命令: {cmd}")
            print(HELP)
            return 1
    except SurviveError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
