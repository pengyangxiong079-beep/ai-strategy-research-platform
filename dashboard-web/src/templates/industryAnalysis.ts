import { finalizeTemplate, widget } from "./commonTemplate";

export const industryAnalysisTemplate = finalizeTemplate({
  id: "INDUSTRY_ANALYSIS", title: "行业分析战略看板",
  decisionQuestion: "行业如何演变，增长和利润集中在哪里？",
  storyline: ["行业定义", "市场规模", "细分结构", "竞争格局", "价值链", "驱动因素", "行业风险", "未来情景"],
  priorityMetrics: ["市场规模", "增长率", "集中度", "利润池"],
  requiredDatasets: ["time_series", "segments"], optionalDatasets: ["metrics", "comparisons", "matrices", "risks", "scenarios"],
  emptyStateMessage: "缺少行业规模或结构化细分数据。",
  pages: [
    { id: "industry-overview", label: "行业总览", purpose: "界定行业并解释规模与增长。", widgets: [widget("kpis", "KpiSummary", "行业关键指标", "metrics", 1, true), widget("trend", "TimeSeriesChart", "市场规模趋势", "time_series", 2, true)] },
    { id: "market-structure", label: "市场结构", purpose: "识别增长集中的细分和利润池。", widgets: [widget("segments", "StackedCompositionChart", "细分构成", "segments", 1, true), widget("profit-pool", "HorizontalBarChart", "利润池", "comparisons", 2)] },
    { id: "competitive-landscape", label: "竞争格局", purpose: "比较主要参与者与集中程度。", widgets: [widget("players", "DotComparisonChart", "参与者比较", "comparisons", 1, true), widget("position", "PositioningMatrix", "参与者定位", "matrices", 2)] },
    { id: "value-chain", label: "价值链", purpose: "解释价值创造与利润分布。", widgets: [widget("value-chain", "ValueChainDiagram", "行业价值链", "strategic_options", 1, true)] },
    { id: "trends-scenarios", label: "趋势与情景", purpose: "呈现驱动因素、风险和未来情景。", widgets: [widget("risk", "RiskMatrix", "行业风险", "risks", 1), widget("scenario", "ScenarioChart", "行业情景", "scenarios", 2, true)] },
  ],
});

