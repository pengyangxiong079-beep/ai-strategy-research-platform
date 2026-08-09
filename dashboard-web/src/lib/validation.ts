import type {
  CompetitorComparison, DashboardData, GeographyDatum, MarketSegment, MatrixDataset,
  Metric, Recommendation, ReportData, RoadmapItem, Scenario, StrategicItem, TimeSeries,
  VerificationStatus,
  Observation, DataCoverage,
} from "../types";
import type { DashboardDataset } from "../templates/types";

export const blockedVerificationStatuses = new Set([
  "UNSUPPORTED", "NOT_CHECKED", "SUPERSEDED", "OUTDATED", "UNKNOWN",
]);

export function normalizeVerificationStatus(status: VerificationStatus | string): VerificationStatus {
  const normalized = String(status || "NOT_CHECKED").toUpperCase();
  if (normalized === "VERIFIED") return "SUPPORTED";
  if (["SUPERSEDED", "OUTDATED"].includes(normalized)) return "UNSUPPORTED";
  if (normalized === "UNKNOWN") return "NOT_CHECKED";
  return normalized as VerificationStatus;
}

export function normalizeMetric(metric: Metric): Metric {
  const verification = normalizeVerificationStatus(metric.verification_status);
  const legacyFuture = ["FORECAST", "TARGET", "SCENARIO"].includes(metric.temporal_status);
  return {
    ...metric,
    verification_status: verification,
    temporal_status: legacyFuture ? "FUTURE_PLAN" : metric.temporal_status === "ESTIMATE" ? "CURRENT" : metric.temporal_status,
    metric_definition: metric.metric_definition || metric.label,
    comparability_group: metric.comparability_group || [
      metric.geography, metric.period, metric.unit, metric.currency, metric.metric_definition || metric.label,
      metric.channel_scope, metric.entity_scope,
    ].filter(Boolean).join("|"),
    quality_note: verification === "PARTIAL" ? "该指标仅获得部分证据支持，请结合来源和限制解读。" : metric.quality_note,
  };
}

export function validateMetric(raw: Metric): string[] {
  const metric = normalizeMetric(raw);
  const reasons: string[] = [];
  if (metric.value === null || !Number.isFinite(metric.value)) reasons.push("缺少有效数值");
  if (!metric.unit) reasons.push("缺少单位");
  if (!metric.period) reasons.push("缺少年份/期间");
  if (!metric.geography) reasons.push("缺少地区");
  if (!metric.source_fact_ids.length) reasons.push("缺少F编号");
  if (blockedVerificationStatuses.has(metric.verification_status)) {
    reasons.push(`核验状态为${metric.verification_status}`);
  }
  return reasons;
}

export function normalizeComparison(item: CompetitorComparison): CompetitorComparison {
  const issues = [...(item.comparability_issues ?? [])];
  if (!item.geography) issues.push("缺少统一地区");
  if (!item.period) issues.push("缺少统一期间");
  if (!item.unit) issues.push("缺少统一单位");
  if (!item.comparison_basis) issues.push("缺少比较口径");
  const declared = item.is_comparable ?? item.comparable ?? false;
  if (!declared && !issues.length) issues.push("报告声明口径不可直接比较");
  const uniqueIssues = [...new Set(issues)];
  return { ...item, comparable: declared && !uniqueIssues.length, is_comparable: declared && !uniqueIssues.length, comparability_issues: uniqueIssues };
}

export function comparisonCanRank(item: CompetitorComparison): boolean {
  const comparison = normalizeComparison(item);
  return Boolean(comparison.is_comparable && comparison.values?.filter((value) => typeof value.value === "number").length && comparison.source_fact_ids.length);
}

export function filterReportData(report: ReportData) {
  const excluded: Array<{ metric_id: string; reasons: string[] }> = [];
  const keep = (raw: Metric) => {
    const metric = normalizeMetric(raw);
    const reasons = validateMetric(metric);
    if (reasons.length) excluded.push({ metric_id: metric.metric_id, reasons });
    return reasons.length === 0;
  };
  return {
    report: {
      ...report,
      kpis: report.kpis.map(normalizeMetric).filter(keep),
      time_series: report.time_series
        .map((series) => ({ ...series, points: series.points.map(normalizeMetric).filter(keep) }))
        .filter((series) => series.points.length > 0),
      market_segments: report.market_segments
        .map((segment) => ({ ...segment, metrics: segment.metrics.map(normalizeMetric).filter(keep) }))
        .filter((segment) => segment.metrics.length > 0),
      competitor_comparisons: report.competitor_comparisons.map(normalizeComparison),
    },
    excluded,
  };
}

export interface DashboardView {
  metrics: Metric[];
  time_series: TimeSeries[];
  comparisons: CompetitorComparison[];
  matrices: MatrixDataset[];
  segments: MarketSegment[];
  geographies: GeographyDatum[];
  risks: StrategicItem[];
  opportunities: StrategicItem[];
  strategic_options: StrategicItem[];
  recommendations: Recommendation[];
  initiatives: RoadmapItem[];
  scenarios: Scenario[];
  evidence: Array<Record<string, unknown>>;
  quality: NonNullable<DashboardData["quality"]>;
  revision: NonNullable<DashboardData["revision"]>;
  data_gaps: ReportData["data_gaps"];
  evidence_summary: Record<string, number>;
  executive_summary: string;
  report: ReportData;
  excluded: Array<Record<string, unknown>>;
  observations: Observation[];
  data_coverage: DataCoverage;
}

export function toDashboardView(dashboard: DashboardData): DashboardView | null {
  if (!dashboard.report_data) return null;
  const filtered = filterReportData(dashboard.report_data);
  const report = filtered.report;
  const metrics = (dashboard.metrics ?? report.kpis).map(normalizeMetric).filter((item) => !validateMetric(item).length);
  const timeSeries = (dashboard.time_series ?? report.time_series).map((series) => ({ ...series, points: series.points.map(normalizeMetric).filter((item) => !validateMetric(item).length) })).filter((series) => series.points.length);
  const segments = (dashboard.segments ?? report.market_segments).map((segment) => ({ ...segment, metrics: segment.metrics.map(normalizeMetric).filter((item) => !validateMetric(item).length) })).filter((segment) => segment.metrics.length);
  const excluded = [...dashboard.excluded_metrics, ...(dashboard.quality?.excluded_fields ?? []), ...filtered.excluded];
  return {
    metrics,
    time_series: timeSeries,
    comparisons: (dashboard.comparisons ?? report.competitor_comparisons).map(normalizeComparison),
    matrices: dashboard.matrices ?? [],
    segments,
    geographies: dashboard.geographies ?? [],
    risks: dashboard.risks ?? report.risks,
    opportunities: dashboard.opportunities ?? report.opportunities,
    strategic_options: dashboard.strategic_options ?? [],
    recommendations: dashboard.recommendations ?? report.recommendations,
    initiatives: dashboard.initiatives ?? report.roadmap,
    scenarios: dashboard.scenarios ?? [],
    evidence: dashboard.evidence ?? [],
    quality: dashboard.quality ?? { overall_status: dashboard.quality_status, quality_issues: [], excluded_fields: excluded },
    revision: dashboard.revision ?? { revision_id: dashboard.report_version, revision_count: 0 },
    data_gaps: report.data_gaps,
    evidence_summary: report.evidence_summary,
    executive_summary: String(dashboard.executive_summary?.conclusion ?? report.executive_summary),
    report,
    excluded,
    observations: (dashboard.observations ?? []).filter((item) => ["SUPPORTED", "PARTIAL", "VERIFIED"].includes(String(item.verification_status).toUpperCase()) && item.temporal_status !== "SUPERSEDED"),
    data_coverage: dashboard.data_coverage ?? {},
  };
}

export function datasetValue(view: DashboardView, dataset: DashboardDataset): unknown {
  if (dataset === "data_gaps") return [...view.data_gaps, ...view.excluded];
  return view[dataset as keyof DashboardView];
}

export function hasDataset(view: DashboardView, dataset: DashboardDataset): boolean {
  const value = datasetValue(view, dataset);
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return Boolean(value);
}

export function formatMetricValue(metric: Metric, locale: string): string {
  if (metric.value === null) return "—";
  const number = new Intl.NumberFormat(locale === "en" ? "en-US" : "zh-CN", {
    maximumFractionDigits: 3,
  }).format(metric.value);
  return [number, metric.unit, metric.currency].filter(Boolean).join(" ");
}
