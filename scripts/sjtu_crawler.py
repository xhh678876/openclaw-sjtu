#!/usr/bin/env python3
"""
SJTU 全站统一爬虫 (Layers 1-3)
- 读取 data/sjtu_sites.yaml
- 抓取列表页 → 解析条目 → 抓取详情页正文
- 入库 SQLite: data/sjtu_kb.db
- 原始 HTML 归档: data/raw/<domain>/<hash>.html
- 增量: url + content_hash 去重

用法:
  python3 sjtu_crawler.py list                   # 列出所有站点
  python3 sjtu_crawler.py crawl --priority 1     # 只爬 priority<=1
  python3 sjtu_crawler.py crawl --site 教务处通知 # 只爬某站
  python3 sjtu_crawler.py crawl --limit 5        # 每站最多 5 条
  python3 sjtu_crawler.py stats                  # 统计
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SITES_YAML = ROOT / "data" / "sjtu_sites.yaml"
DB_PATH = ROOT / "data" / "sjtu_kb.db"
RAW_DIR = ROOT / "data" / "raw"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 12
REQ_GAP = 0.6  # seconds between requests


# ============================================================
# Storage
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT NOT NULL,
    site_type TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    published_at TEXT,
    crawled_at TEXT NOT NULL,
    content TEXT,
    content_hash TEXT,
    raw_path TEXT,
    distilled INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_docs_site ON documents(site_name);
CREATE INDEX IF NOT EXISTS idx_docs_distilled ON documents(distilled);

CREATE TABLE IF NOT EXISTS distilled (
    doc_id INTEGER PRIMARY KEY,
    category TEXT,
    audience TEXT,
    deadline TEXT,
    action_required TEXT,
    summary TEXT,
    tags TEXT,
    model TEXT,
    created_at TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);
"""


@contextmanager
def db_connect() -> Iterator[sqlite3.Connection]:
    """SQLite 连接 context manager,确保 conn.close() 总被调用。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# Site loading
# ============================================================

@dataclass
class Site:
    name: str
    type: str
    list_url: str
    base_url: str
    priority: int = 3
    item_selector: str = ""
    title_selector: str = "a"
    link_selector: str = "a"
    date_selector: str = ""
    detail_selector: str = ""
    encoding: str = "utf-8"


def load_sites() -> list[Site]:
    with open(SITES_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    defaults = cfg.get("defaults", {})
    sites = []
    for s in cfg["sites"]:
        merged = {**defaults, **s}
        sites.append(Site(
            name=merged["name"],
            type=merged["type"],
            list_url=merged["list_url"],
            base_url=merged["base_url"],
            priority=merged.get("priority", 3),
            item_selector=merged.get("item_selector", ""),
            title_selector=merged.get("title_selector", "a"),
            link_selector=merged.get("link_selector", "a"),
            date_selector=merged.get("date_selector", ""),
            detail_selector=merged.get("detail_selector", ""),
            encoding=merged.get("encoding", "utf-8"),
        ))
    return sites


# ============================================================
# Fetching
# ============================================================

def fetch(url: str, encoding: str = "utf-8") -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=True)
        r.encoding = encoding if encoding else r.apparent_encoding
        if r.status_code != 200:
            return None
        return r.text
    except requests.RequestException as e:
        print(f"  [fetch-err] {url}: {e}", file=sys.stderr)
        return None


DATE_RE = re.compile(r"(20\d{2})[-./年]?\s*(\d{1,2})[-./月]?\s*(\d{1,2})?")


def _extract_date(text: str) -> str:
    m = DATE_RE.search(text)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3) or "01"
    try:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    except ValueError:
        return ""


def parse_list(html: str, site: Site) -> list[dict]:
    """Extract {title, url, date} items. Filter out navigation (must have date OR link contains /info/)."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen = set()

    # Candidate list items: prefer li elements; also try article/div patterns
    nodes = soup.select("li.clearfix, li.wp_article_list, ul.wp_article_list li, li")
    if not nodes:
        nodes = soup.find_all(["article", "div"])

    for node in nodes:
        anchors = node.find_all("a", href=True)
        if not anchors:
            continue
        # Pick the anchor that looks like content (has title attr or longest text)
        a = None
        for cand in anchors:
            href = cand["href"].strip()
            if not href or href.startswith(("#", "javascript")):
                continue
            if cand.get("title") or len(cand.get_text(strip=True)) >= 8:
                a = cand
                break
        if a is None:
            a = anchors[0]
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript")):
            continue
        if not re.search(r"/info/\d|/\d{4,}/|/content_|/detail|/show|/tzgg/\d", href) and "htm" not in href.lower():
            continue
        url = urljoin(site.list_url, href)
        if url in seen:
            continue

        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        # Strip leading dates / day numbers like "10 2026-04 " or "2026-04-10 "
        title = re.sub(r"^\s*\d{1,2}\s+20\d{2}[-./]\d{1,2}\s*", "", title)
        title = re.sub(r"^\s*20\d{2}[-./]\d{1,2}[-./]\d{1,2}\s*", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 6:
            continue
        # Require at least 2 CJK chars to filter out timeline/nav labels
        if len(re.findall(r"[\u4e00-\u9fff]", title)) < 2:
            continue
        # Skip obvious navigation text
        if title in {"首页", "下一页", "上一页", "更多", "返回"}:
            continue

        date_str = _extract_date(node.get_text(" ", strip=True))
        # Require date OR info-style URL to avoid sidebar nav
        if not date_str and "/info/" not in href:
            continue

        seen.add(url)
        items.append({"title": title[:300], "url": url, "date": date_str})

    return items


def parse_detail(html: str, site: Site) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in site.detail_selector.split(","):
        sel = sel.strip()
        if not sel:
            continue
        node = soup.select_one(sel)
        if node:
            text = node.get_text("\n", strip=True)
            if len(text) > 80:
                return text
    # fallback: largest <div> by text len
    candidates = [d for d in soup.find_all(["div", "article"]) if d.get_text(strip=True)]
    if candidates:
        best = max(candidates, key=lambda d: len(d.get_text(strip=True)))
        return best.get_text("\n", strip=True)
    return soup.get_text("\n", strip=True)


# ============================================================
# Crawl
# ============================================================

def archive_raw(url: str, html: str) -> str:
    """归档抓到的原始 HTML。

    chmod 0o600 —— scraped 内容可能含校内门户上的个人信息(姓名/邮件等),
    不应让同机器其它用户读到。
    """
    domain = urlparse(url).netloc
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    p = RAW_DIR / domain / f"{h}.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return str(p.relative_to(ROOT))


def crawl_site(site: Site, limit: int, conn: sqlite3.Connection) -> tuple[int, int]:
    """Returns (found, new)."""
    print(f"\n[*] {site.name} ({site.type}) → {site.list_url}")
    html = fetch(site.list_url, site.encoding)
    if not html:
        print("    list fetch failed")
        return 0, 0
    items = parse_list(html, site)
    print(f"    found {len(items)} items")
    new_count = 0
    cur = conn.cursor()
    for it in items[:limit]:
        cur.execute("SELECT 1 FROM documents WHERE url=?", (it["url"],))
        if cur.fetchone():
            continue
        time.sleep(REQ_GAP)
        detail_html = fetch(it["url"], site.encoding)
        if not detail_html:
            continue
        content = parse_detail(detail_html, site)
        if len(content) < 40:
            continue
        content_hash = hashlib.sha1(content.encode()).hexdigest()
        # 二级去重:相同 content_hash 出现在不同 URL(canonical 漂移、镜像站)
        cur.execute(
            "SELECT 1 FROM documents WHERE content_hash=? LIMIT 1",
            (content_hash,),
        )
        if cur.fetchone():
            continue
        raw_path = archive_raw(it["url"], detail_html)
        cur.execute(
            """INSERT OR IGNORE INTO documents
               (site_name, site_type, url, title, published_at, crawled_at,
                content, content_hash, raw_path)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (site.name, site.type, it["url"], it["title"], it["date"],
             datetime.now().isoformat(timespec="seconds"), content,
             content_hash, raw_path),
        )
        if cur.rowcount:
            new_count += 1
            print(f"    + {it['title'][:50]}")
    conn.commit()
    print(f"    new: {new_count}")
    return len(items), new_count


# ============================================================
# CLI
# ============================================================

def cmd_list() -> None:
    for s in load_sites():
        print(f"  [{s.priority}] {s.type:10s}  {s.name:30s}  {s.list_url}")


def cmd_crawl(args) -> None:
    sites = load_sites()
    if args.site:
        sites = [s for s in sites if s.name == args.site]
    sites = [s for s in sites if s.priority <= args.priority]
    print(f"Crawling {len(sites)} site(s), limit={args.limit}/site")
    total_new = 0
    with db_connect() as conn:
        for s in sites:
            try:
                _, new = crawl_site(s, args.limit, conn)
                total_new += new
            except Exception as e:
                print(f"    [err] {e}", file=sys.stderr)
    print(f"\nTotal new documents: {total_new}")


def cmd_stats() -> None:
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT site_name, COUNT(*), SUM(distilled) "
            "FROM documents GROUP BY site_name"
        )
        rows = cur.fetchall()
    total = 0
    total_d = 0
    for name, cnt, dcnt in rows:
        dcnt = dcnt or 0
        print(f"  {name:30s}  {cnt:5d} docs  ({dcnt} distilled)")
        total += cnt
        total_d += dcnt
    print(f"  {'TOTAL':30s}  {total:5d} docs  ({total_d} distilled)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("crawl")
    c.add_argument("--priority", type=int, default=3)
    c.add_argument("--site", type=str, default=None)
    c.add_argument("--limit", type=int, default=10)
    sub.add_parser("stats")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "crawl":
        cmd_crawl(args)
    elif args.cmd == "stats":
        cmd_stats()


if __name__ == "__main__":
    main()
