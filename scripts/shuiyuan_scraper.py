#!/usr/bin/env python3
"""Bulk scraper for Shuiyuan Discourse forum.

Reuses the existing auth infrastructure from shuiyuan_discourse.py.
Saves raw JSON data per-topic for downstream ingestion.

Usage:
    # Scrape all categories, save to ./shuiyuan_data/
    python shuiyuan_scraper.py --output-dir ./shuiyuan_data

    # Scrape specific category
    python shuiyuan_scraper.py --output-dir ./shuiyuan_data --category-id 5

    # Resume interrupted scrape
    python shuiyuan_scraper.py --output-dir ./shuiyuan_data --resume

    # Scrape only topics with 5+ likes
    python shuiyuan_scraper.py --output-dir ./shuiyuan_data --min-likes 5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import requests as http_requests
except ImportError:
    http_requests = None

from shuiyuan_discourse import (
    DEFAULT_AUTH_PATH,
    DEFAULT_SITE,
    Credential,
    HttpRequestError,
    RequestResult,
    request_json,
    resolve_credential,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# --- Rate limiter ---

class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, requests_per_minute: float = 18.0):
        self.interval = 60.0 / requests_per_minute
        self.last_request = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_request = time.monotonic()


# --- API helpers ---

def api_get(
    cred: Credential,
    path: str,
    params: Optional[dict[str, Any]] = None,
    limiter: Optional[RateLimiter] = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    cookie: Optional[str] = None,
) -> dict[str, Any]:
    """GET request with rate limiting and retry on 429.

    If cookie is provided, uses session cookie auth (faster, no daily cap).
    Otherwise falls back to User API Key auth.
    """
    for attempt in range(max_retries):
        if limiter:
            limiter.wait()
        try:
            if cookie:
                # Cookie-based auth: bypass User API Key limits
                return _cookie_get(cred.site, path, params, cookie, timeout)
            result = request_json(
                site=cred.site,
                path=path,
                params=params,
                cred=cred,
                runtime="auto",
                timeout=timeout,
            )
            return result.data if isinstance(result.data, dict) else {}
        except HttpRequestError as exc:
            if exc.status == 429 and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                log.warning("Rate limited (429), waiting %ds before retry...", wait)
                time.sleep(wait)
                continue
            raise
    return {}


def _cookie_get(
    site: str,
    path: str,
    params: Optional[dict[str, Any]],
    cookie: str,
    timeout: float,
) -> dict[str, Any]:
    """GET request using session cookie auth (IP rate limit only: ~200 req/min)."""
    import urllib.parse
    url = f"{site.rstrip('/')}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    headers = {
        "Accept": "application/json",
        "Cookie": f"_t={cookie}" if not cookie.startswith("_t=") else cookie,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) OpenClaw-Scraper/1.0",
    }

    if http_requests:
        resp = http_requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            raise HttpRequestError(status=429, body=resp.text, url=url, runtime="cookie")
        if resp.status_code >= 400:
            raise HttpRequestError(status=resp.status_code, body=resp.text, url=url, runtime="cookie")
        return resp.json()
    else:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json as _json
            return _json.loads(resp.read().decode("utf-8"))


def fetch_categories(cred: Credential, limiter: RateLimiter, cookie: Optional[str] = None) -> list[dict]:
    """Fetch all categories, flattened to include subcategories.

    Discourse nests subcategories under each top-level category's
    `subcategory_list`. We walk the tree so the returned list includes every
    category id the API exposes (otherwise `_categories.json` only captures the
    ~13 top-level names and all real topics live in unmapped subcategories).
    """
    data = api_get(cred, "/categories.json", {"include_subcategories": "true"}, limiter, cookie=cookie)
    cat_list = data.get("category_list", {})
    top_level = cat_list.get("categories", [])

    flat: list[dict] = []
    def _walk(cats: list[dict]) -> None:
        for c in cats:
            flat.append(c)
            subs = c.get("subcategory_list") or []
            if subs:
                _walk(subs)
    _walk(top_level)
    return flat


def fetch_category_topics(
    cred: Credential,
    category_slug: str,
    category_id: int,
    limiter: RateLimiter,
    min_likes: int = 0,
    max_pages: int = 500,
    cookie: Optional[str] = None,
) -> list[dict]:
    """Fetch all topic stubs from a category (paginated)."""
    topics = []
    for page in range(max_pages):
        data = api_get(
            cred,
            f"/c/{category_slug}/{category_id}/l/latest.json",
            {"page": page},
            limiter,
            cookie=cookie,
        )
        topic_list = data.get("topic_list", {})
        page_topics = topic_list.get("topics", [])

        for t in page_topics:
            if min_likes > 0 and (t.get("like_count", 0) or 0) < min_likes:
                continue
            topics.append(t)

        if not topic_list.get("more_topics_url") or len(page_topics) < 30:
            break

        log.info(
            "  Category %s page %d: %d topics so far",
            category_slug, page, len(topics),
        )

    return topics


def fetch_topic_full(
    cred: Credential,
    topic_id: int,
    limiter: RateLimiter,
    max_posts: int = 2000,
    cookie: Optional[str] = None,
) -> Optional[dict]:
    """Fetch a full topic with all posts."""
    # First request: get topic meta + post stream IDs + first chunk of posts
    data = api_get(
        cred,
        f"/t/{topic_id}.json",
        {"include_raw": "true"},
        limiter,
        timeout=30.0,
        cookie=cookie,
    )

    if not data or "post_stream" not in data:
        return None

    post_stream = data.get("post_stream", {})
    all_post_ids = post_stream.get("stream", [])
    fetched_posts = post_stream.get("posts", [])
    fetched_ids = {p["id"] for p in fetched_posts if "id" in p}

    # Fetch remaining posts in batches of 20
    remaining_ids = [pid for pid in all_post_ids if pid not in fetched_ids]
    remaining_ids = remaining_ids[:max_posts - len(fetched_posts)]

    batch_size = 20
    for i in range(0, len(remaining_ids), batch_size):
        batch = remaining_ids[i : i + batch_size]
        params = {f"post_ids[]": batch}
        try:
            batch_data = api_get(
                cred,
                f"/t/{topic_id}/posts.json",
                params,
                limiter,
                cookie=cookie,
            )
            batch_posts = batch_data.get("post_stream", {}).get("posts", [])
            fetched_posts.extend(batch_posts)
        except HttpRequestError as exc:
            log.warning("Failed to fetch post batch for topic %d: %s", topic_id, exc.status)
            break

    # Sort posts by post_number
    fetched_posts.sort(key=lambda p: p.get("post_number", 0))

    # NOTE: Shuiyuan's watermark is rendered client-side via CSS — it does NOT
    # appear in the API's cooked HTML. `is_warning` / `read_restricted` are also
    # absent from the compact API response. So this flag is best-effort only:
    # real public/protected routing happens at ingest time against
    # scripts/shuiyuan_public_whitelist.json (policy B — default-protect).
    is_watermarked = False
    for p in fetched_posts:
        cooked = p.get("cooked", "")
        if "watermark" in cooked.lower() or "data-watermark" in cooked:
            is_watermarked = True
            break
    if data.get("is_warning") or data.get("read_restricted"):
        is_watermarked = True

    # Build clean output
    return {
        "id": data.get("id", topic_id),
        "title": data.get("title", ""),
        "slug": data.get("slug", ""),
        "category_id": data.get("category_id"),
        "tags": data.get("tags", []),
        "views": data.get("views", 0),
        "like_count": data.get("like_count", 0),
        "posts_count": data.get("posts_count", 0),
        "reply_count": data.get("reply_count", 0),
        "created_at": data.get("created_at", ""),
        "last_posted_at": data.get("last_posted_at", ""),
        "pinned": data.get("pinned", False),
        "closed": data.get("closed", False),
        "archived": data.get("archived", False),
        "is_watermarked": is_watermarked,
        "posts": [
            {
                "id": p.get("id"),
                "post_number": p.get("post_number"),
                "username": p.get("username", ""),
                "created_at": p.get("created_at", ""),
                "raw": p.get("raw", ""),
                "cooked": p.get("cooked", ""),
                "like_count": sum(
                    a.get("count", 0)
                    for a in (p.get("actions_summary") or [])
                    if a.get("id") == 2
                ),
                "reply_to_post_number": p.get("reply_to_post_number"),
                "post_type": p.get("post_type", 1),
            }
            for p in fetched_posts
            if isinstance(p, dict) and p.get("post_type", 1) == 1  # regular posts only
        ],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# --- State management ---

class ScrapeState:
    """Track which topics have been scraped, with post counts for change detection."""

    def __init__(self, output_dir: Path):
        self.state_file = output_dir / "_scrape_state.json"
        self.scraped_ids: set[int] = set()
        # topic_id -> posts_count at last scrape (for detecting updates)
        self.topic_post_counts: dict[int, int] = {}
        self.stats = {"topics_scraped": 0, "topics_failed": 0, "topics_updated": 0, "posts_total": 0}
        self._load()

    def _load(self) -> None:
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text())
            self.scraped_ids = set(data.get("scraped_ids", []))
            self.topic_post_counts = {int(k): v for k, v in data.get("topic_post_counts", {}).items()}
            self.stats = data.get("stats", self.stats)
            # Backcompat: ensure new stat keys exist
            self.stats.setdefault("topics_updated", 0)

    def save(self) -> None:
        data = {
            "scraped_ids": sorted(self.scraped_ids),
            "topic_post_counts": self.topic_post_counts,
            "stats": self.stats,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def mark_done(self, topic_id: int, post_count: int) -> None:
        is_new = topic_id not in self.scraped_ids
        self.scraped_ids.add(topic_id)
        self.topic_post_counts[topic_id] = post_count
        if is_new:
            self.stats["topics_scraped"] += 1
        else:
            self.stats["topics_updated"] += 1
        self.stats["posts_total"] += post_count

    def mark_failed(self, topic_id: int) -> None:
        self.stats["topics_failed"] += 1

    def is_done(self, topic_id: int) -> bool:
        return topic_id in self.scraped_ids

    def needs_update(self, topic_id: int, current_posts_count: int) -> bool:
        """Check if a previously scraped topic has new replies."""
        if topic_id not in self.scraped_ids:
            return True  # never scraped
        old_count = self.topic_post_counts.get(topic_id, 0)
        return current_posts_count > old_count


# --- Main scrape logic ---

def scrape(
    cred: Credential,
    output_dir: Path,
    category_id: Optional[int] = None,
    min_likes: int = 0,
    resume: bool = False,
    update: bool = False,
    max_topics: int = 0,
    cookie: Optional[str] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Cookie mode: 150 req/min (safe margin under 200 IP limit)
    # API key mode: 18 req/min (safe margin under 20 user key limit)
    rpm = 150.0 if cookie else 18.0
    limiter = RateLimiter(requests_per_minute=rpm)
    log.info("Rate limit: %.0f req/min (%s mode)", rpm, "cookie" if cookie else "api-key")

    if resume or update:
        state = ScrapeState(output_dir)
    else:
        state = ScrapeState.__new__(ScrapeState)
        state.state_file = output_dir / "_scrape_state.json"
        state.scraped_ids = set()
        state.topic_post_counts = {}
        state.stats = {"topics_scraped": 0, "topics_failed": 0, "topics_updated": 0, "posts_total": 0}

    # Step 1: Get categories
    log.info("Fetching categories...")
    categories = fetch_categories(cred, limiter, cookie=cookie)
    log.info("Found %d categories", len(categories))

    # Save category map
    cat_map = {c["id"]: c.get("name", "") for c in categories if "id" in c}
    (output_dir / "_categories.json").write_text(
        json.dumps(cat_map, ensure_ascii=False, indent=2)
    )

    # Filter categories if needed
    if category_id is not None:
        categories = [c for c in categories if c.get("id") == category_id]
        if not categories:
            log.error("Category %d not found", category_id)
            return

    # Step 2: Enumerate topics per category
    all_topic_stubs: list[dict] = []
    for cat in categories:
        cid = cat.get("id")
        cslug = cat.get("slug", str(cid))
        cname = cat.get("name", cslug)

        if cat.get("read_restricted"):
            log.info("Skipping restricted category: %s (%d)", cname, cid)
            continue

        log.info("Fetching topics for category: %s (%d)...", cname, cid)
        topics = fetch_category_topics(cred, cslug, cid, limiter, min_likes, cookie=cookie)
        log.info("  Found %d topics in %s", len(topics), cname)
        all_topic_stubs.extend(topics)

    # Deduplicate by topic ID
    seen = set()
    unique_stubs = []
    for t in all_topic_stubs:
        tid = t.get("id")
        if tid and tid not in seen:
            seen.add(tid)
            unique_stubs.append(t)

    log.info("Total unique topics to scrape: %d", len(unique_stubs))

    if max_topics > 0:
        unique_stubs = unique_stubs[:max_topics]
        log.info("Limited to %d topics", max_topics)

    # Step 3: Fetch full topic content
    topics_dir = output_dir / "topics"
    topics_dir.mkdir(exist_ok=True)

    for i, stub in enumerate(unique_stubs):
        tid = stub.get("id")
        if not tid:
            continue

        if resume and not update and state.is_done(tid):
            continue

        # In update mode: skip topics that haven't changed
        if update and state.is_done(tid):
            stub_posts_count = stub.get("posts_count", 0)
            if not state.needs_update(tid, stub_posts_count):
                continue
            log.info("  Topic %d has new replies, re-scraping...", tid)

        title = stub.get("title", "")[:50]
        log.info("[%d/%d] Topic %d: %s", i + 1, len(unique_stubs), tid, title)

        try:
            topic_data = fetch_topic_full(cred, tid, limiter, cookie=cookie)
            if topic_data:
                # Add category name for convenience
                topic_data["category_name"] = cat_map.get(topic_data.get("category_id"), "")

                out_file = topics_dir / f"{tid}.json"
                out_file.write_text(json.dumps(topic_data, ensure_ascii=False, indent=2))

                post_count = len(topic_data.get("posts", []))
                state.mark_done(tid, post_count)
                log.info("  Saved %d posts", post_count)
            else:
                state.mark_failed(tid)
                log.warning("  Empty topic, skipped")
        except Exception as exc:
            state.mark_failed(tid)
            log.error("  Failed: %s", exc)

        # Save state periodically
        if (i + 1) % 50 == 0:
            state.save()
            log.info("  Checkpoint: %s", json.dumps(state.stats))

    state.save()
    log.info("Scrape complete: %s", json.dumps(state.stats))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk scrape Shuiyuan Discourse forum")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./shuiyuan_data"),
        help="Directory to save scraped data",
    )
    parser.add_argument("--site", default=DEFAULT_SITE)
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_PATH))
    parser.add_argument("--category-id", type=int, default=None, help="Scrape only this category")
    parser.add_argument("--min-likes", type=int, default=0, help="Minimum topic likes to scrape")
    parser.add_argument("--max-topics", type=int, default=0, help="Max topics to scrape (0=all)")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted scrape")
    parser.add_argument("--update", action="store_true", help="Re-scrape topics with new replies")
    parser.add_argument(
        "--cookie",
        default=None,
        help="Discourse _t session cookie (10x faster, no daily cap). "
             "Get it from browser DevTools: Application > Cookies > _t",
    )

    args = parser.parse_args()

    cred = resolve_credential(
        site=args.site,
        auth_path=Path(os.path.expanduser(args.auth_file)).resolve(),
    )
    mode = "cookie (150 req/min)" if args.cookie else "api-key (18 req/min)"
    log.info("Authenticated via %s, mode: %s", cred.source, mode)

    scrape(
        cred=cred,
        output_dir=args.output_dir,
        category_id=args.category_id,
        min_likes=args.min_likes,
        resume=args.resume,
        update=args.update,
        max_topics=args.max_topics,
        cookie=args.cookie,
    )


if __name__ == "__main__":
    main()
