#!/usr/bin/env python3
"""End-to-end test of MCP search_impl with reranker + confidence threshold.
Monkey-patches verify_jaccount to bypass auth for local testing.
"""
import warnings, sys
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import shuiyuan_rag_mcp as m
m.verify_jaccount = lambda token: True  # bypass for local eval

QUERIES = [
    "选课系统什么时候开放",       # expected: low confidence
    "宿舍空调坏了找谁修",         # expected: low confidence
    "夏天上海哪里好玩",           # expected: low confidence
    "推荐一门简单好过的通识课",   # expected: high confidence (clear hit)
    "实习面试紧张怎么办",         # expected: low confidence
    "信号系统哪个老师好",         # expected: high confidence (course gossip)
]

for q in QUERIES:
    print("\n" + "=" * 70)
    print(f"Q: {q}")
    print("=" * 70)
    results = m.search_impl(query=q, max_results=3, jaccount_token="bypass")
    print(m.format_results(results))
