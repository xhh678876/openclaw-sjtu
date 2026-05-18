"""pytest 全局配置 —— 保证 scripts/ 在 sys.path 上。

scripts/ 不是一个真正的安装包(没有 __init__.py),所以从仓库根目录跑
pytest 时,需要把它显式注入 sys.path。本文件由 pytest 自动加载。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
