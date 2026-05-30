---
name: sjtu-cookie-saver
description: 半交互式手动抓取传承交大(beta.share.dyweb.sjtu.cn)的登录态。打开 Chromium → 用户在浏览器里登 jAccount → 回车后脚本 dump cookies + 抓 localStorage token 到本地 JSON 供脚本复用。当用户说"传承交大重登"、"刷新传承 token"、"传承登不上"、"save_sjtu_cookies"时使用。注：选课社区已改用开放 API key，不再需要抓 cookie。
---

# SJTU 第三方站 Cookie 抓取

针对**不走 jAccount SSO** 的 SJTU 第三方学生站,提供"打开浏览器 → 你登 → 回车 dump cookies"的半交互流程。

## 何时用

- `beta.share.dyweb.sjtu.cn`(传承交大,试卷/资料分享)—— 强制 jAccount 登录,无免登录接口,需抓 token
- 其他**不在 sjtu-oneshot 自动平台列表里**的站点

> 注:**选课社区 course.sjtu.plus 已改用开放 API key**(在 config.json 填 `jcourse_api_key`),
> 不再需要抓 cookie。`course` 参数保留仅作兼容。

不该用的情形:
- 选课社区课评 → 直接配 `jcourse_api_key`,用 `scripts/sjtu_course_review.py`
- jAccount SSO 标准站(i.sjtu / calendar / phycai / lcme) → [sjtu-oneshot](../sjtu-oneshot/SKILL.md)
- 想用 Chrome 已有的 cookies → 直接用 `scripts/auth/chrome_cookies.py`,不用手动登

## Usage

```bash
# 抓传承交大 token（推荐）
~/openclaw-sjtu/.venv/bin/python ~/openclaw-sjtu/scripts/save_sjtu_cookies.py legacy

# 默认抓全部（course 项仅兼容保留）
~/openclaw-sjtu/.venv/bin/python ~/openclaw-sjtu/scripts/save_sjtu_cookies.py
```

## 流程

1. 自动开 Chromium 窗口
2. 你点登录 → jAccount 输账号密码 / 扫码
3. 登录完成后**回到终端按回车**
4. 脚本 dump cookies **+ 抓 localStorage 的 token** 到 `~/.openclaw/skills-data/sjtu-credentials/<site>.json`(0600)
5. `scripts/sjtu_legacy.py` 后续读 `share-dyweb-sjtu-cn.json` 的 `token` 字段调 API（`Auth` header）

## Cookie 存放

```
~/.openclaw/skills-data/sjtu-credentials/
├─ course-sjtu-plus.json     ← course.sjtu.plus
└─ share-dyweb-sjtu-cn.json  ← share.dyweb.sjtu.cn
```

注意路径在用户 home 而不是项目目录 —— 因为这些 cookies 跨项目复用(gateway / scripts / 其他工具)。

## 配套 Skill

- `course.sjtu.plus` 数据消费: `scripts/sjtu_course_review.py` (老 skill,搜课/对比老师)
- 传承交大数据消费: `scripts/sjtu_legacy.py`(老 skill,搜往年试卷/资料)
- 触发词在主 `SKILL.md` 第 (5)(8) 项

## 注意

- 这两个站没有 2FA,jAccount 账号密码登录通常即可
- cookies 有效期通常 7-30 天,失效就再跑一次
- 不要把 dump 出来的 JSON commit 进任何 repo
