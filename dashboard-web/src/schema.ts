import { z } from "zod";

const valueType = z.enum(["ACTUAL", "HISTORICAL", "FORECAST", "TARGET", "SCENARIO", "ESTIMATE", "PROXY", "UNKNOWN"]);
const verificationStatus = z.enum([
  "SUPPORTED", "PARTIAL", "UNSUPPORTED", "NOT_CHECKED",
  "VERIFIED", "SUPERSEDED", "OUTDATED", "UNKNOWN",
]);
const temporalStatus = z.enum([
  "CURRENT", "HISTORICAL", "FUTURE_PLAN", "SUPERSEDED", "UNKNOWN",
  "FORECAST", "TARGET", "SCENARIO", "ESTIMATE",
]);

export const metricSchema = z.object({
  metric_id: z.string().min(1),
  label: z.string().min(1),
  value: z.number().nullable(),
  unit: z.string().nullable(),
  currency: z.string().nullable(),
  geography: z.string().nullable(),
  period: z.string().nullable(),
  metric_definition: z.string().optional(),
  channel_scope: z.string().nullable().optional(),
  entity_scope: z.string().nullable().optional(),
  comparability_group: z.string().optional(),
  value_type: valueType,
  verification_status: verificationStatus,
  temporal_status: temporalStatus,
  source_fact_ids: z.array(z.string()),
  source_grade: z.enum(["A", "B", "C", "D", "N/A"]),
  confidence: z.union([z.enum(["HIGH", "MEDIUM", "LOW"]), z.number(), z.null()]),
  quality_note: z.string().optional(),
}).passthrough();

const strategicItem = z.object({
  item_id: z.string(),
  label: z.string(),
  description: z.string(),
  severity: z.string().nullable().optional(),
  timeframe: z.string().nullable().optional(),
  owner: z.string().nullable().optional(),
  priority: z.string().nullable().optional(),
  source_fact_ids: z.array(z.string()),
}).passthrough();

const comparisonSchema = z.object({
  comparison_id: z.string(),
  metric_id: z.string().optional(),
  entities: z.array(z.string()),
  metric: z.string(),
  geography: z.string().nullable(),
  period: z.string().nullable(),
  unit: z.string().nullable(),
  currency: z.string().nullable(),
  comparable: z.boolean().optional(),
  is_comparable: z.boolean().optional(),
  comparability_issues: z.array(z.string()).optional(),
  comparison_basis: z.string(),
  ranking_claim: z.boolean().optional(),
  source_fact_ids: z.array(z.string()),
  values: z.array(z.object({
    entity: z.string(),
    value: z.union([z.number(), z.string(), z.null()]),
  })).optional(),
}).passthrough();

const timeSeriesSchema = z.object({
  series_id: z.string(),
  label: z.string(),
  chart_type: z.enum(["LINE", "BAR", "BAR_LINE"]).optional(),
  points: z.array(metricSchema),
}).passthrough();

const marketSegmentSchema = z.object({
  segment_id: z.string(),
  label: z.string(),
  metrics: z.array(metricSchema),
}).passthrough();

const roadmapSchema = z.object({
  item_id: z.string(),
  label: z.string(),
  start: z.string().nullable(),
  end: z.string().nullable(),
  status: z.string(),
  description: z.string().optional(),
  source_fact_ids: z.array(z.string()),
}).passthrough();

export const reportDataSchema = z.object({
  schema_version: z.string(),
  scope: z.object({
    topic: z.string(),
    analysis_type: z.string(),
    industry: z.string().nullable().optional(),
    geography: z.string(),
    analysis_date: z.string(),
    selected_template: z.string().nullable().optional(),
  }).passthrough(),
  executive_summary: z.string(),
  kpis: z.array(metricSchema),
  time_series: z.array(timeSeriesSchema),
  market_segments: z.array(marketSegmentSchema),
  competitor_comparisons: z.array(comparisonSchema),
  risks: z.array(strategicItem),
  opportunities: z.array(strategicItem),
  recommendations: z.array(strategicItem),
  roadmap: z.array(roadmapSchema),
  evidence_summary: z.record(z.number()),
  data_gaps: z.array(z.object({
    gap_id: z.string(),
    label: z.string(),
    reason: z.string(),
    required_action: z.string().nullable().optional(),
  })),
}).passthrough();

const qualityIssueSchema = z.record(z.unknown());

export const dashboardSchema = z.object({
  schema_version: z.string(),
  dashboard_status: z.enum(["READY", "READY_WITH_GAPS", "BLOCKED_BY_QUALITY", "UNAVAILABLE"]),
  quality_status: z.enum(["PASS", "WARN", "FAIL", "UNKNOWN"]),
  warning: z.string().optional(),
  meta: z.record(z.unknown()).optional(),
  executive_summary: z.record(z.unknown()).optional(),
  metrics: z.array(metricSchema).optional(),
  time_series: z.array(timeSeriesSchema).optional(),
  comparisons: z.array(comparisonSchema).optional(),
  matrices: z.array(z.record(z.unknown())).optional(),
  segments: z.array(marketSegmentSchema).optional(),
  geographies: z.array(z.record(z.unknown())).optional(),
  risks: z.array(strategicItem).optional(),
  opportunities: z.array(strategicItem).optional(),
  strategic_options: z.array(strategicItem).optional(),
  recommendations: z.array(strategicItem).optional(),
  initiatives: z.array(roadmapSchema).optional(),
  scenarios: z.array(z.record(z.unknown())).optional(),
  observations: z.array(z.object({
    observation_id: z.string(), dataset_id: z.string(), entity: z.string(), metric: z.string(),
    product_name: z.string(), category: z.string(), value: z.number().nullable(), text_value: z.string(),
    unit: z.string(), currency: z.string(), period: z.string(), geography: z.string(), channel: z.string(),
    price_type: z.string(), verification_status: verificationStatus, temporal_status: temporalStatus, comparability_group: z.string(),
    source_id: z.string(), source_url: z.string(), source_grade: z.string(), notes: z.string(),
  }).passthrough()).optional(),
  data_coverage: z.record(z.unknown()).optional(),
  evidence: z.array(z.record(z.unknown())).optional(),
  quality: z.object({
    overall_status: z.string().optional(),
    quality_issues: z.array(qualityIssueSchema).optional(),
    excluded_fields: z.array(z.record(z.unknown())).optional(),
  }).optional(),
  revision: z.record(z.unknown()).optional(),
  scope: z.record(z.unknown()),
  report_version: z.string(),
  template_id: z.string(),
  industry_template_id: z.string().optional(),
  components: z.array(z.record(z.unknown())),
  excluded_metrics: z.array(z.record(z.unknown())),
  validation_errors: z.array(z.string()),
  report_data: reportDataSchema.nullable(),
}).passthrough();

export const reportBundleSchema = z.object({
  schema_version: z.literal("1.0"),
  run_id: z.string(),
  revision: z.string(),
  revision_count: z.number().int().nonnegative(),
  scope: z.record(z.unknown()),
  run_manifest: z.record(z.unknown()),
  revision_manifest: z.record(z.unknown()).nullable(),
  quality: z.object({
    overall_status: z.enum(["PASS", "WARN", "FAIL", "UNKNOWN"]),
    quality_issues: z.array(qualityIssueSchema),
  }),
  dashboard: dashboardSchema,
});

export const catalogSchema = z.object({
  schema_version: z.literal("1.0"),
  generated_at: z.string(),
  reports: z.array(z.object({
    run_id: z.string(),
    topic: z.string(),
    revision: z.string(),
    revision_count: z.number(),
    quality_status: z.string(),
    final_status: z.string(),
    analysis_date: z.string(),
    industry: z.string(),
    geography: z.string(),
    data_url: z.string(),
  })),
});
