"""跨平台守护进程：统一接口 install/uninstall/status。

来源参考：kuan-er/sjtu-agent/sjtu_agent/scheduler/。

只在用户当前 OS 上加载对应实现：
  Darwin  → launchd
  Linux   → systemd (TODO)
  Windows → taskschd (TODO)
"""

from __future__ import annotations

import sys
from typing import Any


def _backend():
    if sys.platform == "darwin":
        from . import launchd
        return launchd
    raise RuntimeError(f"暂不支持的平台：{sys.platform}（目前只实现了 macOS launchd）")


def install(**kwargs: Any) -> dict:
    return _backend().install(**kwargs)


def uninstall(**kwargs: Any) -> dict:
    return _backend().uninstall(**kwargs)


def status(**kwargs: Any) -> dict:
    return _backend().status(**kwargs)
