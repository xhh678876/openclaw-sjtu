#!/usr/bin/env python3
"""Comprehensive regression eval for the Shuiyuan RAG system.

Evaluates retrieval across:
  • 60 real topic titles (self-recall baseline)
  • 30 paraphrased natural questions (real-user style)
  • 10 adversarial queries (no expected match — tests confidence warning)

Reports for both vector-only and +rerank modes:
  • self-recall @1/@5/@10
  • LLM score (Gemini + OpenAI), top-1 + avg-top-5
  • confidence threshold accuracy (does <0.3 actually mean "no match"?)
  • category-id agreement
  • failure case study (worst N)
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "shuiyuan_data"


# ---------- query generation ----------

# Hand-crafted natural questions paired with expected topic_id will be filled
# later; for now we use auto-paraphrase via title→question heuristics.
ADVERSARIAL_QUERIES = [
    "今天纳斯达克指数收盘价",          # not on a school forum
    "比特币挖矿收益怎么算",              # off-topic
    "如何申请美国 H1B 签证 2026",        # too specific, unlikely
    "Linux kernel 5.x 调度器源码解析",   # too technical for forum
    "莎士比亚十四行诗第18首翻译",         # academic but unrelated
    "怎么治疗早期肺癌",                  # medical, forum can't answer
    "GTA6 发售日期确认了吗",             # niche gaming news
    "Tesla 股票今天涨了多少",            # finance
    "波音 737 MAX 事故调查报告全文",     # niche aviation
    "FIFA 世界杯 2030 在哪里举办",       # sports trivia
]


def load_topics_index() -> dict[int, dict]:
    """Return topic_id -> {title, category_id, posts_count, ...}"""
    idx = {}
    for f in (DATA_DIR / "topics").glob("*.json"):
        try:
            t = json.loads(f.read_text())
            tid = int(t["id"])
            idx[tid] = {
                "title": t.get("title", ""),
                "category_id": t.get("category_id"),
                "posts_count": t.get("posts_count", 0),
                "first_post_excerpt": "",
            }
            posts = t.get("posts") or []
            if posts:
                raw = posts[0].get("raw", "")
                # First non-empty line, capped
                for line in raw.split("\n"):
                    line = line.strip()
                    if 20 <= len(line) <= 200:
                        idx[tid]["first_post_excerpt"] = line
                        break
        except Exception:
            continue
    return idx


def build_query_set(idx: dict[int, dict], n_titles: int = 60, n_natural: int = 30) -> list[dict]:
    random.seed(7)
    candidates = [(tid, m) for tid, m in idx.items()
                  if 8 <= len(m["title"]) <= 80
                  and m["posts_count"] >= 5
                  and m["first_post_excerpt"]]
    random.shuffle(candidates)
    queries = []
    # Title-as-query
    for tid, m in candidates[:n_titles]:
        queries.append({
            "query": m["title"],
            "type": "title",
            "expected_topic_id": tid,
            "expected_category_id": m["category_id"],
        })
    # Natural-question style: use the first-post excerpt (more colloquial)
    for tid, m in candidates[n_titles : n_titles + n_natural]:
        queries.append({
            "query": m["first_post_excerpt"],
            "type": "natural",
            "expected_topic_id": tid,
            "expected_category_id": m["category_id"],
        })
    # Adversarial
    for q in ADVERSARIAL_QUERIES:
        queries.append({
            "query": q,
            "type": "adversarial",
            "expected_topic_id": None,
            "expected_category_id": None,
        })
    return queries


# ---------- retrieval ----------

def retrieve(table, embed_model, reranker, query: str, k: int = 10) -> list[dict]:
    out = embed_model.encode([query], return_dense=True)
    vec = out["dense_vecs"][0].tolist()
    rows = table.search(vec).limit(50).to_list()
    if reranker and rows:
        pairs = [[query, r.get("text", "")] for r in rows]
        scores = reranker.compute_score(pairs, normalize=True)
        for r, s in zip(rows, scores):
            r["_rerank"] = float(s)
        rows = sorted(rows, key=lambda r: -r["_rerank"])
    return rows[:k]


# ---------- LLM scoring ----------

SCORE_PROMPT = """You are evaluating a Chinese university forum (SJTU 水源) RAG system.
For each (query, retrieved-result) pair, score relevance 1–5:
  5 = directly answers / perfect match
  4 = closely related, useful
  3 = somewhat related
  2 = only shares keywords
  1 = not relevant at all

Reply with strict JSON only, no markdown:
{"scores":[{"q_idx":0,"top_ranks":[5,4,3,2,1]}, ...]}

`top_ranks` lists 1–5 score for the TOP-5 retrieved results (in order).

Data:
"""


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


def make_payload(retrieval_results: list[dict]) -> str:
    """Compact form for LLM scoring. Each entry: query + top-5 results."""
    payload = []
    for i, r in enumerate(retrieval_results):
        payload.append({
            "q_idx": i,
            "query": r["query"],
            "top5": [
                {"title": h.get("topic_title", ""), "text": (h.get("text", "") or "")[:200]}
                for h in r["hits"][:5]
            ],
        })
    return json.dumps(payload, ensure_ascii=False)


def score_gemini(retrieval_results: list[dict], api_key: str) -> list[list[int]]:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    out = []
    BATCH = 10
    for i in range(0, len(retrieval_results), BATCH):
        batch = retrieval_results[i : i + BATCH]
        try:
            resp = model.generate_content(SCORE_PROMPT + make_payload(batch))
            txt = resp.text.strip()
            if txt.startswith("```"):
                txt = txt.split("```")[1].lstrip("json").strip()
            parsed = json.loads(txt)
            for s in parsed.get("scores", []):
                out.append(s.get("top_ranks", []))
        except Exception as e:
            print(f"  gemini batch {i//BATCH} failed: {e}")
            out.extend([[]] * len(batch))
        time.sleep(0.5)  # politeness
    return out


def score_openai(retrieval_results: list[dict], api_key: str) -> list[list[int]]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    out = []
    BATCH = 10
    for i in range(0, len(retrieval_results), BATCH):
        batch = retrieval_results[i : i + BATCH]
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": SCORE_PROMPT + make_payload(batch)}],
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content)
            for s in parsed.get("scores", []):
                out.append(s.get("top_ranks", []))
        except Exception as e:
            print(f"  openai batch {i//BATCH} failed: {e}")
            out.extend([[]] * len(batch))
    return out


# ---------- analysis ----------

def analyze(queries: list[dict], retrieval_results: list[dict],
            gem_scores: list[list[int]], oai_scores: list[list[int]],
            label: str) -> dict:
    n = len(queries)

    # Self-recall (only meaningful for non-adversarial)
    real = [(q, r) for q, r in zip(queries, retrieval_results)
            if q["expected_topic_id"] is not None]
    rec1 = sum(1 for q, r in real
               if q["expected_topic_id"] in [h.get("topic_id") for h in r["hits"][:1]]) / len(real)
    rec5 = sum(1 for q, r in real
               if q["expected_topic_id"] in [h.get("topic_id") for h in r["hits"][:5]]) / len(real)
    rec10 = sum(1 for q, r in real
                if q["expected_topic_id"] in [h.get("topic_id") for h in r["hits"][:10]]) / len(real)

    # Self-recall split by type
    by_type = {}
    for t in ("title", "natural"):
        sub = [(q, r) for q, r in real if q["type"] == t]
        if not sub:
            continue
        by_type[t] = {
            "n": len(sub),
            "rec1": sum(1 for q, r in sub
                        if q["expected_topic_id"] in [h.get("topic_id") for h in r["hits"][:1]]) / len(sub),
            "rec5": sum(1 for q, r in sub
                        if q["expected_topic_id"] in [h.get("topic_id") for h in r["hits"][:5]]) / len(sub),
        }

    # Category agreement (top-1)
    cat = [(q, r) for q, r in real if q["expected_category_id"]]
    cat_match = sum(1 for q, r in cat
                    if r["hits"] and r["hits"][0].get("category_id") == q["expected_category_id"]) / len(cat)

    # LLM avg
    def avg_top1(scores):
        v = [s[0] for s in scores if s]
        return sum(v) / len(v) if v else 0

    def avg_top5(scores):
        v = []
        for s in scores:
            if s:
                v.append(sum(s[:5]) / max(len(s[:5]), 1))
        return sum(v) / len(v) if v else 0

    # Confidence threshold accuracy
    # For each query, get max rerank score from results. Compare:
    # - low-conf flag triggered ↔ adversarial / poor match
    adversarial_flagged = 0
    real_flagged = 0
    n_adv = sum(1 for q in queries if q["type"] == "adversarial")
    n_real = sum(1 for q in queries if q["type"] != "adversarial")
    for q, r in zip(queries, retrieval_results):
        if not r["hits"]:
            continue
        top_rerank = r["hits"][0].get("_rerank", 1.0)
        if top_rerank < 0.3:
            if q["type"] == "adversarial":
                adversarial_flagged += 1
            else:
                real_flagged += 1

    return {
        "label": label,
        "n_queries": n,
        "self_recall@1": rec1,
        "self_recall@5": rec5,
        "self_recall@10": rec10,
        "self_recall_by_type": by_type,
        "category_top1_match": cat_match,
        "llm_gemini_top1": avg_top1(gem_scores),
        "llm_gemini_top5": avg_top5(gem_scores),
        "llm_openai_top1": avg_top1(oai_scores),
        "llm_openai_top5": avg_top5(oai_scores),
        "low_conf_flag_on_adversarial": f"{adversarial_flagged}/{n_adv}",
        "low_conf_flag_on_real": f"{real_flagged}/{n_real}",
    }


def show_failures(queries, retrieval_results, scores, label, n=5):
    """Show worst N queries by LLM top-1 score."""
    paired = [(q, r, s[0] if s else 0) for q, r, s in zip(queries, retrieval_results, scores) if s]
    paired.sort(key=lambda x: x[2])
    print(f"\n{label} — Worst {n} (by LLM top-1):")
    for q, r, score in paired[:n]:
        top = r["hits"][0] if r["hits"] else {}
        rr = top.get("_rerank", 0)
        print(f"  [{score}/5  rerank={rr:.3f}]  Q: {q['query'][:55]}  → {top.get('topic_title','')[:50]}")


# ---------- main ----------

def main():
    print("Loading data + models...")
    keys = get_keys()
    print(f"  API keys: {list(keys.keys())}")

    import lancedb
    db = lancedb.connect(str(ROOT / "shuiyuan_kb"))
    table = db.open_table("posts_protected")
    print(f"  Table: {table.count_rows():,} rows")

    from FlagEmbedding import BGEM3FlagModel, FlagReranker
    embed = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["mps"])
    print("  Embedding model loaded")
    reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True, devices=["mps"])
    print("  Reranker loaded")

    print("\nIndexing topic metadata...")
    idx = load_topics_index()
    print(f"  {len(idx)} topics indexed")

    queries = build_query_set(idx, n_titles=60, n_natural=30)
    print(f"\nBuilt query set: {len(queries)}")
    types = {}
    for q in queries:
        types[q["type"]] = types.get(q["type"], 0) + 1
    print(f"  Type distribution: {types}")

    # ---- VECTOR-ONLY pass ----
    print("\n" + "=" * 60)
    print("PASS 1 — vector-only")
    print("=" * 60)
    vec_results = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        hits = retrieve(table, embed, None, q["query"], k=10)
        vec_results.append({"query": q["query"], "hits": hits})
        if i % 20 == 0:
            print(f"  {i}/{len(queries)}  ({time.time()-t0:.1f}s)")
    print(f"  Done in {time.time()-t0:.1f}s")

    # ---- +RERANK pass ----
    print("\n" + "=" * 60)
    print("PASS 2 — +rerank")
    print("=" * 60)
    rer_results = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        hits = retrieve(table, embed, reranker, q["query"], k=10)
        rer_results.append({"query": q["query"], "hits": hits})
        if i % 20 == 0:
            print(f"  {i}/{len(queries)}  ({time.time()-t0:.1f}s)")
    print(f"  Done in {time.time()-t0:.1f}s")

    # ---- LLM scoring (only on +rerank pass to save API budget,
    # but compute on both) ----
    print("\n" + "=" * 60)
    print("LLM scoring (Gemini + OpenAI on both passes)")
    print("=" * 60)
    print(" vector-only / Gemini ...")
    gem_vec = score_gemini(vec_results, keys["gemini"])
    print(" vector-only / OpenAI ...")
    oai_vec = score_openai(vec_results, keys["openai"])
    print(" +rerank / Gemini ...")
    gem_rer = score_gemini(rer_results, keys["gemini"])
    print(" +rerank / OpenAI ...")
    oai_rer = score_openai(rer_results, keys["openai"])

    # ---- Analyze ----
    rep_vec = analyze(queries, vec_results, gem_vec, oai_vec, "vector-only")
    rep_rer = analyze(queries, rer_results, gem_rer, oai_rer, "+rerank")

    # ---- Save raw ----
    out_dir = ROOT / "regression_out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "queries.json").write_text(json.dumps(queries, ensure_ascii=False, indent=2))
    (out_dir / "retrieval_vector.json").write_text(json.dumps(vec_results, ensure_ascii=False, indent=2, default=str))
    (out_dir / "retrieval_rerank.json").write_text(json.dumps(rer_results, ensure_ascii=False, indent=2, default=str))
    (out_dir / "scores.json").write_text(json.dumps({
        "vector": {"gemini": gem_vec, "openai": oai_vec},
        "rerank": {"gemini": gem_rer, "openai": oai_rer},
    }, ensure_ascii=False, indent=2))
    (out_dir / "report.json").write_text(json.dumps([rep_vec, rep_rer], ensure_ascii=False, indent=2))

    # ---- Print report ----
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    for rep in (rep_vec, rep_rer):
        print(f"\n## {rep['label'].upper()}")
        print(f"  self-recall  @1={rep['self_recall@1']*100:5.1f}%  @5={rep['self_recall@5']*100:5.1f}%  @10={rep['self_recall@10']*100:5.1f}%")
        for tname, m in rep["self_recall_by_type"].items():
            print(f"    [{tname:8s}] @1={m['rec1']*100:5.1f}%  @5={m['rec5']*100:5.1f}%   (n={m['n']})")
        print(f"  category match (top-1)         : {rep['category_top1_match']*100:5.1f}%")
        print(f"  LLM Gemini  top-1={rep['llm_gemini_top1']:.2f}   top-5={rep['llm_gemini_top5']:.2f}")
        print(f"  LLM OpenAI  top-1={rep['llm_openai_top1']:.2f}   top-5={rep['llm_openai_top5']:.2f}")
        print(f"  conf-flag(<0.3) on adversarial : {rep['low_conf_flag_on_adversarial']}  (want HIGH)")
        print(f"  conf-flag(<0.3) on real        : {rep['low_conf_flag_on_real']}  (want LOW)")

    # Failure cases for +rerank pass
    show_failures(queries, rer_results, gem_rer, "+rerank · Gemini", n=5)
    show_failures(queries, rer_results, oai_rer, "+rerank · OpenAI", n=5)

    print(f"\nRaw artifacts saved -> {out_dir}/")


if __name__ == "__main__":
    main()
