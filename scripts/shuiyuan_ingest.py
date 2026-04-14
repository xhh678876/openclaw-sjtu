#!/usr/bin/env python3
"""Ingest scraped Shuiyuan data into a LanceDB vector knowledge base.

Reads JSON files from shuiyuan_scraper.py output, chunks by post,
embeds with BGE-M3, and stores in LanceDB with metadata.

Usage:
    # Full ingest from scraped data
    python shuiyuan_ingest.py --data-dir ./shuiyuan_data --db-path ./shuiyuan_kb

    # Incremental ingest (skip already-ingested topics)
    python shuiyuan_ingest.py --data-dir ./shuiyuan_data --db-path ./shuiyuan_kb --incremental

    # Ingest with reduced embedding dimensions (saves space)
    python shuiyuan_ingest.py --data-dir ./shuiyuan_data --db-path ./shuiyuan_kb --dim 512
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# --- Text cleaning ---

def clean_post_content(raw: str) -> str:
    """Clean a Discourse post's raw markdown content.

    Design: preserve semantically valuable content (code, math, tables,
    link text, @mentions), remove only noise (raw URLs, HTML chrome, uploads).
    Based on cross-model review with Gemini 2.5 Flash.
    """
    text = raw

    # Remove Discourse quote blocks (keep a marker)
    text = re.sub(r'\[quote[^\]]*\].*?\[/quote\]', '[引用]', text, flags=re.DOTALL)

    # Preserve code blocks — replace with tagged markers so they survive cleaning
    code_blocks = []
    def _save_code(m):
        code_blocks.append(m.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"
    text = re.sub(r'```[\s\S]*?```', _save_code, text)  # fenced code blocks
    text = re.sub(r'`[^`]+`', _save_code, text)  # inline code

    # Preserve LaTeX/MathJax formulas
    math_blocks = []
    def _save_math(m):
        math_blocks.append(m.group(0))
        return f"__MATH_BLOCK_{len(math_blocks) - 1}__"
    text = re.sub(r'\$\$[\s\S]*?\$\$', _save_math, text)  # display math
    text = re.sub(r'\$[^\$]+\$', _save_math, text)  # inline math

    # Replace image uploads with placeholder (keep alt text)
    text = re.sub(r'!\[([^\]]*)\]\(upload://[^\)]+\)', lambda m: f'[图片: {m.group(1)}]' if m.group(1) else '[图片]', text)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '[图片]', text)

    # URLs: keep link text, drop raw URLs
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '[链接]', text)

    # Remove HTML tags if any remain (but not code/math placeholders)
    text = re.sub(r'<[^>]+>', '', text)

    # Normalize whitespace (preserve table structure)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    # Restore code blocks and math blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"__CODE_BLOCK_{i}__", block)
    for i, block in enumerate(math_blocks):
        text = text.replace(f"__MATH_BLOCK_{i}__", block)

    # Keep @mentions and #tags — they carry semantic value

    return text.strip()


def chunk_topic_posts(
    topic: dict,
    max_chunk_len: int = 1500,
    cat_map: dict[int, str] | None = None,
) -> list[dict]:
    """Convert a topic's posts into chunks with metadata.

    Each post becomes one chunk. Very long posts are split on paragraph
    boundaries. Topic title + tags are prepended as context. `cat_map` resolves
    category_id -> display name for topics that lack `category_name` (older
    scrapes or subcategories that the flat `_categories.json` missed).
    """
    title = topic.get("title", "")
    cid = topic.get("category_id")
    category = topic.get("category_name") or (cat_map or {}).get(cid, "") if cid else ""
    tags = topic.get("tags", [])
    topic_id = topic.get("id")

    prefix = f"话题: {title}\n"
    if category:
        prefix += f"分类: {category}\n"
    if tags:
        tag_strs = [t if isinstance(t, str) else t.get("name", str(t)) for t in tags]
        prefix += f"标签: {', '.join(tag_strs)}\n"
    prefix += "\n"

    chunks = []
    for post in topic.get("posts", []):
        raw = post.get("raw", "") or post.get("cooked", "")
        if not raw:
            continue

        body = clean_post_content(raw)

        # Quality filter: skip low-value posts
        stripped = body.strip()
        if len(stripped) < 30:  # too short to be useful
            continue
        # Skip pure noise posts (common on Chinese forums)
        noise_patterns = [
            "顶", "同问", "mark", "收藏", "哈哈", "感谢", "谢谢",
            "thanks", "+1", "赞", "好的", "了解", "明白",
            "同意", "是的", "对的", "确实", "厉害", "牛",
        ]
        if stripped in noise_patterns or (len(stripped) < 15 and any(stripped.startswith(p) for p in noise_patterns)):
            continue
        # Skip posts that are just placeholders after cleaning
        if stripped.count("[图片]") + stripped.count("[引用]") + stripped.count("[链接]") >= len(stripped.split()) * 0.8:
            continue

        base_meta = {
            "topic_id": topic_id,
            "topic_title": title,
            "post_id": post.get("id"),
            "post_number": post.get("post_number", 0),
            "username": post.get("username", ""),
            "category": category,
            "category_id": topic.get("category_id") or 0,
            "tags": tags,
            "like_count": post.get("like_count", 0),
            "created_at": post.get("created_at", ""),
            "views": topic.get("views", 0),
            "topic_like_count": topic.get("like_count", 0),
            "url": f"https://shuiyuan.sjtu.edu.cn/t/{topic.get('slug', topic_id)}/{topic_id}/{post.get('post_number', '')}",
        }

        full_text = prefix + body

        if len(full_text) <= max_chunk_len:
            chunks.append({"text": full_text, **base_meta})
        else:
            # Split on paragraph boundaries
            paragraphs = body.split("\n\n")
            current = prefix
            chunk_idx = 0
            for para in paragraphs:
                if len(current) + len(para) + 2 > max_chunk_len and current != prefix:
                    chunks.append({"text": current.strip(), "chunk_idx": chunk_idx, **base_meta})
                    current = prefix
                    chunk_idx += 1
                current += para + "\n\n"
            if current.strip() != prefix.strip():
                chunks.append({"text": current.strip(), "chunk_idx": chunk_idx, **base_meta})

    return chunks


# --- Embedding + DB ---

def load_embedding_model(
    model_name: str = "BAAI/bge-m3",
    use_fp16: bool = True,
    device: str | None = None,
):
    """Load BGE-M3 embedding model.

    device: 'mps' for Apple Silicon GPU, 'cuda' for NVIDIA, None = auto (CPU).
    """
    log.info("Loading embedding model %s (fp16=%s, device=%s)...", model_name, use_fp16, device or "auto")
    from FlagEmbedding import BGEM3FlagModel
    kwargs: dict = {"use_fp16": use_fp16}
    if device:
        kwargs["devices"] = [device]
    model = BGEM3FlagModel(model_name, **kwargs)
    log.info("Model loaded.")
    return model


def create_or_open_db(db_path: str):
    """Create or open LanceDB database."""
    import lancedb
    return lancedb.connect(db_path)


def ingest_chunks(
    db,
    table_name: str,
    chunks: list[dict],
    model,
    batch_size: int = 64,
    dim: int = 1024,
    is_protected: bool = True,
) -> int:
    """Embed and insert chunks into LanceDB."""
    if not chunks:
        return 0

    import numpy as np

    texts = [c["text"] for c in chunks]
    all_vectors = []

    # Batch encode
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        output = model.encode(batch, return_dense=True)
        vecs = output["dense_vecs"]
        # Truncate dimensions if needed
        if dim < vecs.shape[1]:
            vecs = vecs[:, :dim]
        all_vectors.append(vecs)

    vectors = np.concatenate(all_vectors, axis=0)

    # Build records
    records = []
    for i, chunk in enumerate(chunks):
        record = {
            "text": chunk["text"],
            "vector": vectors[i].tolist(),
            "topic_id": chunk.get("topic_id", 0),
            "topic_title": chunk.get("topic_title", ""),
            "post_id": chunk.get("post_id", 0),
            "post_number": chunk.get("post_number", 0),
            "username": chunk.get("username", ""),
            "category": chunk.get("category", ""),
            "category_id": int(chunk.get("category_id") or 0),
            "tags": json.dumps(chunk.get("tags", []), ensure_ascii=False),
            "like_count": chunk.get("like_count", 0),
            "views": chunk.get("views", 0),
            "created_at": chunk.get("created_at", ""),
            "url": chunk.get("url", ""),
            "is_watermarked": is_protected,
        }
        records.append(record)

    # Insert into LanceDB
    try:
        table = db.open_table(table_name)
        table.add(records)
    except Exception:
        table = db.create_table(table_name, records)

    return len(records)


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Shuiyuan data into LanceDB RAG")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./shuiyuan_data"),
        help="Directory with scraped topic JSON files",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./shuiyuan_kb",
        help="LanceDB database path",
    )
    parser.add_argument("--table-name", default="posts", help="LanceDB table name")
    parser.add_argument("--model", default="BAAI/bge-m3", help="Embedding model name")
    parser.add_argument("--dim", type=int, default=1024, help="Embedding dimension (1024/768/512)")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    parser.add_argument("--max-chunk-len", type=int, default=1500, help="Max characters per chunk")
    parser.add_argument("--incremental", action="store_true", help="Skip already-ingested topics")
    parser.add_argument("--no-fp16", action="store_true", help="Disable FP16 (use FP32)")
    parser.add_argument("--device", default=None, help="Device: mps (Apple GPU), cuda, or omit for CPU")

    parser.add_argument(
        "--whitelist",
        type=Path,
        default=Path(__file__).parent / "shuiyuan_public_whitelist.json",
        help="JSON file listing topic_ids/category_ids that may enter the public 'posts' table",
    )

    args = parser.parse_args()

    # Policy B (default-protect): everything is protected unless explicitly whitelisted.
    allowed_topic_ids: set[int] = set()
    allowed_category_ids: set[int] = set()
    if args.whitelist.exists():
        try:
            wl = json.loads(args.whitelist.read_text())
            allowed_topic_ids = set(wl.get("allowed_topic_ids") or [])
            allowed_category_ids = set(wl.get("allowed_category_ids") or [])
            log.info(
                "Whitelist loaded: %d topics, %d categories allowed public",
                len(allowed_topic_ids), len(allowed_category_ids),
            )
        except Exception as exc:
            log.warning("Failed to parse whitelist %s: %s", args.whitelist, exc)
    else:
        log.info("No whitelist file — all content routed to protected table")

    # Category id -> name map (for chunks that lack category_name)
    cat_file = args.data_dir / "_categories.json"
    cat_map: dict[int, str] = {}
    if cat_file.exists():
        try:
            raw = json.loads(cat_file.read_text())
            cat_map = {int(k): v for k, v in raw.items()}
        except Exception as exc:
            log.warning("Failed to parse %s: %s", cat_file, exc)

    topics_dir = args.data_dir / "topics"
    if not topics_dir.exists():
        log.error("Topics directory not found: %s", topics_dir)
        log.error("Run shuiyuan_scraper.py first to collect data.")
        sys.exit(1)

    topic_files = sorted(topics_dir.glob("*.json"))
    log.info("Found %d topic files in %s", len(topic_files), topics_dir)

    if not topic_files:
        log.error("No topic files found. Run scraper first.")
        sys.exit(1)

    # Load model
    model = load_embedding_model(args.model, use_fp16=not args.no_fp16, device=args.device)

    # Open DB
    db = create_or_open_db(args.db_path)

    # Track ingested topics for incremental mode — union of public + protected
    ingested_topics: dict[int, int] = {}  # topic_id -> chunk_count
    _public_table_ref = None
    _protected_table_ref = None
    if args.incremental:
        for tname, is_protected in (
            (args.table_name, False),
            (args.table_name + "_protected", True),
        ):
            try:
                tref = db.open_table(tname)
                df = tref.to_pandas()
                counts = df.groupby("topic_id").size().to_dict()
                for tid, n in counts.items():
                    ingested_topics[int(tid)] = ingested_topics.get(int(tid), 0) + int(n)
                if is_protected:
                    _protected_table_ref = tref
                else:
                    _public_table_ref = tref
                log.info("Incremental: %s has %d topics", tname, len(counts))
            except Exception:
                log.info("Incremental: table %s not present (skipped)", tname)
        log.info("Incremental mode: %d topics already ingested across both tables", len(ingested_topics))

    # Load scrape state to detect updated topics
    scrape_state_file = args.data_dir / "_scrape_state.json"
    updated_topic_ids: set[int] = set()
    if scrape_state_file.exists():
        try:
            ss = json.loads(scrape_state_file.read_text())
            if ss.get("stats", {}).get("topics_updated", 0) > 0:
                log.info("Detected updated topics in scrape state")
        except Exception:
            pass

    # Process topics
    total_chunks = 0
    start_time = time.monotonic()

    for i, topic_file in enumerate(topic_files):
        topic_id = int(topic_file.stem)

        if args.incremental and topic_id in ingested_topics:
            # Check if topic file is newer than what we have
            # (re-scraped topics get a fresh scraped_at timestamp)
            try:
                topic_data = json.loads(topic_file.read_text())
                post_count = len(topic_data.get("posts", []))
                old_chunk_count = ingested_topics.get(topic_id, 0)
                # Simple heuristic: if post count changed, re-ingest
                if post_count <= old_chunk_count:
                    continue
                # Delete old entries for this topic before re-ingesting (both tables)
                log.info("Topic %d updated (%d -> %d posts), re-ingesting...", topic_id, old_chunk_count, post_count)
                for tref in (_public_table_ref, _protected_table_ref):
                    if tref is not None:
                        try:
                            tref.delete(f"topic_id = {topic_id}")
                        except Exception:
                            pass
            except Exception:
                continue

        try:
            topic = json.loads(topic_file.read_text())
        except json.JSONDecodeError as exc:
            log.warning("Invalid JSON in %s: %s", topic_file, exc)
            continue

        chunks = chunk_topic_posts(topic, max_chunk_len=args.max_chunk_len, cat_map=cat_map)
        if not chunks:
            continue

        # Policy B: default-protect. Public only if explicitly whitelisted.
        topic_cid = topic.get("category_id")
        is_public = (
            topic_id in allowed_topic_ids
            or (topic_cid is not None and topic_cid in allowed_category_ids)
        )
        is_protected = not is_public
        target_table = args.table_name + "_protected" if is_protected else args.table_name

        n = ingest_chunks(
            db, target_table, chunks, model, args.batch_size, args.dim,
            is_protected=is_protected,
        )
        total_chunks += n

        if (i + 1) % 100 == 0:
            elapsed = time.monotonic() - start_time
            rate = total_chunks / elapsed if elapsed > 0 else 0
            log.info(
                "[%d/%d] %d chunks ingested (%.1f chunks/s)",
                i + 1, len(topic_files), total_chunks, rate,
            )

    elapsed = time.monotonic() - start_time
    log.info(
        "Ingestion complete: %d chunks from %d files in %.1fs",
        total_chunks, len(topic_files), elapsed,
    )

    # Create FTS index on both public and protected tables
    for tname in (args.table_name, args.table_name + "_protected"):
        try:
            table = db.open_table(tname)
            table.create_fts_index("text", replace=True)
            log.info("FTS index created on %s", tname)
        except Exception as exc:
            log.warning("FTS index on %s skipped: %s", tname, exc)


if __name__ == "__main__":
    main()
