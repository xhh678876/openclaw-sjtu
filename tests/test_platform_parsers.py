"""平台 HTML 表格解析单元测试。

主要覆盖 phycai._parse_table / lcme._parse_reservation_table —— 这俩
靠表头模糊匹配 + 列位映射来抓取实验排课,DOM 变化时最容易回归。

每个测试喂一段最小可代表性的 HTML fixture,断言:
  - DDLItem 字段映射正确(name/course/due/location)
  - 已过期的实验被过滤
  - 表头同义词被识别(实验项目 vs 项目名称 等)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from scripts.platforms.base import CST
from scripts.platforms.lcme import LCMEPlatform
from scripts.platforms.phycai import PhyCaiPlatform


# ── phycai ──────────────────────────────────────────────────────────────────

def _future_date(days_ahead: int = 7) -> str:
    return (datetime.now(CST) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def test_phycai_parse_basic_table() -> None:
    future = _future_date(7)
    html = f"""
    <html><body>
    <table>
      <tr><th>实验项目</th><th>实验日期</th><th>实验时间</th><th>上课教室</th></tr>
      <tr><td>力学实验 A</td><td>{future}</td><td>14:00-16:00</td><td>物理楼 401</td></tr>
    </table>
    </body></html>
    """
    items = PhyCaiPlatform()._parse_table(html)
    assert len(items) == 1
    item = items[0]
    assert item.platform == "phycai"
    assert item.course == "物理实验"
    assert item.name == "力学实验 A"
    assert item.location == "物理楼 401"
    assert item.due.hour == 14
    assert item.due.minute == 0


def test_phycai_filters_past_dates() -> None:
    past = (datetime.now(CST) - timedelta(days=5)).strftime("%Y-%m-%d")
    future = _future_date(3)
    html = f"""
    <table>
      <tr><th>实验项目</th><th>日期</th><th>时间</th><th>教室</th></tr>
      <tr><td>过期实验</td><td>{past}</td><td>10:00</td><td>A</td></tr>
      <tr><td>未来实验</td><td>{future}</td><td>10:00</td><td>B</td></tr>
    </table>
    """
    items = PhyCaiPlatform()._parse_table(html)
    assert len(items) == 1
    assert items[0].name == "未来实验"


def test_phycai_header_synonyms() -> None:
    """表头用 '项目名称' / '上课日期' / '上课时间' / '实验室' 同样应该被识别。"""
    future = _future_date(5)
    html = f"""
    <table>
      <tr><th>项目名称</th><th>上课日期</th><th>上课时间</th><th>实验室</th></tr>
      <tr><td>电磁学</td><td>{future}</td><td>09:30-11:30</td><td>实验楼 203</td></tr>
    </table>
    """
    items = PhyCaiPlatform()._parse_table(html)
    assert len(items) == 1
    assert items[0].name == "电磁学"
    assert items[0].location == "实验楼 203"


def test_phycai_empty_table_returns_empty() -> None:
    assert PhyCaiPlatform()._parse_table("<html><body></body></html>") == []
    assert PhyCaiPlatform()._parse_table("<table><tr><th>nothing</th></tr></table>") == []


# ── lcme ────────────────────────────────────────────────────────────────────

def test_lcme_parse_reservation_table() -> None:
    future = _future_date(10)
    html = f"""
    <table>
      <tr><th>实验项目</th><th>预约日期</th><th>预约时间</th>
          <th>实验室</th><th>课程</th><th>状态</th></tr>
      <tr><td>液压传动 实验 3</td><td>{future}</td><td>13:00-15:00</td>
          <td>机动 305</td><td>液压气压传动</td><td>已通过</td></tr>
    </table>
    """
    rows = LCMEPlatform._parse_reservation_table(html)
    assert len(rows) == 1
    assert rows[0]["name"] == "液压传动 实验 3"
    assert rows[0]["room"] == "机动 305"
    assert rows[0]["course"] == "液压气压传动"
    assert rows[0]["status"] == "已通过"


def test_lcme_list_ddls_via_parser() -> None:
    """端到端:_parse_reservation_table → list_ddls 过滤 + 转 DDLItem。"""
    future = _future_date(8)
    past = (datetime.now(CST) - timedelta(days=3)).strftime("%Y-%m-%d")
    html = f"""
    <table>
      <tr><th>实验项目</th><th>预约日期</th><th>预约时间</th>
          <th>实验室</th><th>课程</th><th>状态</th></tr>
      <tr><td>已过期</td><td>{past}</td><td>10:00</td>
          <td>A</td><td>课程X</td><td>已完成</td></tr>
      <tr><td>未来实验</td><td>{future}</td><td>14:00-16:00</td>
          <td>B</td><td>课程Y</td><td>已通过</td></tr>
    </table>
    """
    rows = LCMEPlatform._parse_reservation_table(html)
    assert len(rows) == 2  # parser 不过滤过期,list_ddls 才过滤
    # 模拟 list_ddls 的过滤逻辑(避免触网/登录)
    now = datetime.now(CST)
    future_rows = [
        r for r in rows
        if LCMEPlatform._parse_dt(r["date"], r["time"]) is not None
        and LCMEPlatform._parse_dt(r["date"], r["time"]) > now
    ]
    assert len(future_rows) == 1
    assert future_rows[0]["name"] == "未来实验"


def test_lcme_no_tables_returns_empty() -> None:
    assert LCMEPlatform._parse_reservation_table("<div>nothing</div>") == []
