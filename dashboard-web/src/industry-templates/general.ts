import type { PageId } from "../types";

export interface IndustryTemplate {
  templateId: string;
  pages: Array<{
    id: PageId;
    components: string[];
    metricPatterns: string[];
    order: number;
    emptyStateRequired: boolean;
  }>;
}

export const generalTemplate: IndustryTemplate = {
  templateId: "general",
  pages: [
    { id: "overview", components: ["KpiSummary", "TimeSeriesChart", "StackedCompositionChart"], metricPatterns: [], order: 1, emptyStateRequired: true },
    { id: "market", components: ["TimeSeriesChart", "StackedCompositionChart", "DataGapPanel"], metricPatterns: ["market", "revenue", "市场", "收入"], order: 2, emptyStateRequired: true },
    { id: "competition", components: ["DotComparisonChart", "CompetitorHeatmap"], metricPatterns: [], order: 3, emptyStateRequired: true },
    { id: "risk", components: ["RiskMatrix"], metricPatterns: [], order: 4, emptyStateRequired: true },
    { id: "roadmap", components: ["StrategyTimeline"], metricPatterns: [], order: 5, emptyStateRequired: true },
    { id: "evidence", components: ["EvidenceStatusChart", "SourceGradeChart", "DataGapPanel"], metricPatterns: [], order: 6, emptyStateRequired: true },
    { id: "revision", components: ["RevisionComparison"], metricPatterns: [], order: 7, emptyStateRequired: true },
  ],
};
