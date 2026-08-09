# 通用行业与公司战略研究平台

本项目以“结构化证据优先”为原则，把范围确认、数据需求、采集、充分性检查、Research、Review、Fact Verification、人工审核、Strategy、Quality、Revision 和专业 Dashboard 串成可审计工作流。

Canonical JSON 是事实源，Markdown 与 HTML 只是派生视图。数据不足时系统记录缺口并降级展示；`UNSUPPORTED` 不进入核心图表，`PARTIAL` 明示质量提示，历史数据与核验状态分别管理。

离线演示使用 Fake Agent，不需要 `OPENAI_API_KEY`。真实联网研究依赖公开来源可访问性，并可能消耗用户现有 Codex 额度，因此自动测试与 CI 不会启动真实 Agent。

Windows 快速启动、测试命令和架构图见根目录 [README](../README.md)。质量门、Revision 和审计规则分别见本目录的专题文档。
