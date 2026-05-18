#!/usr/bin/env python3
"""
用 Claude Opus 4.6 蒸馏已爬取的文档为结构化摘要。
- 从 SQLite documents 读取 distilled=0 的记录
- 通过 `claude -p --model claude-opus-4-6 --output-format json` 调用
- 写入 distilled 表

用法:
  python3 sjtu_distill.py run --limit 5
  python3 sjtu_distill.py run --site 教务处通知 --limit 20
  python3 sjtu_distill.py show <doc_id>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sjtu_kb.db"

MODEL = "claude-opus-4-6"

PROMPT_TMPL = """你是交大公告蒸馏器。请把下面一条公告正文提炼成严格的 JSON, 字段:
- category: 类别, 从 {{教学|考试|选课|奖助|活动|讲座|招聘|行政|学籍|其它}} 选一个
- audience: 面向对象, 如 本科生/研究生/全体师生/教师/具体专业
- deadline: 若有明确截止时间, ISO 日期 (YYYY-MM-DD); 无则空串
- action_required: 是否需要收件人采取行动 (true/false)
- summary: 200 字以内中文摘要, 突出 what/when/who/how
- tags: 3-6 个关键词数组

只输出 JSON, 不要多余文字。若内容是导航菜单/空页面, 返回 {{"category":"其它","audience":"","deadline":"","action_required":false,"summary":"SKIP","tags":[]}}。

=== 标题 ===
{title}

=== 来源 ===
{site} ({url})

=== 正文 ===
{content}
"""


def db_connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def call_claude(prompt: str, timeout: int = 180) -> str:
    """Invoke claude CLI, return raw text.

    Prompt 走 stdin 而不是 argv:
      - 避免 ARG_MAX(macOS ~256KB)截断大 prompt 导致静默失败
      - 即使 shell=False 已经隔离 shell 注入,argv 路径仍不适合传 6KB+
        的抓取内容,改 stdin 更稳。
    """
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        print("ERROR: `claude` CLI not found in PATH", file=sys.stderr)
        sys.exit(1)


def extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    # find first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    blob = text[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def distill_one(row: tuple) -> dict | None:
    doc_id, site_name, url, title, content = row
    content = (content or "")[:6000]  # cap input
    prompt = PROMPT_TMPL.format(title=title or "", site=site_name, url=url, content=content)
    raw = call_claude(prompt)
    if not raw:
        return None
    data = extract_json(raw)
    if not data:
        print(f"  [parse-fail] doc {doc_id}: {raw[:120]}", file=sys.stderr)
        return None
    return data


def cmd_run(args):
    conn = db_connect()
    cur = conn.cursor()
    q = "SELECT id, site_name, url, title, content FROM documents WHERE distilled=0"
    params: list = []
    if args.site:
        q += " AND site_name=?"
        params.append(args.site)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    cur.execute(q, params)
    rows = cur.fetchall()
    print(f"Distilling {len(rows)} doc(s) with {MODEL} ...")

    for row in rows:
        doc_id, site_name, url, title, _ = row
        print(f"\n[{doc_id}] {site_name} :: {title[:60]}")
        data = distill_one(row)
        if not data:
            continue
        if data.get("summary") == "SKIP":
            cur.execute("UPDATE documents SET distilled=2 WHERE id=?", (doc_id,))
            conn.commit()
            print("    skipped (empty/nav)")
            continue
        cur.execute(
            """INSERT OR REPLACE INTO distilled
               (doc_id, category, audience, deadline, action_required,
                summary, tags, model, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                doc_id,
                data.get("category", ""),
                data.get("audience", ""),
                data.get("deadline", ""),
                1 if data.get("action_required") else 0,
                data.get("summary", ""),
                json.dumps(data.get("tags", []), ensure_ascii=False),
                MODEL,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        cur.execute("UPDATE documents SET distilled=1 WHERE id=?", (doc_id,))
        conn.commit()
        print(f"    [{data.get('category')}] {data.get('summary','')[:80]}")

    print("\nDone.")


def cmd_show(args):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """SELECT d.site_name, d.title, d.url, d.published_at,
                  x.category, x.audience, x.deadline, x.action_required,
                  x.summary, x.tags
           FROM documents d LEFT JOIN distilled x ON d.id=x.doc_id
           WHERE d.id=?""",
        (args.doc_id,),
    )
    row = cur.fetchone()
    if not row:
        print("not found")
        return
    (site, title, url, pub, cat, aud, dl, act, summ, tags) = row
    print(f"Title   : {title}")
    print(f"Site    : {site}")
    print(f"URL     : {url}")
    print(f"Date    : {pub}")
    print(f"Category: {cat}")
    print(f"Audience: {aud}")
    print(f"Deadline: {dl}")
    print(f"Action  : {bool(act)}")
    print(f"Tags    : {tags}")
    print(f"\nSummary:\n{summ}")


def cmd_list(args):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """SELECT d.id, d.site_name, d.title, x.category, x.deadline, x.summary
           FROM documents d JOIN distilled x ON d.id=x.doc_id
           ORDER BY d.id DESC LIMIT ?""",
        (args.limit,),
    )
    for row in cur.fetchall():
        did, site, title, cat, dl, summ = row
        print(f"[{did}] ({cat}) {site} :: {title[:50]}")
        if dl:
            print(f"     ⏰ {dl}")
        print(f"     {summ[:140]}")
        print()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=5)
    r.add_argument("--site", type=str, default=None)
    s = sub.add_parser("show")
    s.add_argument("doc_id", type=int)
    l = sub.add_parser("list")
    l.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    {"run": cmd_run, "show": cmd_show, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    main()
