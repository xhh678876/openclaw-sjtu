#!/usr/bin/env python3
"""RAG quality evaluation framework.

Supports multi-model cross-validation: Claude, Gemini, and GPT each score
the same retrieval results independently. Agreement = confidence.

Usage:
    # Generate eval dataset from scraped data
    python rag_eval.py generate --data-dir ./shuiyuan_data --output eval_queries.json

    # Run retrieval and collect results
    python rag_eval.py retrieve --queries eval_queries.json --db-path ./shuiyuan_kb

    # Score with multiple models
    python rag_eval.py score --results eval_results.json --model claude
    python rag_eval.py score --results eval_results.json --model gemini
    python rag_eval.py score --results eval_results.json --model openai

    # Compare scores across models
    python rag_eval.py compare --scores-dir ./eval_scores/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
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


# --- Query generation ---

def generate_eval_queries(data_dir: Path, output: Path, n_queries: int = 100) -> None:
    """Generate evaluation queries from scraped topics.

    Strategy: extract titles and high-engagement posts as natural queries.
    """
    topics_dir = data_dir / "topics"
    topic_files = list(topics_dir.glob("*.json"))
    random.shuffle(topic_files)

    queries = []
    for tf in topic_files:
        if len(queries) >= n_queries:
            break
        try:
            topic = json.loads(tf.read_text())
        except Exception:
            continue

        title = topic.get("title", "")
        if not title or len(title) < 5:
            continue

        # Use topic title as a natural query
        queries.append({
            "query": title,
            "source_topic_id": topic.get("id"),
            "expected_category": topic.get("category_name", ""),
            "type": "title_as_query",
        })

        # Also generate paraphrased queries from high-like posts
        for post in topic.get("posts", [])[:3]:
            if post.get("like_count", 0) >= 3:
                raw = post.get("raw", "")
                # Take first sentence as a query
                first_line = raw.split("\n")[0].strip()
                if 10 < len(first_line) < 200:
                    queries.append({
                        "query": first_line,
                        "source_topic_id": topic.get("id"),
                        "source_post_id": post.get("id"),
                        "expected_category": topic.get("category_name", ""),
                        "type": "post_excerpt",
                    })

    queries = queries[:n_queries]
    output.write_text(json.dumps(queries, ensure_ascii=False, indent=2))
    log.info("Generated %d eval queries -> %s", len(queries), output)


# --- Retrieval ---

def run_retrieval(queries_file: Path, db_path: str, output: Path, max_results: int = 5) -> None:
    """Run retrieval for all eval queries, save results."""
    from shuiyuan_rag_mcp import search_impl

    queries = json.loads(queries_file.read_text())
    results = []

    for i, q in enumerate(queries):
        log.info("[%d/%d] %s", i + 1, len(queries), q["query"][:50])
        try:
            hits = search_impl(query=q["query"], max_results=max_results)
        except Exception as exc:
            log.warning("Search failed for '%s': %s", q["query"][:30], exc)
            hits = []

        results.append({
            **q,
            "results": hits,
            "num_results": len(hits),
        })

    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    log.info("Retrieval complete: %d queries -> %s", len(results), output)


# --- Multi-model scoring ---

SCORE_PROMPT = """You are evaluating a RAG (Retrieval-Augmented Generation) system for a Chinese university forum (SJTU Shuiyuan).

For each query-result pair, score the relevance on a 1-5 scale:
- 5: Perfectly relevant, directly answers the query
- 4: Highly relevant, closely related
- 3: Somewhat relevant, tangentially related
- 2: Barely relevant, only shares keywords
- 1: Not relevant at all

Also flag any quality issues: wrong info, outdated content, spam, etc.

Respond in JSON format:
{
  "scores": [
    {"query_idx": 0, "result_scores": [4, 3, 5, 2, 1], "notes": "..."},
    ...
  ]
}

Here are the query-result pairs to evaluate:
"""


def score_with_claude(results: list[dict], api_key: str | None = None) -> list[dict]:
    """Score results using Claude API."""
    try:
        import anthropic
    except ImportError:
        log.error("pip install anthropic")
        return []

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    # Batch queries (10 at a time to stay within context)
    batch_size = 10
    all_scores = []

    for i in range(0, len(results), batch_size):
        batch = results[i : i + batch_size]
        payload = json.dumps(batch, ensure_ascii=False, indent=2)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": SCORE_PROMPT + payload}],
        )

        try:
            text = response.content[0].text
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            parsed = json.loads(text)
            all_scores.extend(parsed.get("scores", []))
        except Exception as exc:
            log.warning("Failed to parse Claude response: %s", exc)

    return all_scores


def score_with_gemini(results: list[dict], api_key: str | None = None) -> list[dict]:
    """Score results using Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        log.error("pip install google-generativeai")
        return []

    genai.configure(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-pro")

    batch_size = 10
    all_scores = []

    for i in range(0, len(results), batch_size):
        batch = results[i : i + batch_size]
        payload = json.dumps(batch, ensure_ascii=False, indent=2)

        response = model.generate_content(SCORE_PROMPT + payload)

        try:
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            parsed = json.loads(text)
            all_scores.extend(parsed.get("scores", []))
        except Exception as exc:
            log.warning("Failed to parse Gemini response: %s", exc)

    return all_scores


def score_with_openai(results: list[dict], api_key: str | None = None) -> list[dict]:
    """Score results using OpenAI API."""
    try:
        from openai import OpenAI
    except ImportError:
        log.error("pip install openai")
        return []

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    batch_size = 10
    all_scores = []

    for i in range(0, len(results), batch_size):
        batch = results[i : i + batch_size]
        payload = json.dumps(batch, ensure_ascii=False, indent=2)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": SCORE_PROMPT + payload}],
            max_tokens=4096,
        )

        try:
            text = response.choices[0].message.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            parsed = json.loads(text)
            all_scores.extend(parsed.get("scores", []))
        except Exception as exc:
            log.warning("Failed to parse OpenAI response: %s", exc)

    return all_scores


def run_scoring(results_file: Path, model: str, output_dir: Path) -> None:
    """Run scoring with specified model."""
    results = json.loads(results_file.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)

    scorers = {
        "claude": score_with_claude,
        "gemini": score_with_gemini,
        "openai": score_with_openai,
    }

    scorer = scorers.get(model)
    if not scorer:
        log.error("Unknown model: %s. Choose from: %s", model, list(scorers.keys()))
        return

    log.info("Scoring %d queries with %s...", len(results), model)
    scores = scorer(results)

    output_file = output_dir / f"scores_{model}.json"
    output_file.write_text(json.dumps({
        "model": model,
        "num_queries": len(results),
        "scores": scores,
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, ensure_ascii=False, indent=2))
    log.info("Scores saved to %s", output_file)


# --- Cross-model comparison ---

def compare_scores(scores_dir: Path) -> None:
    """Compare scores across models and report agreement."""
    score_files = list(scores_dir.glob("scores_*.json"))
    if len(score_files) < 2:
        log.error("Need at least 2 score files to compare. Found: %d", len(score_files))
        return

    models = {}
    for sf in score_files:
        data = json.loads(sf.read_text())
        model_name = data["model"]
        # Flatten: query_idx -> mean score
        query_scores = {}
        for s in data["scores"]:
            idx = s.get("query_idx", 0)
            result_scores = s.get("result_scores", [])
            if result_scores:
                query_scores[idx] = sum(result_scores) / len(result_scores)
        models[model_name] = query_scores

    model_names = list(models.keys())
    print(f"\n{'='*60}")
    print(f"Cross-Model RAG Quality Comparison")
    print(f"{'='*60}")

    # Per-model averages
    for name, scores in models.items():
        vals = list(scores.values())
        if vals:
            avg = sum(vals) / len(vals)
            print(f"\n{name}: avg score = {avg:.2f} (over {len(vals)} queries)")

    # Pairwise agreement
    print(f"\n--- Pairwise Agreement ---")
    for i, m1 in enumerate(model_names):
        for m2 in model_names[i + 1 :]:
            common = set(models[m1].keys()) & set(models[m2].keys())
            if not common:
                print(f"{m1} vs {m2}: no overlapping queries")
                continue

            diffs = [abs(models[m1][k] - models[m2][k]) for k in common]
            avg_diff = sum(diffs) / len(diffs)
            agree_count = sum(1 for d in diffs if d < 1.0)  # within 1 point
            agree_pct = agree_count / len(diffs) * 100

            print(f"{m1} vs {m2}: avg diff = {avg_diff:.2f}, agreement = {agree_pct:.0f}% ({agree_count}/{len(common)})")

    # Flag disagreements
    print(f"\n--- Top Disagreements (investigate these) ---")
    if len(model_names) >= 2:
        m1, m2 = model_names[0], model_names[1]
        common = set(models[m1].keys()) & set(models[m2].keys())
        disagreements = [(k, abs(models[m1][k] - models[m2][k])) for k in common]
        disagreements.sort(key=lambda x: x[1], reverse=True)
        for idx, diff in disagreements[:10]:
            scores_str = ", ".join(f"{name}: {models[name].get(idx, '?'):.1f}" for name in model_names)
            print(f"  Query #{idx}: {scores_str} (diff={diff:.1f})")

    print(f"\n{'='*60}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="RAG evaluation framework")
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = sub.add_parser("generate", help="Generate eval queries from scraped data")
    gen.add_argument("--data-dir", type=Path, default=Path("./shuiyuan_data"))
    gen.add_argument("--output", type=Path, default=Path("./eval_queries.json"))
    gen.add_argument("--n-queries", type=int, default=100)

    # retrieve
    ret = sub.add_parser("retrieve", help="Run retrieval for eval queries")
    ret.add_argument("--queries", type=Path, required=True)
    ret.add_argument("--db-path", type=str, default="./shuiyuan_kb")
    ret.add_argument("--output", type=Path, default=Path("./eval_results.json"))
    ret.add_argument("--max-results", type=int, default=5)

    # score
    sc = sub.add_parser("score", help="Score results with an LLM")
    sc.add_argument("--results", type=Path, required=True)
    sc.add_argument("--model", required=True, choices=["claude", "gemini", "openai"])
    sc.add_argument("--output-dir", type=Path, default=Path("./eval_scores"))

    # compare
    cmp = sub.add_parser("compare", help="Compare scores across models")
    cmp.add_argument("--scores-dir", type=Path, default=Path("./eval_scores"))

    args = parser.parse_args()

    if args.command == "generate":
        generate_eval_queries(args.data_dir, args.output, args.n_queries)
    elif args.command == "retrieve":
        run_retrieval(args.queries, args.db_path, args.output, args.max_results)
    elif args.command == "score":
        run_scoring(args.results, args.model, args.output_dir)
    elif args.command == "compare":
        compare_scores(args.scores_dir)


if __name__ == "__main__":
    main()
