---
name: sjtu-crawler
description: 抓取 SJTU 全站门户网站(教务/研究生院/学院/招生/图书馆/IT 等 50+ 站点)的通知公告,并用 Claude Opus 把每条公告蒸馏成结构化 JSON(类别/受众/截止/摘要/tags)。当用户说"爬交大网站"、"抓教务通知"、"采集 SJTU 公告"、"蒸馏公告"、"sjtu_crawler"、"sjtu_distill"、"建本地知识库"、"今天教务发了什么"时使用。
---

# SJTU 全站爬虫 + Claude 蒸馏

两段式管线:

1. **`sjtu_crawler`** — 按 `data/sjtu_sites.yaml` 种子清单抓列表页 → 解析条目 → 抓详情正文 → 入 SQLite + 归档 raw HTML。URL + content_hash 双重去重
2. **`sjtu_distill`** — 把入库的公告原文喂给 `claude -p --model claude-opus-4-6 --output-format json`,蒸馏出 `{category, audience, deadline, action_required, summary, tags}`,写 `distilled` 表

## When to Invoke

- 用户要建本地"交大公告知识库"
- "教务最近发了什么 / 研究生院什么时候开会"
- "把这周所有通知摘成清单"
- "对比奖学金通知 / 招聘公告"
- 跟 RAG / 检索 / 提醒系统对接

## Sites 种子清单

`data/sjtu_sites.yaml` 按 `priority` (1=必抓 / 2=重要 / 3=可选) 和 `type` (jwc / grad / student / career / library / it / department / platform) 分类。新增站点只用追 YAML,不用改代码。

每个 site 字段:
```yaml
- name: 教务处通知
  type: jwc
  priority: 1
  list_url: https://jwc.sjtu.edu.cn/tzgg.htm
  base_url: https://jwc.sjtu.edu.cn/
  item_selector: ul.wp_article_list li     # 默认值在 defaults: 下
  title_selector: a
  date_selector: .date
  detail_selector: .wp_articlecontent
  encoding: utf-8                          # 部分老站是 gb2312
```

## Usage

```bash
# 列出所有站点
python3 scripts/sjtu_crawler.py list

# 只抓 priority<=1 的核心站点,每站最多 5 条新
python3 scripts/sjtu_crawler.py crawl --priority 1 --limit 5

# 只抓某站(用于调试新站配置)
python3 scripts/sjtu_crawler.py crawl --site 教务处通知 --limit 10

# 统计已入库
python3 scripts/sjtu_crawler.py stats

# 蒸馏 5 篇未蒸馏的(消耗 Claude Opus 额度)
python3 scripts/sjtu_distill.py run --limit 5

# 只蒸馏某站
python3 scripts/sjtu_distill.py run --site 教务处通知 --limit 20

# 看一条蒸馏结果
python3 scripts/sjtu_distill.py show 42

# 列出最新蒸馏结果
python3 scripts/sjtu_distill.py list --limit 20
```

## SQLite Schema

```
data/sjtu_kb.db
├─ documents     (id, site_name, site_type, url, title, published_at,
│                 crawled_at, content, content_hash, raw_path, distilled)
└─ distilled     (doc_id, category, audience, deadline, action_required,
                  summary, tags, model, created_at)
```

`distilled` 列在 documents 表上是个 enum:
- `0` 未蒸馏
- `1` 蒸馏成功
- `2` 蒸馏返回 SKIP(空页/导航页,跳过)

## 文件归档

`data/raw/<domain>/<url_sha1[:16]>.html`(chmod 0600,可能含校内 PII)。`data/raw/` 已 gitignored。

## 成本(蒸馏)

每篇调一次 `claude -p --model claude-opus-4-6`。HTML 截 6000 字 → prompt + completion 平均 ~2k tokens。按目前 Opus 价格大概 $0.02-0.05 / 篇。**先跑 `--limit 1` 验证产出格式,确认后再批量**。

## Security 修复(已 commit)

- prompt 走 stdin 不走 argv —— 避免 ARG_MAX 截断 + prompt-injection 表面更小
- raw HTML 落盘 chmod 0o600 —— 避免同机器其他用户读到校内门户的姓名/邮件等 PII
- SQLite 连接走 `contextmanager`,杜绝连接泄漏

## 测试

```bash
.venv/bin/python -m pytest tests/test_distill_extract_json.py -v
```

## 限制

- **没并发** — 顺序抓,大量站点会很慢。`REQ_GAP` 节流 1.5s
- **HTML 解析靠 CSS selector** — 站点 DOM 改了选择器就废,需要 YAML 跟进
- **校内域名需要 VPN** — `iam.sjtu.edu.cn` 等部分站点校外不可达
