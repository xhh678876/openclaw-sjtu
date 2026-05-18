"""sjtu_distill.extract_json() 单元测试。

覆盖 Claude CLI 返回的三种常见形式:
  1. 裸 JSON
  2. fenced markdown(```json ... ``` / ``` ... ```)
  3. JSON 之外有解释文字
  4. malformed / 不可解析
"""
from __future__ import annotations

import pytest

from scripts.sjtu_distill import extract_json


def test_bare_json() -> None:
    text = '{"category": "教学", "summary": "test"}'
    out = extract_json(text)
    assert out == {"category": "教学", "summary": "test"}


def test_json_fenced_with_language_tag() -> None:
    text = '```json\n{"category": "考试", "deadline": "2026-06-01"}\n```'
    out = extract_json(text)
    assert out is not None
    assert out["category"] == "考试"
    assert out["deadline"] == "2026-06-01"


def test_json_fenced_without_language_tag() -> None:
    text = '```\n{"a": 1, "b": [2, 3]}\n```'
    out = extract_json(text)
    assert out == {"a": 1, "b": [2, 3]}


def test_json_embedded_with_prose() -> None:
    """Claude 偶尔会前后多一些解释文字 —— 我们应该照样能抓出 JSON。"""
    text = (
        "Here's the JSON you asked for:\n"
        '{"category": "活动", "audience": "全体师生", "summary": "X"}\n'
        "Hope this helps!"
    )
    out = extract_json(text)
    assert out is not None
    assert out["category"] == "活动"
    assert out["audience"] == "全体师生"


def test_skip_marker_passes_through() -> None:
    """SKIP summary 是合法 JSON,extract_json 不该过滤,后续 cmd_run 才会跳过。"""
    text = '{"category":"其它","summary":"SKIP","tags":[]}'
    out = extract_json(text)
    assert out is not None
    assert out["summary"] == "SKIP"


def test_malformed_json_returns_none() -> None:
    text = '{"category": "教学", missing_quote: "x"}'
    assert extract_json(text) is None


def test_no_braces_returns_none() -> None:
    assert extract_json("just a sentence") is None


def test_empty_returns_none() -> None:
    assert extract_json("") is None
    assert extract_json("   \n\n   ") is None


@pytest.mark.parametrize("crud", [
    "```json\n```",
    "```\n```",
    "Sure, here:\n",
])
def test_no_actual_json_payload(crud: str) -> None:
    assert extract_json(crud) is None
