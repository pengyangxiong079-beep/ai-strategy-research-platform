import type { AnalysisType, Metric, ReportBundle } from "../types";

export function demoMetric(metric_id: string, label: string, value: number, unit: string, changes: Partial<Metric> = {}): Metric {
  return {
    metric_id, label, value, unit, currency: null, geography: "演示地区", period: "2026演示期",
    metric_definition: "仅用于开发测试的演示口径", value_type: "ACTUAL",
    verification_status: "SUPPORTED", temporal_status: "CURRENT", source_fact_ids: ["F9001"],
    source_grade: "A", confidence: "HIGH", comparability_group: "DEMO_ONLY", is_demo: true,
    ...changes,
  };
}

export function demoBundle(analysisType: AnalysisType, topic: string): ReportBundle {
  const scope = { topic, analysis_type: analysisType, industry: "演示行业", geography: "演示地区", analysis_date: "2026-08-07", time_horizon: "2026—2029（演示）", selected_template: "general", is_demo: true };
  const reportData = {
    schema_version: "1.0", scope, executive_summary: "仅用于模板开发测试，不代表真实研究结论。",
    kpis: [] as Metric[], time_series: [], market_segments: [], competitor_comparisons: [],
    risks: [], opportunities: [], recommendations: [], roadmap: [],
    evidence_summary: { supported: 1, partial: 0, unsupported: 0, not_checked: 0 }, data_gaps: [],
  };
  return {
    schema_version: "1.0", run_id: `demo-${analysisType.toLowerCase()}`, revision: "rev_demo", revision_count: 1,
    scope, run_manifest: { final_status: "DEMO", is_demo: true }, revision_manifest: { revision_id: "rev_demo", is_demo: true },
    quality: { overall_status: "PASS", quality_issues: [] },
    dashboard: {
      schema_version: "2.0", dashboard_status: "READY", quality_status: "PASS", meta: { ...scope, analysis_type: analysisType, run_id: `demo-${analysisType.toLowerCase()}`, is_demo: true },
      executive_summary: { conclusion: reportData.executive_summary }, metrics: [], time_series: [], comparisons: [], matrices: [], segments: [], geographies: [], risks: [], opportunities: [], strategic_options: [], recommendations: [], initiatives: [], scenarios: [], evidence: [{ fact_id: "F9001", result: "SUPPORTED", is_demo: true }], quality: { overall_status: "PASS", quality_issues: [], excluded_fields: [] }, revision: { revision_id: "rev_demo", revision_count: 1 },
      scope, report_version: "rev_demo", template_id: analysisType, components: [], excluded_metrics: [], validation_errors: [], report_data: reportData,
    },
  };
}

