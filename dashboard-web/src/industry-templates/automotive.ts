import type { IndustryTemplate } from "./general";

export const automotiveTemplate: IndustryTemplate = {
  templateId: "automotive",
  pages: [
    { id: "overview", components: ["KpiSummary", "TimeSeriesChart", "StackedCompositionChart"], metricPatterns: ["注册", "销量", "BEV"], order: 1, emptyStateRequired: true },
    { id: "market", components: ["TimeSeriesChart", "StackedCompositionChart", "DataGapPanel"], metricPatterns: ["BEV", "动力", "注册", "充电", "channel"], order: 2, emptyStateRequired: true },
    { id: "competition", components: ["DotComparisonChart", "CompetitorHeatmap"], metricPatterns: ["车型", "价格", "渠道"], order: 3, emptyStateRequired: true },
    { id: "risk", components: ["RiskMatrix"], metricPatterns: ["监管", "供应链", "关税"], order: 4, emptyStateRequired: true },
    { id: "roadmap", components: ["StrategyTimeline"], metricPatterns: ["市场进入"], order: 5, emptyStateRequired: true },
    { id: "evidence", components: ["EvidenceStatusChart", "SourceGradeChart", "DataGapPanel"], metricPatterns: [], order: 6, emptyStateRequired: true },
    { id: "revision", components: ["RevisionComparison"], metricPatterns: [], order: 7, emptyStateRequired: true },
  ],
};
