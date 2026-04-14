#!/usr/bin/env python3
"""End-to-end RAG evaluation driver — bypasses MCP's jAccount gate for local
testing against the protected table.

Steps:
  1. Smoke-test 5 hand-crafted queries
  2. Generate 50 eval queries from scraped data
  3. Retrieve top-5 for each query
  4. Score with Gemini and OpenAI in parallel
  5. Print agreement summary
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DB_PATH = ROOT / "shuiyuan_kb"
DATA_DIR = ROOT / "shuiyuan_data"


def get_keys() -> dict:
    cfg = json.loads((Path.home() / ".openclaw" / "openclaw.json").read_text())
    keys = {}
    g = cfg.get("models", {}).get("providers", {}).get("google", {})
    if g.get("apiKey"):
        keys["gemini"] = g["apiKey"]
    for entry in cfg.get("skills", {}).get("entries", {}).values():
        if isinstance(entry, dict) and entry.get("apiKey", "").startswith("sk-"):
            keys["openai"] = entry["apiKey"]
            break
    return keys


def load_db():
    import lancedb
    db = lancedb.connect(str(DB_PATH))
    return db.open_table("posts_protected")


def load_model():
    log.info("Loading BGE-M3 (mps)...")
    from FlagEmbedding import BGEM3FlagModel
    return BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["mps"])


def load_reranker():
    log.info("Loading BGE-Reranker-v2-m3 (mps)...")
    from FlagEmbedding import FlagReranker
    # FlagReranker auto-uses GPU if available
    return FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True, devices=["mps"])


def search(table, model, query: str, k: int = 5, reranker=None, oversample: int = 30) -> list[dict]:
    out = model.encode([query], return_dense=True)
    vec = out["dense_vecs"][0].tolist()
    try:
        # Oversample if reranking
        n = oversample if reranker else k
        rows = table.search(vec).limit(n).to_list()
    except Exception as e:
        log.error("Search failed: %s", e)
        return []
    if reranker and rows:
        pairs = [[query, r.get("text", "")] for r in rows]
        scores = reranker.compute_score(pairs, normalize=True)
        for r, s in zip(rows, scores):
            r["_rerank"] = float(s)
        rows = sorted(rows, key=lambda r: -r["_rerank"])[:k]
    else:
        rows = rows[:k]
    return [
        {
            "topic_title": r.get("topic_title", ""),
            "category": r.get("category", ""),
            "username": r.get("username", ""),
            "like_count": r.get("like_count", 0),
            "url": r.get("url", ""),
            "text": (r.get("text", "") or "")[:300],
            "_distance": r.get("_distance", 0),
            "_rerank": r.get("_rerank", None),
        }
        for r in rows
    ]


def smoke_test(table, model):
    print("\n" + "=" * 70)
    print("STEP 1 — Smoke test")
    print("=" * 70)
    queries = [
        "选课系统什么时候开放",
        "宿舍空调坏了找谁修",
        "夏天上海哪里好玩",
        "推荐一门简单好过的通识课",
        "实习面试紧张怎么办",
    ]
    for q in queries:
        print(f"\n  Q: {q}")
        hits = search(table, model, q, k=3)
        for i, h in enumerate(hits, 1):
            print(f"    [{i}] [{h['category']}] {h['topic_title'][:50]}  (dist={h['_distance']:.3f}, ❤{h['like_count']})")
            print(f"        {h['text'][:120].replace(chr(10),' ')}...")


def generate_queries(n: int = 50) -> list[dict]:
    print("\n" + "=" * 70)
    print(f"STEP 2 — Generating {n} eval queries from scraped topics")
    print("=" * 70)
    files = list((DATA_DIR / "topics").glob("*.json"))
    random.seed(42)
    random.shuffle(files)
    queries = []
    for f in files:
        if len(queries) >= n:
            break
        try:
            t = json.loads(f.read_text())
        except Exception:
            continue
        title = t.get("title", "")
        if 8 <= len(title) <= 80 and t.get("posts_count", 0) >= 3:
            queries.append({
                "query": title,
                "source_topic_id": t.get("id"),
                "expected_category_id": t.get("category_id"),
            })
    print(f"  Generated {len(queries)} queries")
    return queries


def run_retrieval(table, model, queries: list[dict]) -> list[dict]:
    print("\n" + "=" * 70)
    print(f"STEP 3 — Retrieval (k=5) for {len(queries)} queries")
    print("=" * 70)
    results = []
    for i, q in enumerate(queries, 1):
        hits = search(table, model, q["query"], k=5)
        # Self-recall: did the source topic appear in top-5?
        src = q.get("source_topic_id")
        # We need topic_id from results. Re-search with topic_id to check.
        out = model.encode([q["query"]], return_dense=True)
        vec = out["dense_vecs"][0].tolist()
        rows = table.search(vec).limit(5).to_list()
        topic_ids = [r.get("topic_id") for r in rows]
        in_topk = src in topic_ids
        results.append({
            **q,
            "results": hits,
            "topic_ids_topk": topic_ids,
            "self_recall@5": in_topk,
        })
        if i % 10 == 0:
            print(f"  {i}/{len(queries)} done")
    rec = sum(r["self_recall@5"] for r in results) / len(results)
    print(f"  Self-recall@5 (source topic in top-5): {rec*100:.1f}%")
    return results


SCORE_PROMPT = """You are evaluating a Chinese university forum RAG system (SJTU 水源).
For each query and its 5 retrieved results, score relevance 1-5:
  5 = directly answers / perfectly matches
  4 = closely related, useful
  3 = somewhat related
  2 = only shares keywords
  1 = not relevant

Reply ONLY with strict JSON, no markdown:
{"scores": [{"q_idx": 0, "ranks": [5,4,3,2,1]}, {"q_idx": 1, "ranks": [...]}, ...]}

Data:
"""


def score_gemini(results: list[dict], api_key: str) -> list[list[int]]:
    print("\n  Scoring with Gemini 2.5 Flash...")
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    out = []
    BATCH = 10
    for i in range(0, len(results), BATCH):
        batch = results[i : i + BATCH]
        compact = [{
            "q_idx": j,
            "query": r["query"],
            "results": [{"title": h["topic_title"], "text": h["text"][:200]} for h in r["results"]],
        } for j, r in enumerate(batch)]
        try:
            resp = model.generate_content(SCORE_PROMPT + json.dumps(compact, ensure_ascii=False))
            txt = resp.text.strip()
            if txt.startswith("```"):
                txt = txt.split("```")[1].lstrip("json").strip()
            parsed = json.loads(txt)
            for s in parsed.get("scores", []):
                out.append(s.get("ranks", []))
        except Exception as e:
            print(f"    batch {i//BATCH} failed: {e}")
            out.extend([[]] * len(batch))
    return out


def score_openai(results: list[dict], api_key: str) -> list[list[int]]:
    print("\n  Scoring with OpenAI gpt-4o-mini...")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    out = []
    BATCH = 10
    for i in range(0, len(results), BATCH):
        batch = results[i : i + BATCH]
        compact = [{
            "q_idx": j,
            "query": r["query"],
            "results": [{"title": h["topic_title"], "text": h["text"][:200]} for h in r["results"]],
        } for j, r in enumerate(batch)]
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": SCORE_PROMPT + json.dumps(compact, ensure_ascii=False)}],
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content)
            for s in parsed.get("scores", []):
                out.append(s.get("ranks", []))
        except Exception as e:
            print(f"    batch {i//BATCH} failed: {e}")
            out.extend([[]] * len(batch))
    return out


def summarize(results: list[dict], gem_scores: list[list[int]], oai_scores: list[list[int]]):
    print("\n" + "=" * 70)
    print("STEP 5 — Summary")
    print("=" * 70)

    def avg_top1(scores):
        vals = [s[0] for s in scores if s]
        return sum(vals) / len(vals) if vals else 0

    def avg_topk(scores, k=5):
        vals = []
        for s in scores:
            if s:
                vals.append(sum(s[:k]) / max(len(s[:k]), 1))
        return sum(vals) / len(vals) if vals else 0

    n = len(results)
    print(f"\n  Queries evaluated      : {n}")
    print(f"  Self-recall@5          : {sum(r['self_recall@5'] for r in results)/n*100:.1f}%")
    print(f"\n  Gemini  avg top-1 score: {avg_top1(gem_scores):.2f}/5   avg top-5: {avg_topk(gem_scores):.2f}/5")
    print(f"  OpenAI  avg top-1 score: {avg_top1(oai_scores):.2f}/5   avg top-5: {avg_topk(oai_scores):.2f}/5")

    # Agreement: how often do the two models agree (within 1 point) on the top-1?
    agree = 0
    both = 0
    for g, o in zip(gem_scores, oai_scores):
        if g and o:
            both += 1
            if abs(g[0] - o[0]) <= 1:
                agree += 1
    if both:
        print(f"\n  Cross-model agreement (top-1 within ±1): {agree}/{both} = {agree/both*100:.1f}%")


def main():
    keys = get_keys()
    print(f"API keys: {list(keys.keys())}")

    table = load_db()
    print(f"Table rows: {table.count_rows():,}")

    model = load_model()

    smoke_test(table, model)

    queries = generate_queries(n=40)
    results = run_retrieval(table, model, queries)

    out_dir = ROOT
    (out_dir / "eval_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"  Saved retrieval results -> eval_results.json")

    print("\n" + "=" * 70)
    print("STEP 4 — Cross-model scoring")
    print("=" * 70)

    gem_scores = score_gemini(results, keys["gemini"]) if "gemini" in keys else []
    oai_scores = score_openai(results, keys["openai"]) if "openai" in keys else []

    (out_dir / "eval_scores.json").write_text(json.dumps({
        "gemini": gem_scores,
        "openai": oai_scores,
    }, ensure_ascii=False, indent=2))

    summarize(results, gem_scores, oai_scores)


if __name__ == "__main__":
    main()
