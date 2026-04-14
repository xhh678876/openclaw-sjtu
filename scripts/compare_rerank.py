#!/usr/bin/env python3
"""Compare retrieval quality with vs without BGE-Reranker-v2-m3 on the
hand-picked smoke queries that previously failed.
"""
import warnings, sys
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from run_eval import load_db, load_model, load_reranker, search

QUERIES = [
    "选课系统什么时候开放",
    "宿舍空调坏了找谁修",
    "夏天上海哪里好玩",
    "推荐一门简单好过的通识课",
    "实习面试紧张怎么办",
]

def show(label, hits):
    print(f"\n  [{label}]")
    for i, h in enumerate(hits, 1):
        rerank = f"  rerank={h['_rerank']:.3f}" if h['_rerank'] is not None else ""
        print(f"    [{i}] [{h['category']}] {h['topic_title'][:50]}  (dist={h['_distance']:.3f}{rerank})")
        print(f"        {h['text'][:120].replace(chr(10),' ')}...")

def main():
    table = load_db()
    print(f"Table rows: {table.count_rows():,}")
    embed = load_model()
    rer = load_reranker()
    for q in QUERIES:
        print("\n" + "=" * 70)
        print(f"Q: {q}")
        print("=" * 70)
        before = search(table, embed, q, k=3)
        after = search(table, embed, q, k=3, reranker=rer, oversample=30)
        show("VECTOR-ONLY", before)
        show("WITH RERANK", after)

if __name__ == "__main__":
    main()
