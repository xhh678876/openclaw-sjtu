"""SJTU 多平台抽象层。

每个 platform 模块实现 base.BasePlatform 接口：
  - login()       触发 SSO 或刷 cookie
  - list_ddls()   返回未来截止任务列表

已有平台：
  phycai          物理实验排课 (phycai.sjtu.edu.cn)
  i_sjtu          新教务系统课表/成绩 (i.sjtu.edu.cn)
  calendar_sjtu   学校校历 (calendar.sjtu.edu.cn)
  icourse163      中国大学MOOC (icourse163.org)
"""

from .base import BasePlatform, DDLItem  # noqa: F401
