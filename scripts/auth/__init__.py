"""统一认证 / cookie 持久化层。

模块：
  cookie_store  — 跨平台 cookie 加载/保存 (~/openclaw-sjtu/config.json)
  jaccount      — jAccount SSO 登录（Playwright + 三级验证码）

来源：参考 kuan-er/sjtu-agent 的 login.py 实现，适配本项目 config.json 结构。
"""

from .cookie_store import CookieStore  # noqa: F401
from .jaccount import JAccountLogin    # noqa: F401
from .chrome_cookies import import_from_browser as import_chrome_cookies  # noqa: F401
