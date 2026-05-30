#!/usr/bin/env python3
"""交大新闻 + 教务通知抓取工具

目标(均为公开页面，无需登录):
  - 交大新闻网   https://news.sjtu.edu.cn   (栏目: jdyw 交大要闻 / mtjj 媒体聚焦)
  - 教务处通知   https://jwc.sjtu.edu.cn/index/mxxsdtz.htm

命令:
  news [n] [--json]   交大新闻 (默认 jdyw 栏目)
  jwc  [n] [--json]   教务处通知
  all  [n]            两者都抓
  --column <栏目>     指定新闻栏目 (jdyw/mtjj)

新闻条目 DOM (2026-05 实测): <a class="item" href="/jdyw/YYYYMMDD/id.html">
  标题在 <h3> 或 title 属性；日期可从 URL 路径 /YYYYMMDD/ 可靠提取。
"""
from __future__ import annotations

import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

TIMEOUT = 12
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

NEWS_BASE = "https://news.sjtu.edu.cn"
JWC_URL = "https://jwc.sjtu.edu.cn/index/mxxsdtz.htm"
JWC_BASE = "https://jwc.sjtu.edu.cn/"

NEWS_COLUMNS = {
    "jdyw": "交大要闻",
    "mtjj": "媒体聚焦",
}


class NewsError(Exception):
    """抓取失败。"""


def _fetch(url: str) -> str:
    """GET 一个页面，返回 UTF-8 文本。失败抛 NewsError。"""
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        raise NewsError(f"HTTP {e.code}: {url}") from e
    except URLError as e:
        raise NewsError(f"网络错误（需校园网/代理？）: {e.reason}") from e


# ===== 交大新闻 =====
# 新闻站 HTML 含畸形标签，html.parser/bs4 解析不出列表项；改用正则直接抽。
# 列表项形如 <a href="/jdyw/YYYYMMDD/id.html" ... class="card"> ... <img alt="标题"> ... </a>
# 用单条正则同时锚定 href 与同一 <a> 内的 img alt（(?:(?!</a>).)*? 禁止跨卡片边界，
# 避免相邻卡片 href/标题错位）；标题取 alt（纯净，不含正文摘要），href 自带日期。

_CARD_RE = re.compile(
    r'<a\s+href="(/[a-z]+/\d{8}/\d+\.html?)"[^>]*\bclass="card"[^>]*>'
    r'(?:(?!</a>).)*?<img[^>]*\balt="([^"]+)"',
    re.S,
)


def _date_from_url(href: str) -> str:
    """从 /jdyw/20260529/223300.html 提取 2026-05-29。"""
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", href)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def get_news(limit: int = 10, column: str = "jdyw") -> list[dict]:
    """抓取交大新闻某栏目最新条目。"""
    if column not in NEWS_COLUMNS:
        raise NewsError(f"未知栏目: {column}，可选 {'/'.join(NEWS_COLUMNS)}")
    html = _fetch(f"{NEWS_BASE}/{column}/index.html")
    matches = _CARD_RE.findall(html)
    if not matches:
        raise NewsError(f"未解析到新闻条目（{column} 页面结构可能已变）。")

    out = []
    seen = set()
    for href, title in matches:
        title = title.strip()
        if href in seen or not title:
            continue
        seen.add(href)
        out.append({
            "title": title,
            "url": urljoin(NEWS_BASE, href),
            "date": _date_from_url(href),
        })
        if len(out) >= limit:
            break
    return out


# ===== 教务处通知 (BeautifulSoup, 结构较稳定) =====

def get_jwc_notices(limit: int = 10) -> list[dict]:
    """抓取教务处面向学生的通知。"""
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise NewsError("缺少 beautifulsoup4：pip install beautifulsoup4") from e

    html = _fetch(JWC_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div.Newslist li.clearfix")
    if not items:
        raise NewsError("未解析到教务通知（jwc 页面结构可能已变）。")

    out = []
    for item in items[:limit]:
        a = item.select_one("div.wz a")
        if not a:
            continue
        h2 = a.find("h2")
        title = (h2.get_text(strip=True) if h2 else a.get_text(strip=True))
        if not title:
            continue
        href = urljoin(JWC_BASE, a.get("href", ""))

        date_str = ""
        sj = item.select_one("div.sj")
        if sj:
            day_el, ym_el = sj.find("h2"), sj.find("p")
            if day_el and ym_el:
                ym = ym_el.get_text(strip=True).replace(".", "-")  # 2026.03 -> 2026-03
                date_str = f"{ym}-{day_el.get_text(strip=True)}"

        p = item.select_one("div.wz > p")
        summary = p.get_text(strip=True)[:120] if p else ""
        out.append({"title": title, "url": href, "date": date_str, "summary": summary})
    return out


# ===== 输出 =====

def print_items(heading: str, items: list[dict]) -> None:
    print(f"\n📰 {heading}")
    print("─" * 64)
    if not items:
        print("  （暂无数据）")
        return
    for i, it in enumerate(items, 1):
        date = f" [{it['date']}]" if it.get("date") else ""
        print(f"  {i:>2}. {it['title']}{date}")
        if it.get("summary"):
            print(f"      📝 {it['summary']}")
        print(f"      🔗 {it['url']}")
    print()


# ===== CLI =====

HELP = """交大新闻 / 教务通知抓取
用法:
  python3 sjtu_news.py news [n] [--column jdyw|mtjj] [--json]
  python3 sjtu_news.py jwc  [n] [--json]
  python3 sjtu_news.py all  [n]

栏目: jdyw=交大要闻(默认)  mtjj=媒体聚焦
"""


def _parse_args(argv: list[str]) -> tuple[int, str, bool]:
    """从位置/选项参数解析 (limit, column, as_json)。"""
    limit, column, as_json = 10, "jdyw", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--column" and i + 1 < len(argv):
            column = argv[i + 1]
            i += 1
        elif a.isdigit():
            limit = int(a)
        i += 1
    return limit, column, as_json


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    cmd = argv[0].lower()
    limit, column, as_json = _parse_args(argv[1:])
    try:
        if cmd == "news":
            items = get_news(limit, column)
            print(json.dumps(items, ensure_ascii=False, indent=2)) if as_json \
                else print_items(f"交大新闻 · {NEWS_COLUMNS[column]}", items)
        elif cmd == "jwc":
            items = get_jwc_notices(limit)
            print(json.dumps(items, ensure_ascii=False, indent=2)) if as_json \
                else print_items("教务处通知", items)
        elif cmd == "all":
            print_items(f"交大新闻 · {NEWS_COLUMNS[column]}", get_news(limit, column))
            print_items("教务处通知", get_jwc_notices(limit))
        elif cmd in ("help", "-h", "--help"):
            print(HELP)
        else:
            print(f"❌ 未知命令: {cmd}")
            print(HELP)
            return 1
    except NewsError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
