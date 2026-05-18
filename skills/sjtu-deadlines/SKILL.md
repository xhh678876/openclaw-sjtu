---
name: sjtu-deadlines
description: 跨平台聚合所有 SJTU 截止任务(作业/实验/测验)到一张清单。覆盖 Canvas、phycai 物理实验、icourse163 MOOC、lcme 机动学院实验预约。支持文本/JSON 输出和 macOS 通知。当用户问"我有什么 DDL/作业/实验"、"明天要交什么"、"周几有实验"、"未来要做什么"、"提醒我下一个截止"、"unified_ddl"、"截止任务"、"待办"时使用。
---

# SJTU 跨平台 DDL 聚合

把分散在 Canvas / phycai / icourse163 / lcme 几家平台的截止任务收成一张统一表,支持文本/JSON 两种输出与系统通知。

## When to Invoke

- 用户问"我未来有什么 DDL / 作业 / 实验"
- "下次实验/测验是什么时候"
- 跨平台对比"哪些截止已过 vs 即将到来"
- 跟 launchd 定时任务对接(`--remind-check`)

不该用本 skill 的情形:
- 只关心 Canvas → 用 `scripts/canvas_api.py ddls`(老 skill,更细)
- 要登录刷新 cookies + 抓全部内容(课表/校历/...) → 用 [sjtu-oneshot](../sjtu-oneshot/SKILL.md)

## Architecture

```
scripts/unified_ddl.py        ← CLI 入口
   └─ scripts/platforms/      ← 每平台一个适配器
       ├─ base.py             (DDLItem dataclass + BasePlatform abc)
       ├─ phycai.py           (物理实验排课;校内域名,需 VPN)
       ├─ icourse163.py       (中国大学 MOOC;互联网公网可达)
       ├─ lcme.py             (机动学院 openlab;校内域名,需 VPN)
       └─ calendar_sjtu.py    (校历;互联网公网可达)
```

每个适配器实现 `login()` + `list_ddls() -> list[DDLItem]`。`unified_ddl` 惰性导入,某家挂掉不拖累其他。

## Usage

```bash
# 文本表(默认)
python3 -m scripts.unified_ddl

# JSON(给程序用)
python3 -m scripts.unified_ddl --json

# 跳过某家
python3 -m scripts.unified_ddl --skip phycai lcme

# 检查 70 分钟内即将到期 + macOS 通知(launchd 调这个)
python3 -m scripts.unified_ddl --remind-check
```

## 凭据 / Cookies

- 走 `config.json` 里各平台的 `*_cookies`。若过期,先跑 [sjtu-oneshot](../sjtu-oneshot/SKILL.md) 刷新
- icourse163 需要 `.env` 设 `MOOC_USERNAME` / `MOOC_PASSWORD` + `config.json` 里 `icourse_courses` 数组
- lcme 默认用 jAccount 同账号密码;不同时单独填 `lcme_username` / `lcme_password`

## 已知限制(校外网)

| 平台 | 校外访问 |
|------|---------|
| Canvas (oc.sjtu.edu.cn) | ✓ 公网可达 |
| calendar.sjtu.edu.cn | ✓ 公网可达 |
| icourse163.org | ✓ 互联网 |
| phycai.sjtu.edu.cn | ✗ 校内域名,需 VPN |
| lcme.sjtu.edu.cn | ✗ 校内域名,需 VPN |

校外网跑会出现 `ERR_NAME_NOT_RESOLVED`,**不是 bug**,是网络环境限制。可以 `--skip phycai lcme`。

## launchd 集成

```bash
python3 -m scripts.scheduler.launchd install daily-report
python3 -m scripts.scheduler.launchd install remind-check
```

- `daily-report` 每天 22:00 跑 `unified_ddl --notify`
- `remind-check` 每分钟跑 `--remind-check` 检测 70min 内即将到期

## Safety

- macOS 通知里课程/作业名走 `_applescript_escape` 转义,避免被注入 `do shell script`
- 凭据不上 CLI argv;`--pass` 已加 ps-aux 警告,缺密码时 getpass 交互式询问

## 测试

```bash
.venv/bin/python -m pytest tests/test_platform_parsers.py -v
```
