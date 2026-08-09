import { finalizeTemplate, widget } from "./commonTemplate";

export const marketEntryTemplate = finalizeTemplate({
  id: "MARKET_ENTRY",
  title: "市场进入战略看板",
  decisionQuestion: "目标市场是否值得进入，以及应在何时、以何种方式进入？",
  storyline: ["市场吸引力", "客户需求", "竞争强度", "准入障碍", "风险与机会", "进入方式", "情景分析", "进入路线图"],
  priorityMetrics: ["市场规模", "增长率", "进入成本", "渠道覆盖", "里程碑"],
  requiredDatasets: ["metrics", "risks", "recommendations"],
  optionalDatasets: ["time_series", "segments", "geographies", "comparisons", "matrices", "scenarios", "initiatives"],
  emptyStateMessage: "缺少支持进入判断的结构化市场、风险或行动数据。",
  pages: [
    { id: "entry-overview", label: "进入总览", labelEn: "Entry overview", purpose: "呈现进入结论、主要前提、机会和风险，不使用黑箱综合分。", widgets: [widget("entry-kpis", "KpiSummary", "进入判断关键指标", "metrics", 1, true), widget("risk-opportunity", "RiskMatrix", "机会与风险", "risks", 2, true), widget("entry-recommendation", "RecommendationsPanel", "推荐进入结论", "recommendations", 3, true)] },
    { id: "market-opportunity", label: "市场机会", labelEn: "Market opportunity", purpose: "验证市场规模、增长、细分和地区机会。", widgets: [widget("market-trend", "TimeSeriesChart", "市场规模与增长", "time_series", 1, true), widget("segments", "StackedCompositionChart", "细分市场构成", "segments", 2), widget("map", "GeographicMap", "地区机会", "geographies", 3)] },
    { id: "risks-barriers", label: "风险与壁垒", labelEn: "Risks and barriers", purpose: "区分监管、竞争、渠道、供应链、品牌、数据、财务和执行风险。", widgets: [widget("risk-matrix", "RiskMatrix", "进入风险", "risks", 1, true), widget("barrier-heatmap", "CompetitorHeatmap", "准入壁垒", "comparisons", 2), widget("mitigation", "RecommendationsPanel", "风险缓释", "recommendations", 3)] },
    { id: "entry-mode", label: "进入方式", labelEn: "Entry mode", purpose: "比较控制、投资、速度和风险，不强制排名不可比方案。", widgets: [widget("mode-matrix", "PositioningMatrix", "进入方式比较", "matrices", 1, true), widget("mode-comparison", "DotComparisonChart", "速度、投入与风险", "comparisons", 2, true)] },
    { id: "scenario-roadmap", label: "情景与路线图", labelEn: "Scenario and roadmap", purpose: "展示情景、触发条件、里程碑和暂停条件。", widgets: [widget("scenarios", "ScenarioChart", "进入情景", "scenarios", 1, true), widget("roadmap", "InitiativeRoadmap", "阶段性进入路线图", "initiatives", 2, true)] },
  ],
});

