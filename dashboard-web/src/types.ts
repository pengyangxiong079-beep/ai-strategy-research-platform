export type AnalysisType =
  | "COMPETITOR_ANALYSIS"
  | "MARKET_ENTRY"
  | "INDUSTRY_ANALYSIS"
  | "COMPANY_STRATEGY"
  | "PRODUCT_STRATEGY"
  | "GROWTH_STRATEGY"
  | "BUSINESS_MODEL"
  | "INVESTMENT_MA"
  | "GENERIC_STRATEGY";

export type ValueType =
  | "ACTUAL"
  | "HISTORICAL"
  | "FORECAST"
  | "TARGET"
  | "SCENARIO"
  | "ESTIMATE"
  | "PROXY"
  | "UNKNOWN";

export type VerificationStatus =
  | "SUPPORTED"
  | "PARTIAL"
  | "UNSUPPORTED"
  | "NOT_CHECKED"
  // v1 history compatibility
  | "VERIFIED"
  | "SUPERSEDED"
  | "OUTDATED"
  | "UNKNOWN";

export type TemporalStatus =
  | "CURRENT"
  | "HISTORICAL"
  | "FUTURE_PLAN"
  | "SUPERSEDED"
  | "UNKNOWN"
  // v1 history compatibility
  | "FORECAST"
  | "TARGET"
  | "SCENARIO"
  | "ESTIMATE";

export interface Metric {
  metric_id: string;
  label: string;
  value: number | null;
  unit: string | null;
  currency: string | null;
  geography: string | null;
  period: string | null;
  metric_definition?: string;
  channel_scope?: string | null;
  entity_scope?: string | null;
  comparability_group?: string;
  value_type: ValueType;
  verification_status: VerificationStatus;
  temporal_status: TemporalStatus;
  source_fact_ids: string[];
  source_grade: "A" | "B" | "C" | "D" | "N/A";
  confidence: "HIGH" | "MEDIUM" | "LOW" | number | null;
  quality_note?: string;
  [key: string]: unknown;
}

export interface TimeSeries {
  series_id: string;
  label: string;
  chart_type?: "LINE" | "BAR" | "BAR_LINE";
  points: Metric[];
}

export interface MarketSegment {
  segment_id: string;
  label: string;
  metrics: Metric[];
}

export interface CompetitorComparison {
  comparison_id: string;
  metric_id?: string;
  entities: string[];
  metric: string;
  geography: string | null;
  period: string | null;
  unit: string | null;
  currency: string | null;
  comparable?: boolean;
  is_comparable?: boolean;
  comparability_issues?: string[];
  comparison_basis: string;
  ranking_claim?: boolean;
  metric_definition?: string;
  channel_scope?: string | null;
  entity_scope?: string | null;
  source_fact_ids: string[];
  values?: Array<{ entity: string; value: number | string | null }>;
}

export interface StrategicItem {
  item_id: string;
  label: string;
  description: string;
  severity?: string | null;
  timeframe?: string | null;
  owner?: string | null;
  priority?: string | null;
  source_fact_ids: string[];
  [key: string]: unknown;
}

export interface Recommendation extends StrategicItem {
  recommendation_id?: string;
  title?: string;
  rationale?: string;
  time_horizon?: string | null;
  responsible_function?: string | null;
  required_capabilities?: string[];
  related_risks?: string[];
  related_opportunities?: string[];
  kpi?: string | null;
}

export interface RoadmapItem {
  item_id: string;
  label: string;
  start: string | null;
  end: string | null;
  status: string;
  description?: string;
  source_fact_ids: string[];
  [key: string]: unknown;
}

export interface MatrixPoint {
  item_id: string;
  label: string;
  x: number | null;
  y: number | null;
  size?: number | null;
  x_label?: string;
  y_label?: string;
  methodology?: string;
  source_fact_ids: string[];
  is_analyst_judgment?: boolean;
}

export interface MatrixDataset {
  matrix_id: string;
  label: string;
  matrix_type?: string;
  points: MatrixPoint[];
}

export interface GeographyDatum {
  geography_id: string;
  label: string;
  value: number | null;
  unit?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  period?: string | null;
  source_fact_ids: string[];
  is_demo?: boolean;
}

export interface Scenario {
  scenario_id: string;
  label: string;
  value_type?: "MODELLED" | "QUALITATIVE";
  assumptions?: string[];
  trigger_conditions?: string[];
  implications?: string;
  actions?: string[];
  confidence?: "HIGH" | "MEDIUM" | "LOW" | number | null;
  points?: Metric[];
  source_fact_ids: string[];
}

export interface ReportData {
  schema_version: string;
  scope: Record<string, unknown> & {
    topic: string;
    analysis_type: string;
    industry?: string | null;
    geography: string;
    analysis_date: string;
    selected_template?: string | null;
  };
  executive_summary: string;
  kpis: Metric[];
  time_series: TimeSeries[];
  market_segments: MarketSegment[];
  competitor_comparisons: CompetitorComparison[];
  risks: StrategicItem[];
  opportunities: StrategicItem[];
  recommendations: Recommendation[];
  roadmap: RoadmapItem[];
  evidence_summary: Record<string, number>;
  data_gaps: Array<{
    gap_id: string;
    label: string;
    reason: string;
    required_action?: string | null;
  }>;
}

export interface QualityIssue {
  rule_id?: string;
  severity?: string;
  status?: string;
  reason?: string;
  file?: string;
  metric_id?: string | null;
  [key: string]: unknown;
}

export interface DashboardData {
  schema_version: string;
  dashboard_status: "READY" | "READY_WITH_GAPS" | "BLOCKED_BY_QUALITY" | "UNAVAILABLE";
  quality_status: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
  warning?: string;
  meta?: Record<string, unknown> & { analysis_type?: AnalysisType; is_demo?: boolean };
  executive_summary?: Record<string, unknown>;
  metrics?: Metric[];
  time_series?: TimeSeries[];
  comparisons?: CompetitorComparison[];
  matrices?: MatrixDataset[];
  segments?: MarketSegment[];
  geographies?: GeographyDatum[];
  risks?: StrategicItem[];
  opportunities?: StrategicItem[];
  strategic_options?: StrategicItem[];
  recommendations?: Recommendation[];
  initiatives?: RoadmapItem[];
  scenarios?: Scenario[];
  observations?: Observation[];
  data_coverage?: DataCoverage;
  component_availability?: Record<string, {
    status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "NOT_APPLICABLE";
    reason_code?: string;
    reason: string;
    observed_count?: number;
    exported_count?: number;
    gap_ids?: string[];
    search_stop_reason?: string;
    required_action?: string;
  }>;
  evidence?: Array<Record<string, unknown>>;
  quality?: {
    overall_status?: string;
    quality_issues?: QualityIssue[];
    excluded_fields?: Array<Record<string, unknown>>;
  };
  revision?: { revision_id?: string; revision_count?: number; [key: string]: unknown };
  // v1 compatibility fields
  scope: Record<string, unknown>;
  report_version: string;
  template_id: string;
  industry_template_id?: string;
  components: Array<Record<string, unknown>>;
  excluded_metrics: Array<Record<string, unknown>>;
  validation_errors: string[];
  report_data: ReportData | null;
}

export interface Observation {
  observation_id: string;
  dataset_id: string;
  entity: string;
  metric: string;
  product_name: string;
  category: string;
  value: number | null;
  text_value: string;
  unit: string;
  currency: string;
  period: string;
  geography: string;
  channel: string;
  price_type: string;
  verification_status: VerificationStatus;
  temporal_status: TemporalStatus;
  comparability_group: string;
  source_fact_ids?: string[];
  source_id: string;
  source_url: string;
  source_grade: string;
  notes: string;
  [key: string]: unknown;
}

export interface DataCoverageDataset {
  dataset_id: string;
  priority: "CRITICAL" | "IMPORTANT" | "OPTIONAL";
  status: "PASS" | "PARTIAL" | "INSUFFICIENT" | "NOT_APPLICABLE";
  entity_count: number;
  observation_count: number;
  comparability_rate: number | null;
  dashboard_readiness: Record<string, boolean>;
  gaps: Array<Record<string, unknown>>;
}

export interface DataCoverage {
  overall_status?: string;
  datasets?: DataCoverageDataset[];
  search_stop_reason?: string;
  gap_search_rounds_completed?: number;
}

export interface ReportBundle {
  schema_version: "1.0";
  run_id: string;
  revision: string;
  revision_count: number;
  scope: Record<string, unknown>;
  run_manifest: Record<string, unknown>;
  revision_manifest: Record<string, unknown> | null;
  quality: {
    overall_status: "PASS" | "WARN" | "FAIL" | "UNKNOWN";
    quality_issues: QualityIssue[];
  };
  dashboard: DashboardData;
}

export interface CatalogEntry {
  run_id: string;
  topic: string;
  revision: string;
  revision_count: number;
  quality_status: string;
  final_status: string;
  analysis_date: string;
  industry: string;
  geography: string;
  data_url: string;
}

export interface Catalog {
  schema_version: "1.0";
  generated_at: string;
  reports: CatalogEntry[];
}

export interface EmbeddedDashboardPayload {
  catalog: Catalog;
  reports: Record<string, ReportBundle>;
  selected_key: string;
}

export type PageId = string;
