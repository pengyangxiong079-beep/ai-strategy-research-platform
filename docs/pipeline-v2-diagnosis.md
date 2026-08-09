# Pipeline V2 现状诊断

## 当前阶段与交接物

当前主流程由 `main.py` 驱动：Scope（本地 JSON）→ Data Requirements（本地 JSON）→ Data Acquisition（Agent JSON）→ Sufficiency/Gap Search（本地）→ Research（Agent Markdown）→ Review（Agent Markdown）→ Fact Verification（Agent Markdown，随后解析为 JSON）→ Human Feedback（Markdown）→ Strategy（Agent Markdown + report JSON）→ Quality（本地）→ Dashboard（结构化 JSON）。

## 主要结构问题

- `run_manifest.json` 同时承担运行状态、质量摘要、文件索引和部分 UI 状态，不是严格的阶段状态模型。
- Research、Review 和 Fact Verification 仍以 Markdown 作为主要 Agent 间交接物；Fact JSON 是 Markdown 生成后的兼容产物。
- F/R/H 是文本编号，拆分事实后容易发生重编号和引用漂移；缺少稳定 Claim/Review/Feedback ID。
- 来源同时存在于 Observation、Fact Markdown、report data 和最终 Markdown，来源等级可能重复维护。
- 多数语义与引用检查集中在最终 Quality Check；产生阶段缺少统一 Stage Contract。
- Revision 以三种固定重跑路径实现，尚无显式依赖图；上游变化可能留下旧 Final、Dashboard 或 Quality。
- 历史运行文件结构跨多个版本；读取逻辑通过默认值兼容，但缺少明确 Legacy 视图模型。
- analysis type 已标准化，industry 搜索词已路由；旧行业报告模板仍可能因 `select_analysis_template` 关键词不足回退 `general`。
- Dashboard 已主要使用结构化 report/dashboard data，不从 Markdown 抽取数字；Legacy draft 会明确留空。

## 风险与升级边界

- 不能直接迁移或覆盖既有 `outputs/`；V2 仅对新运行创建 canonical 目录。
- 现有 Agent 调用与 Codex 认证必须保留；本地验证、渲染、ID、依赖传播不调用 Agent。
- V1 `app.py` 和现有测试继续保留；新入口 `streamlit_app.py` 默认启用 Workspace V2。

## 修改清单

- 新增 `pipeline_v2/`：run state、稳定 ID、contracts/gates、依赖图、renderer、quality、legacy adapter、service。
- 新增 `ui/` 与 `app_pages/`：App Shell、View Models、组件和九个页面。
- 新增 V2 JSON Schema、离线 fixtures、Pipeline/UI/Integration 测试。
- 修改 `main.py`：新运行初始化 V2、manifest 更新同步 run state/canonical artifacts。
- 新增架构、迁移、信息架构、设计系统和用户流文档。

