"""Platform 抽象基类。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

CST = timezone(timedelta(hours=8))


@dataclass
class DDLItem:
    platform: str          # "canvas" / "phycai" / "icourse163" / ...
    course: str            # 课程名
    name: str              # 任务名
    due: datetime          # CST 时区
    submitted: bool = False
    location: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "course": self.course,
            "name": self.name,
            "due": self.due.isoformat() if self.due else None,
            "submitted": self.submitted,
            "location": self.location,
            "extra": self.extra,
        }


class BasePlatform:
    """所有平台的统一接口。"""

    name: str = "base"

    def login(self) -> bool:
        """触发 SSO 登录或确认 cookies 有效。返回 True 表示可继续 fetch。"""
        raise NotImplementedError

    def list_ddls(self) -> list[DDLItem]:
        """返回未来截止任务（已过期的应过滤）。"""
        raise NotImplementedError

    def list_courses(self) -> list[dict]:
        """可选：返回已选课程列表。"""
        return []
