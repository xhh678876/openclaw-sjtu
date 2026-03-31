# 贡献指南

感谢你有兴趣为 openclaw-sjtu 做出贡献！🎓

## 如何贡献

1. **Fork** 本仓库
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 提交修改：`git commit -m "feat: 添加xxx功能"`
4. 推送分支：`git push origin feat/your-feature`
5. 提交 **Pull Request**

## Issue 规范

- **Bug 报告**：请附上复现步骤、错误输出和环境信息（Python 版本、操作系统）
- **功能建议**：描述使用场景和预期行为
- **数据更新**：食堂、教室等硬编码数据变动，请注明来源

## PR 规范

- 一个 PR 只做一件事
- 提供清晰的描述
- 确保现有功能不受影响
- 如添加新脚本，请同步更新 `README.md` 和 `SKILL.md`

## Commit 消息格式

```
<type>: <简要描述>

类型:
- feat: 新功能
- fix: 修复
- docs: 文档更新
- refactor: 重构
- chore: 杂项
```

## 代码风格

- Python 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 使用 4 空格缩进
- 函数和关键逻辑添加中文注释
- 敏感信息（Token、密码）一律从 `config.json` 读取，禁止硬编码

## 安全提醒

- **禁止** 在代码或文档中提交任何真实的 Token、密码、用户 ID
- 使用 `config.example.json` 作为配置模板

---

有任何问题，欢迎开 Issue 讨论！
