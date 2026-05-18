---
name: sjtu-oneshot
description: 单 Playwright 会话一次性登录 SJTU 所有平台(jAccount SSO),刷新所有 cookies,然后拉取课表/校历/物理实验/MOOC/Canvas 全部信息,打印统一报告。当用户说"刷新所有交大 cookies"、"登录所有 SJTU 平台"、"一键拉全部信息"、"重新登 jAccount"、"sjtu_oneshot"、"oneshot"、"我的课表/校历过期了"、"i.sjtu 登不上"时使用。
---

# SJTU 一键登录 + 全平台拉取

复用单个 Playwright session 通过 jAccount SSO 把 i.sjtu / calendar / phycai / lcme 几家都登一遍,所有 cookies 落 `config.json`,然后纯 requests 抓数据 + 打印报告。

## When to Invoke

- 用户报告"课表/校历/作业拉不到了" → 多半 cookies 过期,跑本 skill 刷一遍
- "登录 jAccount" / "走一遍 SSO" / "走 2FA"
- 需要批量刷新所有平台 cookies 而不是一家一家点

不该用的情形:
- 只想看 DDL 不想真登录 → [sjtu-deadlines](../sjtu-deadlines/SKILL.md)
- 只想抓某一家(如 Canvas) → 用对应 skill / 脚本

## 关键设计

1. **JATrustCookie 跳 2FA** — 启动前从 config.json + 系统 Chrome 收集 jAccount 信任 cookie,注入 Playwright session。jAccount 看到 trust cookie 就免 2FA 直接通过
2. **单浏览器跑全部** — 一次启动 Playwright,顺序访问 i.sjtu / calendar / phycai 入口,SSO 通过后所有平台共享会话
3. **headless 默认** — 因为有 JATrustCookie 不需要扫码
4. **失败友好** — 三级错误分类(captcha/cred/unknown);凭据错立刻放弃,验证码错重试 5 次;校外网 DNS 失败不阻塞其他平台

## Usage

```bash
# 凭据写一次(0600 落 config.json,日后裸跑)
python3 -m scripts.sjtu_oneshot --save-creds --user <jaccount> --pass <password>

# 之后裸跑(密码已存)
python3 -m scripts.sjtu_oneshot

# 显示浏览器(调试 / 首次 2FA 时用)
python3 -m scripts.sjtu_oneshot --show

# 跳过登录直接用现有 cookies 拉
python3 -m scripts.sjtu_oneshot --skip-login

# 即使从 Chrome 拿到 cookies 也强制走一次完整登录
python3 -m scripts.sjtu_oneshot --force-login

# JSON 汇总输出
python3 -m scripts.sjtu_oneshot --json
```

⚠ **--pass 安全提示**:argv 对 `ps aux` 可见。优先用 `--save-creds` 写一次,后续裸跑。本 skill 已实测验证密码不在 argv 中。

## Seed Cookies 来源(自动收集顺序)

1. **config.json 历史 cookies** — 上次成功登录留下的 JATrustCookie / JAAuthCookie
2. **系统 Chrome 数据库** — 如果你在 Chrome 里登过 jAccount,直接读出来(用 `browser_cookie3`)。`--no-chrome-import` 禁用此源

两个来源都不够 → 走完整 jAccount 流程:密码 + 三级验证码(geek ResNet → Claude Haiku → 手动)+ 可能 2FA

## 报告内容

```
📅 校历 — 当前周 / 学期总周
📚 课表 — 当学期所有课
⏳ 未来 7 天课程 — 展开成单次事件
🔬 物理实验 — 未来安排
🧪 LCME — 机动学院实验预约
🎓 MOOC — 中国大学慕课 ddl
📋 Canvas — 作业 ddl(如配置)
```

## Known Issues

- **phycai / lcme 校外网失败** — 校内域名,需要 VPN。日志会显示 `ERR_NAME_NOT_RESOLVED`,不影响 i.sjtu / calendar
- **首次跑触发 2FA** — 如果 config.json + Chrome 都没有 JATrustCookie,必须先 `--show` 让你手机扫码一次,之后才会有 trust cookie 跳过 2FA
- **验证码 OCR ~80% 准** — 极客协会 ResNet 偶尔识错;识错时下次自动 refresh 重试,最多 5 次。失败截图存 `data/captcha_failures/`(0600)便于人工核对
- **Pillow 必装** — 不装会让 captcha API 因 payload 太大返 413;本 skill 现在会 raise 而不是静默回退

## 依赖

```bash
pip install -r scripts/requirements-platforms.txt
playwright install chromium
```

## 相关 skill

- [sjtu-deadlines](../sjtu-deadlines/SKILL.md) — 只读 DDL,不重新登录
- [sjtu-cookie-saver](../sjtu-cookie-saver/SKILL.md) — 手动登录 course.sjtu.plus / 传承交大(jAccount 之外的站)
