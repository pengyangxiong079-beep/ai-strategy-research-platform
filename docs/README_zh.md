# 通用行业与公司战略研究平台

本项目以“结构化证据优先”为原则，把范围确认、数据需求、采集、充分性检查、Research、Review、Fact Verification、人工审核、Strategy、Quality、Revision 和专业 Dashboard 串成可审计工作流。

Canonical JSON 是事实源，Markdown 与 HTML 只是派生视图。数据不足时系统记录缺口并降级展示；`UNSUPPORTED` 不进入核心图表，`PARTIAL` 明示质量提示，历史数据与核验状态分别管理。

离线演示使用 Fake Agent，不需要 `OPENAI_API_KEY`。真实联网研究依赖公开来源可访问性，并可能消耗用户现有 Codex 额度，因此自动测试与 CI 不会启动真实 Agent。

## 最新更新

本次更新基于完整真实模式案例的运行反馈，进一步强化了 Pipeline V2 的稳定性、专业报告协议与可视化看板：系统现在会保留无效 Agent 响应用于可审计修复，避免格式重试占用关键数据补检机会，并在 CRITICAL 数据缺口出现时执行一次范围明确、来源优先级清晰的定向检索；同时完善事实核验、时间属性、置信度、管理层摘要、指标与对比数据在报告和看板之间的结构化传递。证据不足时流程仍会停在 `BLOCKED_DATA`，不会生成看似完整但缺少来源支撑的结论。当前版本已通过 136 项 Python 测试、Fake Agent 端到端测试、30 项前端测试、生产构建及仓库安全检查。

Windows 快速启动、测试命令和架构图见根目录 [README](../README.md)。质量门、Revision 和审计规则分别见本目录的专题文档。
