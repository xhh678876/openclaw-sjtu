#!/usr/bin/env python3
"""
交大新闻 + 教务通知爬虫
目标:
  - https://news.sjtu.edu.cn （新闻网）
  - https://jwc.sjtu.edu.cn/index/mxxsdtz.htm （教务处通知）
  - https://gk.sjtu.edu.cn （信息公开网）
"""

import sys
import re
import json
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ============================================================
# 常量
# ============================================================

TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

NEWS_URL = "https://news.sjtu.edu.cn"
JWC_URL = "https://jwc.sjtu.edu.cn/index/mxxsdtz.htm"
GK_URL = "https://gk.sjtu.edu.cn"


# ============================================================
# 交大新闻网
# ============================================================

def get_news(limit: int = 10) -> list[dict]:
    """爬取交大新闻网最新新闻"""
    results = []

    try:
        resp = requests.get(NEWS_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试多种选择器
        selectors = [
            "ul.news-list li a",
            "div.news-item a",
            ".list-item a",
            "a[href*='/info/']",
            "a[href*='content']",
        ]

        links = []
        for sel in selectors:
            links = soup.select(sel)
            if links:
                break

        # 如果选择器都不行，找所有有标题的链接
        if not links:
            links = [a for a in soup.find_all("a", href=True)
                     if a.get_text(strip=True) and len(a.get_text(strip=True)) > 8
                     and not a.get_text(strip=True).startswith(("首页", "关于", "English", "登录"))]

        seen = set()
        for a in links:
            if len(results) >= limit:
                break
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or len(title) < 4 or title in seen:
                continue
            seen.add(title)

            # 补全相对链接
            if href.startswith("/"):
                href = NEWS_URL + href
            elif not href.startswith("http"):
                href = NEWS_URL + "/" + href

            # 尝试从周围提取日期
            date_str = ""
            parent = a.parent
            if parent:
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', parent.get_text())
                if date_match:
                    date_str = date_match.group(1)

            results.append({"title": title, "url": href, "date": date_str})

    except Exception as e:
        print(f"⚠️ 爬取新闻网失败: {e}", file=sys.stderr)
        results = _fallback_news()

    return results[:limit]


def _fallback_news() -> list[dict]:
    """降级: 硬编码提示"""
    return [{
        "title": "（无法获取最新新闻，请直接访问网站）",
        "url": NEWS_URL,
        "date": "",
    }]


# ============================================================
# 教务处通知
# ============================================================

def get_jwc_notices(limit: int = 10) -> list[dict]:
    """爬取教务处面向学生的通知"""
    results = []

    try:
        resp = requests.get(JWC_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 教务处页面结构: div.Newslist > ul > li.clearfix
        # 每个 li 包含 div.sj(日期) + div.wz(标题+摘要)
        items = soup.select("div.Newslist li.clearfix")

        if items:
            for item in items[:limit]:
                a = item.select_one("div.wz a")
                if not a:
                    continue
                h2 = a.find("h2")
                title = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
                if not title:
                    continue

                href = a.get("href", "")
                # 链接格式: ../info/1222/125441.htm → 补全为绝对路径
                if href.startswith("../"):
                    href = "https://jwc.sjtu.edu.cn/" + href.lstrip("../")
                elif href.startswith("/"):
                    href = "https://jwc.sjtu.edu.cn" + href
                elif not href.startswith("http"):
                    href = "https://jwc.sjtu.edu.cn/" + href

                # 日期: div.sj 中 h2=日, p=年.月
                date_str = ""
                sj = item.select_one("div.sj")
                if sj:
                    day_el = sj.find("h2")
                    ym_el = sj.find("p")
                    if day_el and ym_el:
                        day = day_el.get_text(strip=True)
                        ym = ym_el.get_text(strip=True)  # e.g. "2026.03"
                        date_str = f"{ym}.{day}".replace(".", "-")  # "2026-03-30"

                # 摘要
                summary = ""
                p = item.select_one("div.wz > p")
                if p:
                    summary = p.get_text(strip=True)[:120]

                results.append({
                    "title": title,
                    "url": href,
                    "date": date_str,
                    "summary": summary,
                })
        else:
            # 降级: 通用链接抓取
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                if title and len(title) > 8 and len(results) < limit:
                    href = a["href"]
                    if href.startswith("../"):
                        href = "https://jwc.sjtu.edu.cn/" + href.lstrip("../")
                    elif href.startswith("/"):
                        href = "https://jwc.sjtu.edu.cn" + href
                    elif not href.startswith("http"):
                        href = "https://jwc.sjtu.edu.cn/" + href

                    # 跳过导航链接
                    if any(kw in title for kw in ("首页", "关于", "部门", "办公室", "English")):
                        continue

                    date_str = ""
                    parent = a.parent
                    if parent:
                        dm = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})', parent.get_text())
                        if dm:
                            date_str = dm.group(1)

                    results.append({"title": title, "url": href, "date": date_str})

    except Exception as e:
        print(f"⚠️ 爬取教务处失败: {e}", file=sys.stderr)
        results = [{"title": "（无法获取，请直接访问）", "url": JWC_URL, "date": ""}]

    return results[:limit]


# ============================================================
# 信息公开网
# ============================================================

def get_gk_notices(limit: int = 10) -> list[dict]:
    """爬取信息公开网最新公告"""
    results = []

    try:
        resp = requests.get(GK_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试常见选择器
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if title and len(title) > 6 and len(results) < limit:
                href = a["href"]
                if href.startswith("/"):
                    href = GK_URL + href
                elif not href.startswith("http"):
                    href = GK_URL + "/" + href

                # 过滤导航链接
                if any(kw in title for kw in ("首页", "关于", "English", "登录", "注册", "搜索")):
                    continue

                date_str = ""
                parent = a.parent
                if parent:
                    dm = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', parent.get_text())
                    if dm:
                        date_str = dm.group(1)

                results.append({"title": title, "url": href, "date": date_str})

    except Exception as e:
        print(f"⚠️ 爬取信息公开网失败: {e}", file=sys.stderr)
        # 信息公开网可能是 JS 渲染
        print("💡 提示: 信息公开网可能需要 JS 渲染，建议直接访问", file=sys.stderr)
        results = [{"title": "（无法获取，请直接访问）", "url": GK_URL, "date": ""}]

    return results[:limit]


# ============================================================
# 输出格式化
# ============================================================

def print_items(title: str, items: list[dict]):
    """格式化输出列表"""
    print(f"\n📰 {title}")
    print("─" * 60)
    if not items:
        print("  （暂无数据）")
        return
    for i, item in enumerate(items, 1):
        date_part = f" [{item['date']}]" if item.get("date") else ""
        print(f"  {i:>2}. {item['title']}{date_part}")
        if item.get("summary"):
            print(f"      📝 {item['summary'][:100]}")
        if item.get("url"):
            print(f"      🔗 {item['url']}")
    print()


# ============================================================
# CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_news.py <命令> [数量]")
        print()
        print("命令:")
        print("  news [n]  交大新闻网最新新闻 (默认10条)")
        print("  jwc  [n]  教务处面向学生通知 (默认10条)")
        print("  gk   [n]  信息公开网公告 (默认10条)")
        print("  all  [n]  全部获取")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    if cmd == "news":
        items = get_news(limit)
        print_items("交大新闻网", items)
    elif cmd == "jwc":
        items = get_jwc_notices(limit)
        print_items("教务处通知", items)
    elif cmd == "gk":
        items = get_gk_notices(limit)
        print_items("信息公开网", items)
    elif cmd == "all":
        print_items("交大新闻网", get_news(limit))
        print_items("教务处通知", get_jwc_notices(limit))
        print_items("信息公开网", get_gk_notices(limit))
    else:
        print(f"❌ 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
