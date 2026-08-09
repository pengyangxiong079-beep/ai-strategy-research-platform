import { finalizeTemplate, widget } from "./commonTemplate";

export const genericStrategyTemplate = finalizeTemplate({
  id: "GENERIC_STRATEGY", title: "通用战略看板",
  decisionQuestion: "基于当前证据，最重要的战略判断和下一步行动是什么？",
  storyline: ["结论", "市场与表现", "竞争", "风险与机会", "建议", "执行"],
  priorityMetrics: [], requiredDatasets: ["recommendations"],
  optionalDatasets: ["metrics", "time_series", "segments", "comparisons", "risks", "opportunities", "initiatives"],
  emptyStateMessage: "当前分析类型未匹配专用模板，已使用通用模板；缺失数据将明确标注。",
  pages: [
    { id: "overview", label: "总览", purpose: "呈现最重要的结论和指标。", widgets: [widget("kpis", "KpiSummary", "关键指标", "metrics", 1, true), widget("trend", "TimeSeriesChart", "趋势", "time_series", 2)] },
    { id: "market", label: "市场与结构", purpose: "展示市场趋势和业务结构。", widgets: [widget("segments", "StackedCompositionChart", "市场与业务构成", "segments", 1, true)] },
    { id: "competition", label: "竞争", purpose: "比较可比竞争数据。", widgets: [widget("comparison", "DotComparisonChart", "竞品比较", "comparisons", 1, true)] },
    { id: "risk-opportunity", label: "风险与机会", purpose: "呈现结构化风险与机会。", widgets: [widget("risk", "RiskMatrix", "风险与机会", "risks", 1, true)] },
    { id: "recommendations", label: "战略建议", purpose: "形成有证据支持的行动建议。", widgets: [widget("recommendations", "RecommendationsPanel", "战略建议", "recommendations", 1, true)] },
    { id: "roadmap", label: "执行路线图", purpose: "连接行动与时间。", widgets: [widget("roadmap", "InitiativeRoadmap", "战略路线图", "initiatives", 1, true)] },
  ],
});

