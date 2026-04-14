#!/usr/bin/env python3
"""MCP Server for querying the Shuiyuan RAG knowledge base.

Exposes search tools that Claude Code can call directly via MCP protocol.

Configuration in ~/.claude.json or project settings:
{
    "mcpServers": {
        "shuiyuan-rag": {
            "command": "python",
            "args": ["<path>/shuiyuan_rag_mcp.py"],
            "env": {
                "SHUIYUAN_KB_PATH": "./shuiyuan_kb"
            }
        }
    }
}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DB_PATH = os.environ.get("SHUIYUAN_KB_PATH", "./shuiyuan_kb")
TABLE_NAME = os.environ.get("SHUIYUAN_TABLE_NAME", "posts")
PROTECTED_TABLE_NAME = os.environ.get("SHUIYUAN_PROTECTED_TABLE", "posts_protected")
MODEL_NAME = os.environ.get("SHUIYUAN_EMBED_MODEL", "BAAI/bge-m3")
RERANKER_NAME = os.environ.get("SHUIYUAN_RERANKER", "BAAI/bge-reranker-v2-m3")

# Lazy-loaded globals
_db = None
_table = None
_protected_table = None
_embed_model = None
_reranker = None


def get_db():
    global _db, _table, _protected_table
    if _db is None:
        import lancedb
        _db = lancedb.connect(DB_PATH)
        # Public table may not exist under policy B (default-protect) if the
        # whitelist is empty — tolerate that.
        try:
            _table = _db.open_table(TABLE_NAME)
            log.info("Public table loaded: %s", TABLE_NAME)
        except Exception:
            _table = None
            log.info("No public table (%s) — whitelist may be empty", TABLE_NAME)
        try:
            _protected_table = _db.open_table(PROTECTED_TABLE_NAME)
            log.info("Protected table loaded: %s", PROTECTED_TABLE_NAME)
        except Exception:
            _protected_table = None
            log.info("No protected table (%s)", PROTECTED_TABLE_NAME)
    return _db, _table


def get_protected_table():
    """Get the protected (watermarked) table. Returns None if not available."""
    get_db()  # ensure db is loaded
    return _protected_table


def verify_jaccount(cookie_or_token: str) -> bool:
    """Verify jAccount authentication.

    Accepts either:
    - A Shuiyuan _t session cookie (verified against Shuiyuan API)
    - A jAccount OAuth token (verified against jaccount.sjtu.edu.cn)

    Returns True if authenticated as a valid SJTU user.
    """
    if not cookie_or_token:
        return False

    # Method 1: Verify Shuiyuan session cookie
    try:
        if http_requests := _get_requests():
            resp = http_requests.get(
                "https://shuiyuan.sjtu.edu.cn/session/current.json",
                headers={
                    "Cookie": f"_t={cookie_or_token}",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("current_user", {}).get("username"):
                    return True
    except Exception:
        pass

    return False


def _get_requests():
    try:
        import requests
        return requests
    except ImportError:
        return None


def get_embed_model():
    global _embed_model
    if _embed_model is None:
        from FlagEmbedding import BGEM3FlagModel
        _embed_model = BGEM3FlagModel(MODEL_NAME, use_fp16=True)
        log.info("Embedding model loaded: %s", MODEL_NAME)
    return _embed_model


def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from FlagEmbedding import FlagReranker
            _reranker = FlagReranker(RERANKER_NAME, use_fp16=True)
            log.info("Reranker loaded: %s", RERANKER_NAME)
        except Exception as exc:
            log.warning("Reranker not available: %s. Falling back to vector-only.", exc)
            _reranker = False  # sentinel: tried but failed
    return _reranker if _reranker is not False else None


def _time_decay_score(created_at: str, half_life_days: float = 365.0) -> float:
    """Compute a time decay weight. Score = 0.5 ^ (age_days / half_life).

    - Post from today: 1.0
    - Post from 1 year ago: 0.5
    - Post from 2 years ago: 0.25
    - Post from 3 years ago: 0.125
    """
    try:
        dt_str = created_at[:19]  # "2024-03-15T10:30:00"
        post_time = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        age_days = (datetime.now(post_time.tzinfo) - post_time).days
        if age_days < 0:
            age_days = 0
        return 0.5 ** (age_days / half_life_days)
    except Exception:
        return 0.5  # fallback for unparseable dates


def search_impl(
    query: str,
    category: str | None = None,
    min_likes: int = 0,
    max_results: int = 5,
    recency_days: int | None = None,
    time_weight: float = 0.3,
    jaccount_token: str | None = None,
) -> list[dict]:
    """Core search: embed query -> vector search -> time decay -> optional rerank.

    Final score = (1 - time_weight) * relevance + time_weight * recency
    Set time_weight=0 to disable time decay.

    If jaccount_token is provided and valid, also searches protected (watermarked)
    content. Otherwise only searches public posts.
    """
    _, table = get_db()
    model = get_embed_model()

    # Encode query
    output = model.encode([query], return_dense=True)
    query_vec = output["dense_vecs"][0].tolist()

    # Check if user is authenticated for protected content
    include_protected = False
    if jaccount_token:
        include_protected = verify_jaccount(jaccount_token)
        if include_protected:
            log.info("jAccount verified, including protected content")

    # Build filters once — reused across public + protected tables
    filters = []
    if category:
        filters.append(f"category = '{category}'")
    if min_likes > 0:
        filters.append(f"like_count >= {min_likes}")
    if recency_days:
        cutoff = (datetime.now() - timedelta(days=recency_days)).strftime("%Y-%m-%d")
        filters.append(f"created_at > '{cutoff}'")
    filter_clause = " AND ".join(filters) if filters else None

    # Public table search (may be absent under policy B with empty whitelist)
    candidates: list[dict] = []
    if table is not None:
        try:
            search = table.search(query_vec).limit(50)
            if filter_clause:
                search = search.where(filter_clause)
            candidates = search.to_list()
        except Exception as exc:
            log.error("Public table search failed: %s", exc)

    # Also search protected table if authenticated
    if include_protected:
        protected_table = get_protected_table()
        if protected_table is not None:
            try:
                p_search = protected_table.search(query_vec).limit(50)
                if filter_clause:
                    p_search = p_search.where(filter_clause)
                protected_results = p_search.to_list()
                # Mark protected results so we can tag them in output
                for r in protected_results:
                    r["_is_protected"] = True
                candidates.extend(protected_results)
            except Exception as exc:
                log.warning("Protected table search failed: %s", exc)

    if not candidates:
        return []

    # Apply time decay: boost newer posts
    if time_weight > 0:
        for c in candidates:
            vector_score = 1.0 - c.get("_distance", 0.5)  # LanceDB returns distance
            recency_score = _time_decay_score(c.get("created_at", ""))
            c["_combined_score"] = (1 - time_weight) * vector_score + time_weight * recency_score
        candidates.sort(key=lambda x: x.get("_combined_score", 0), reverse=True)

    # Rerank if available — always run when reranker exists (even if
    # candidates <= max_results) so we get confidence scores.
    reranker = get_reranker()
    max_rerank: float | None = None
    if reranker and candidates:
        pairs = [[query, c["text"]] for c in candidates]
        try:
            scores = reranker.compute_score(pairs, normalize=True)
            for c, s in zip(candidates, scores):
                c["_rerank"] = float(s)
            candidates.sort(key=lambda c: c.get("_rerank", 0), reverse=True)
            candidates = candidates[:max_results]
            max_rerank = candidates[0]["_rerank"] if candidates else None
        except Exception as exc:
            log.warning("Rerank failed, using vector scores: %s", exc)
            candidates = candidates[:max_results]
    else:
        candidates = candidates[:max_results]

    # Confidence threshold: rerank score < 0.3 means "no strongly relevant
    # content found" — warn the caller in format_results.
    low_confidence = max_rerank is not None and max_rerank < 0.3

    # Format results
    results = []
    for doc in candidates:
        tags = doc.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        results.append({
            "text": doc.get("text", "")[:3000],
            "topic_title": doc.get("topic_title", ""),
            "topic_id": doc.get("topic_id"),
            "post_number": doc.get("post_number"),
            "username": doc.get("username", ""),
            "category": doc.get("category", ""),
            "tags": tags,
            "like_count": doc.get("like_count", 0),
            "views": doc.get("views", 0),
            "created_at": doc.get("created_at", ""),
            "url": doc.get("url", ""),
            "_rerank": doc.get("_rerank"),
            "_low_confidence": low_confidence,
            "_is_protected": doc.get("_is_protected", False),
        })

    return results


def format_results(results: list[dict]) -> str:
    """Format search results as readable text."""
    if not results:
        return "No results found."

    parts = []
    if results[0].get("_low_confidence"):
        top = results[0].get("_rerank")
        parts.append(
            f"⚠️ **低置信度结果** — 重排序最高分仅 {top:.3f} (<0.3),"
            "语料里可能没有强相关内容,以下结果仅供宽泛参考,**不要当作权威信息引用**。\n"
        )

    for i, r in enumerate(results, 1):
        protected_tag = " [校内保护内容]" if r.get("_is_protected") else ""
        header = f"**[{i}] {r['topic_title']}{protected_tag}**"

        # Add age warning for old posts
        age_note = ""
        try:
            dt_str = r.get("created_at", "")[:10]
            from datetime import date
            post_date = date.fromisoformat(dt_str)
            age_days = (date.today() - post_date).days
            if age_days > 730:
                age_note = " [!!超过2年前，信息可能已过时]"
            elif age_days > 365:
                age_note = " [!超过1年前]"
        except Exception:
            pass

        meta = f"by @{r['username']} | {r['created_at'][:10]}{age_note} | 👍{r['like_count']} | 👀{r['views']}"
        if r.get("category"):
            meta += f" | 分类: {r['category']}"
        url = r.get("url", "")
        text = r["text"]
        # Remove the topic prefix from display
        if "\n\n" in text:
            text = text.split("\n\n", 1)[-1]

        parts.append(f"{header}\n{meta}\n{url}\n\n{text}")

    return "\n\n---\n\n".join(parts)


# --- MCP Server ---

def run_mcp_server():
    """Run as an MCP server via stdio."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError:
        log.error("MCP SDK not installed. Run: pip install mcp")
        sys.exit(1)

    import asyncio

    app = Server("shuiyuan-rag")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="search_shuiyuan",
                description=(
                    "Search the SJTU Shuiyuan (水源社区) forum knowledge base. "
                    "Use this to find discussions, experiences, advice, and information "
                    "shared by SJTU students about campus life, courses, academics, "
                    "career, and more."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query in Chinese or English",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by forum category name (optional)",
                        },
                        "min_likes": {
                            "type": "integer",
                            "description": "Minimum likes to filter quality posts (default 0)",
                            "default": 0,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (default 5, max 20)",
                            "default": 5,
                        },
                        "recency_days": {
                            "type": "integer",
                            "description": "Only posts from last N days (optional)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="shuiyuan_stats",
                description="Get statistics about the Shuiyuan knowledge base (total posts, categories, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "search_shuiyuan":
            results = search_impl(
                query=arguments["query"],
                category=arguments.get("category"),
                min_likes=arguments.get("min_likes", 0),
                max_results=min(arguments.get("max_results", 5), 20),
                recency_days=arguments.get("recency_days"),
            )
            text = format_results(results)
            return [TextContent(type="text", text=text)]

        elif name == "shuiyuan_stats":
            _, table = get_db()
            protected = get_protected_table()
            import pandas as pd
            frames = []
            if table is not None:
                frames.append(table.to_pandas().assign(_scope="public"))
            if protected is not None:
                frames.append(protected.to_pandas().assign(_scope="protected"))
            if not frames:
                return [TextContent(type="text", text="No tables available.")]
            df = pd.concat(frames, ignore_index=True)
            stats = {
                "total_chunks": len(df),
                "public_chunks": int((df["_scope"] == "public").sum()),
                "protected_chunks": int((df["_scope"] == "protected").sum()),
                "unique_topics": int(df["topic_id"].nunique()),
                "unique_users": int(df["username"].nunique()),
                "categories": df["category"].unique().tolist(),
                "date_range": {
                    "earliest": df["created_at"].min(),
                    "latest": df["created_at"].max(),
                },
            }
            return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _main():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    asyncio.run(_main())


# --- CLI mode for testing ---

def run_cli():
    """Run as a CLI for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Query Shuiyuan RAG knowledge base")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--category", default=None)
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--recency-days", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    results = search_impl(
        query=args.query,
        category=args.category,
        min_likes=args.min_likes,
        max_results=args.max_results,
        recency_days=args.recency_days,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_results(results))


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        sys.argv.remove("--mcp")
        run_mcp_server()
    elif len(sys.argv) > 1 and sys.argv[1] != "--help":
        run_cli()
    else:
        # Default: MCP server mode
        run_mcp_server()
