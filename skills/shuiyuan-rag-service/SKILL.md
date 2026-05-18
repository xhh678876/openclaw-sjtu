---
name: shuiyuan-rag-service
description: 水源社区 RAG 检索的常驻 FastAPI 服务(127.0.0.1:9111),把 BGEM3 embedding + BGE reranker 预加载到内存供 lobster-gateway 等多个客户端共享,避免 stdio MCP 每会话冷启动 30s。当用户说"启动水源 RAG 服务"、"重启 shuiyuan-rag"、"shuiyuan-rag /healthz"、"水源检索服务挂了"、"RAG HTTP 服务状态"、"shuiyuan_rag_http"时使用。
---

# Shuiyuan RAG HTTP 服务

`scripts/shuiyuan_rag_http.py` —— 把原本是 stdio MCP server 的水源检索(`shuiyuan_rag_mcp.py`)包成长跑 FastAPI 服务。

**为什么不用 MCP 直接跑?** Claude Code 每个 session 都会 spawn 一个独立的 stdio server,每个都要 ~30s 冷启动加载 BGEM3 embedding。改 HTTP daemon 后 lobster-gateway 几个 chat session 共享一份内存模型,第一次启动后每查询 1-3s。

## When to Invoke

- 用户问"水源搜索挂了 / 慢了"
- "重启 RAG 服务"
- "查 /healthz / /stats"
- 修改 KB 后要 reload

## 运行

```bash
# 手动启动
~/openclaw-sjtu/.venv/bin/python -m uvicorn shuiyuan_rag_http:app \
  --host 127.0.0.1 --port 9111 --workers 1

# 走 launchd plist(推荐 — 开机自启 + 崩了自动拉起)
launchctl load ~/Library/LaunchAgents/com.dahui.shuiyuan-rag.plist
launchctl start com.dahui.shuiyuan-rag
launchctl list | grep shuiyuan-rag

# plist 模板: ~/agents-chat/gateway/deploy/com.dahui.shuiyuan-rag.plist
```

## API

```bash
# 健康检查 — 报告 lifespan 是否完成预加载
curl -s http://127.0.0.1:9111/healthz
# → {"ok": true, "ready": true}

# 搜索
curl -sS -X POST http://127.0.0.1:9111/search \
  -H "Content-Type: application/json" \
  -d '{"query":"教务选课流程","max_results":5,"recency_days":null}'

# KB 统计 — 总帖数 + 类别分布
curl -sS -X POST http://127.0.0.1:9111/stats
```

### Request Schema (POST /search)

```json
{
  "query":        "string, 1-200 chars (required)",
  "category":     "string | null  — 限制板块",
  "min_likes":    0,
  "max_results":  5,        // 1-20
  "recency_days": null,     // null = 全时段; 1-1825 = 近 N 天
  "time_weight":  0.3       // 0.0-1.0,越大越倾向新帖
}
```

### Response

```json
{
  "query": "...",
  "total": 5,
  "low_confidence": false,   // BGE-reranker 平均置信度低于阈值时 true
  "hits": [{
    "title": "...",
    "excerpt": "...(<=1500 字)",
    "author": "...",
    "category": "...",
    "likes": 0, "views": 0,
    "created_at": "2024-...",
    "url": "https://shuiyuan.sjtu.edu.cn/t/topic/...",
    "confidence": 0.87,
    "is_protected": false
  }]
}
```

## 环境变量

```
SHUIYUAN_KB_PATH        默认 /Users/xiehaohui/openclaw-sjtu/scripts/shuiyuan_kb
SHUIYUAN_LOCAL_BYPASS   "1" = 包含 protected 帖(运营者明确开放,可能有隐私)
                        "0" = 只搜公开表(默认,生产)
```

由 launchd plist 控制,不在代码里写死。

## 安全收敛(已 commit)

- `/healthz` **不再泄露** `SHUIYUAN_KB_PATH` 绝对路径 —— 即使绑 127.0.0.1,localhost fetch 也能拿到没必要给
- `/stats` 500 错误返通用 `"stats unavailable"`,不再回显内部 exception(防止内部路径/LanceDB 实现细节)
- `_models_loaded` 全局布尔替代之前侵入式访问 `srm._embed_model` 私有属性

## 故障排查

| 症状 | 排查 |
|------|------|
| 500 + log "no public table loaded" | KB 文件丢/路径错;检查 `SHUIYUAN_KB_PATH` |
| 首次查询超长 | 正常,BGEM3 加载 30s;之后 1-3s |
| 全部 0 命中 + low_confidence=true | BGE-reranker 全部低于阈值;问题词大概率不在 KB |
| connection refused | 服务没起;`launchctl list \| grep shuiyuan-rag` |
| 重启后 /healthz ready=false | lifespan 还在跑;等 30s |

## 部署架构

```
lobster-gateway (Next.js)  →  127.0.0.1:9111/search  →  BGEM3 + LanceDB
shuiyuan-search MCP client →  同上                   →  共享一份内存模型
```

服务挂了 lobster-gateway 的 chat 会拿不到 RAG 上下文,**直接答用户问题但没引用** —— 不会崩,质量会下降。

## 相关

- KB 数据: `scripts/shuiyuan_kb/`(已 gitignored)
- 老 MCP server: `scripts/shuiyuan_rag_mcp.py`(本服务包它)
- 数据采集: `scripts/shuiyuan_ingest.py` + `scripts/shuiyuan_discourse.py`
