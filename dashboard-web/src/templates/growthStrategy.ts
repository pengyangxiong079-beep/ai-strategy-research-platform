import { finalizeTemplate, widget } from "./commonTemplate";

export const growthStrategyTemplate = finalizeTemplate({
  id: "GROWTH_STRATEGY", title: "增长战略看板",
  decisionQuestion: "未来增长来自哪些客户、产品、渠道和地区？",
  storyline: ["增长基线", "增长驱动", "细分机会", "渠道与地区", "情景", "行动组合"],
  priorityMetrics: ["收入增长", "新用户", "复购", "客单价", "渠道贡献"],
  requiredDatasets: ["metrics", "recommendations"], optionalDatasets: ["time_series", "segments", "geographies", "scenarios", "initiatives"],
  emptyStateMessage: "缺少可分解的增长驱动或行动数据。",
  pages: [
    { id: "growth-overview", label: "增长总览", purpose: "呈现增长基线与结论。", widgets: [widget("kpis", "KpiSummary", "增长关键指标", "metrics", 1, true), widget("trend", "TimeSeriesChart", "增长趋势", "time_series", 2)] },
    { id: "growth-drivers", label: "增长驱动", purpose: "分解客户、产品、渠道和地区贡献。", widgets: [widget("waterfall", "WaterfallChart", "增长来源分解", "metrics", 1, true)] },
    { id: "segment-opportunities", label: "细分机会", purpose: "比较细分吸引力和增长。", widgets: [widget("segments", "StackedCompositionChart", "细分增长", "segments", 1, true), widget("matrix", "PortfolioMatrix", "细分增长矩阵", "matrices", 2)] },
    { id: "channel-geography", label: "渠道与地区", purpose: "识别渠道贡献和地区机会。", widgets: [widget("channel", "HorizontalBarChart", "渠道贡献", "comparisons", 1), widget("map", "GeographicMap", "地区机会", "geographies", 2, true)] },
    { id: "growth-scenarios", label: "增长情景", purpose: "呈现情景假设和触发条件。", widgets: [widget("scenarios", "ScenarioChart", "增长情景", "scenarios", 1, true)] },
    { id: "growth-roadmap", label: "增长路线图", purpose: "连接行动组合和里程碑。", widgets: [widget("recommendations", "RecommendationsPanel", "增长行动", "recommendations", 1, true), widget("roadmap", "InitiativeRoadmap", "增长里程碑", "initiatives", 2)] },
  ],
});

