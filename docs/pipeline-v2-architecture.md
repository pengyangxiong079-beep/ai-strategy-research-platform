# Pipeline V2 架构

Pipeline V2 将运行控制与研究语义分离。`run_state.json` 是状态权威源；`data/source_registry.json` 和 `data/observations.json` 是来源与观测权威源；`research/claims.json` 是Claim Ledger；`review/review_issues.json`、`fact_check/verified_claims.json`、`human/feedback.json`、`strategy/recommendations.json` 和 `strategy/report_model.json` 分别是各阶段唯一结构化交接物。

阶段顺序为 Scope → Data → Research → Review → Fact Check → Human → Strategy → Report → Dashboard → Quality。每个阶段由 `pipeline_v2/contracts/` 声明输入、输出、前后置条件、阻塞错误、允许警告、修复策略和下游依赖。确定性 Gate 在产物生成阶段运行；WARNING聚合为PASS_WITH_WARNINGS，ERROR才阻塞。

稳定实体ID使用内容派生UUID5：SRC、OBS、CLM、REV、HFB、REC、MET。F/R/H只由Renderer按显示顺序赋值。Renderer根据Claim的source_ids从Source Registry生成邻近Markdown链接。

Agent只用于搜索、语义提取、事实判断、战略分析和语义修订。本地代码负责Schema、ID、渲染、单位日期、依赖传播、Dashboard、Revision Diff和质量聚合。每阶段自动修复最多2次，每个run最多6次。

