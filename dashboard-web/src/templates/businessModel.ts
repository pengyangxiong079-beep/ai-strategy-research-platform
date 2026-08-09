import { finalizeTemplate, widget } from "./commonTemplate";

export const businessModelTemplate = finalizeTemplate({
  id: "BUSINESS_MODEL", title: "商业模式看板",
  decisionQuestion: "企业如何创造价值、传递价值并获取利润？",
  storyline: ["价值主张", "收入模式", "成本结构", "单位经济性", "价值链", "敏感性与风险"],
  priorityMetrics: ["收入", "毛利", "贡献毛利", "获客成本", "生命周期价值"],
  requiredDatasets: ["metrics"], optionalDatasets: ["segments", "comparisons", "strategic_options", "scenarios", "risks"],
  emptyStateMessage: "缺少可验证的收入、成本或单位经济性数据。",
  pages: [
    { id: "business-model-overview", label: "模式总览", purpose: "解释价值创造、传递和获取机制。", widgets: [widget("kpis", "KpiSummary", "商业模式关键指标", "metrics", 1, true)] },
    { id: "revenue-model", label: "收入模式", purpose: "分析收入来源与稳定性。", widgets: [widget("revenue", "StackedCompositionChart", "收入来源构成", "segments", 1, true)] },
    { id: "cost-structure", label: "成本结构", purpose: "分析主要成本和经营杠杆。", widgets: [widget("cost", "HorizontalBarChart", "成本结构", "comparisons", 1, true)] },
    { id: "unit-economics", label: "单位经济性", purpose: "展示可验证的单位经济性桥接。", widgets: [widget("unit-waterfall", "WaterfallChart", "单位经济性", "metrics", 1, true)] },
    { id: "business-value-chain", label: "价值链", purpose: "定位价值活动和利润获取环节。", widgets: [widget("chain", "ValueChainDiagram", "价值链", "strategic_options", 1, true)] },
    { id: "sensitivity-risks", label: "敏感性与风险", purpose: "分析关键假设、盈亏平衡和风险。", widgets: [widget("scenario", "ScenarioChart", "敏感性情景", "scenarios", 1, true), widget("risk", "RiskMatrix", "商业模式风险", "risks", 2)] },
  ],
});

