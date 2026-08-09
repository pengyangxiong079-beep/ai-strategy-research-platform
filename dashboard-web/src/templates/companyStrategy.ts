import { finalizeTemplate, widget } from "./commonTemplate";

export const companyStrategyTemplate = finalizeTemplate({
  id: "COMPANY_STRATEGY", title: "公司战略看板",
  decisionQuestion: "公司应把资源配置到哪些业务、能力和战略行动上？",
  storyline: ["经营表现", "业务组合", "能力诊断", "战略选择", "资源配置", "执行路线图"],
  priorityMetrics: ["收入", "利润", "现金流", "运营效率"],
  requiredDatasets: ["metrics", "recommendations"], optionalDatasets: ["time_series", "segments", "matrices", "risks", "initiatives"],
  emptyStateMessage: "缺少支持资源配置判断的公司指标或战略建议。",
  pages: [
    { id: "corporate-overview", label: "公司总览", purpose: "呈现公司结论和最重要指标。", widgets: [widget("kpis", "KpiSummary", "经营关键指标", "metrics", 1, true)] },
    { id: "performance-diagnosis", label: "经营诊断", purpose: "分析财务和运营趋势。", widgets: [widget("trend", "TimeSeriesChart", "财务与运营趋势", "time_series", 1, true), widget("composition", "StackedCompositionChart", "收入与利润结构", "segments", 2)] },
    { id: "business-portfolio", label: "业务组合", purpose: "比较业务吸引力、竞争力与资源占用。", widgets: [widget("portfolio", "PortfolioMatrix", "业务组合", "matrices", 1, true)] },
    { id: "capability-gaps", label: "能力差距", purpose: "识别战略所需能力和当前差距。", widgets: [widget("capability", "CompetitorHeatmap", "能力差距", "comparisons", 1, true)] },
    { id: "strategic-priorities", label: "战略重点", purpose: "选择可执行的资源配置重点。", widgets: [widget("options", "PositioningMatrix", "战略选择", "matrices", 1), widget("recommendations", "RecommendationsPanel", "战略重点", "recommendations", 2, true)] },
    { id: "execution-roadmap", label: "执行路线图", purpose: "明确行动、责任和里程碑。", widgets: [widget("roadmap", "InitiativeRoadmap", "行动组合", "initiatives", 1, true)] },
  ],
});

