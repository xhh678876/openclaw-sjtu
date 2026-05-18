#!/usr/bin/env python3
"""水源 RAG HTTP 服务 — 把 shuiyuan_rag_mcp.search_impl 包成常驻 FastAPI。

为什么要这个：
  - shuiyuan_rag_mcp.py 原本以 stdio MCP server 模式跑（per Claude Code session 一个）
  - 改 HTTP 后所有 lobster-gateway 的 chat session 共享一份内存里的 BGEM3 模型
  - 第一次启动慢 (~30s 加载 embed + reranker)，之后每个查询 1-3s

部署：
  ~/openclaw-sjtu/.venv/bin/python -m uvicorn shuiyuan_rag_http:app \\
    --host 127.0.0.1 --port 9111 --workers 1

  对应 launchd plist 在 ~/agents-chat/gateway/deploy/com.dahui.shuiyuan-rag.plist

调用：
  POST http://127.0.0.1:9111/search
  Body: {"query": "...", "max_results": 5, "recency_days": null}
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# SHUIYUAN_LOCAL_BYPASS 由 launchd plist 控制：
#   "1" = 搜全部 (protected 也返) — 运营者明确选择全开
#   "0" = 只搜公开表 (此 KB 几乎为空，会返 0 结果)
os.environ.setdefault("SHUIYUAN_KB_PATH", "/Users/xiehaohui/openclaw-sjtu/scripts/shuiyuan_kb")
os.environ.setdefault("SHUIYUAN_LOCAL_BYPASS", "0")

# 把 scripts 目录加 sys.path，import shuiyuan_rag_mcp
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import shuiyuan_rag_mcp as srm  # noqa: E402

log = logging.getLogger("shuiyuan_rag_http")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# 启动 lifespan 跑完后置 True;/healthz 用它代替之前侵入式访问 srm._embed_model
_models_loaded = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预加载 embed + reranker，让首个真实请求就快。"""
    global _models_loaded
    log.info("⏳ preloading BGEM3 embedding + reranker (一次性 ~30s)...")
    try:
        srm.get_db()
        srm.get_embed_model()
        # reranker 是 lazy 的，但提前 warm 一下让首请更顺
        srm.get_reranker()
        _models_loaded = True
        log.info("✅ shuiyuan-rag HTTP 服务就绪 — 监听 127.0.0.1:9111")
    except Exception:  # noqa: BLE001
        log.exception("预加载失败（服务会继续起来，单次请求时会再试）")
    yield
    log.info("shuiyuan-rag HTTP 关闭")


app = FastAPI(title="shuiyuan-rag", version="0.1.0", lifespan=lifespan)


class SearchReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    category: str | None = None
    min_likes: int = Field(0, ge=0)
    max_results: int = Field(5, ge=1, le=20)
    recency_days: int | None = Field(None, ge=1, le=365 * 5)
    time_weight: float = Field(0.3, ge=0.0, le=1.0)


class SearchHit(BaseModel):
    title: str
    excerpt: str
    author: str
    category: str
    likes: int
    views: int
    created_at: str
    url: str
    confidence: float
    is_protected: bool = False


class SearchResp(BaseModel):
    query: str
    total: int
    low_confidence: bool
    hits: list[SearchHit]


@app.get("/healthz")
async def healthz() -> dict:
    """健康检查 — 报告启动 lifespan 是否完成。

    不暴露 SHUIYUAN_KB_PATH(绝对文件路径) —— 即便绑 127.0.0.1,localhost
    fetch 也能拿到,没必要泄露。
    """
    return {"ok": True, "ready": _models_loaded}


@app.post("/search", response_model=SearchResp)
async def search(req: SearchReq) -> SearchResp:
    import asyncio

    def _run() -> list[dict[str, Any]]:
        # 强制 jaccount_token=None — 永远只搜公开表，防御性
        return srm.search_impl(
            query=req.query,
            category=req.category,
            min_likes=req.min_likes,
            max_results=req.max_results,
            recency_days=req.recency_days,
            time_weight=req.time_weight,
            jaccount_token=None,
        )

    try:
        raw = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        log.exception("search 失败: %s", req.query[:50])
        raise HTTPException(500, f"search failed: {type(e).__name__}")

    # bypass=0 时上游已不会返 protected；bypass=1 时运营者明确选择放开，全部返
    # 这里不再做剔除（之前的硬性剔除导致全 KB 都是 protected 的情况下零结果）

    low_conf = False
    hits: list[SearchHit] = []
    for r in raw:
        if r.get("_low_confidence"):
            low_conf = True
        hits.append(
            SearchHit(
                title=(r.get("topic_title") or "")[:200],
                excerpt=(r.get("text") or "")[:1500],
                author=r.get("username") or "anon",
                category=r.get("category") or "",
                likes=int(r.get("like_count") or 0),
                views=int(r.get("views") or 0),
                created_at=(r.get("created_at") or "")[:19],
                url=r.get("url") or "",
                confidence=round(float(r.get("_rerank") or 0.0), 3),
                is_protected=bool(r.get("_is_protected", False)),
            )
        )

    return SearchResp(
        query=req.query, total=len(hits), low_confidence=low_conf, hits=hits
    )


@app.post("/stats")
async def stats() -> dict:
    """KB 统计：总帖数、类别分布。"""
    _, table = srm.get_db()
    if table is None:
        return {"error": "no public table loaded"}
    try:
        df = table.to_pandas()
        return {
            "total_posts": len(df),
            "categories": df["category"].value_counts().head(15).to_dict()
            if "category" in df.columns
            else {},
        }
    except Exception:  # noqa: BLE001
        log.exception("stats 失败")
        raise HTTPException(500, "stats unavailable")
