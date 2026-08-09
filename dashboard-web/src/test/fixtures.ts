import type { Catalog, Metric, ReportBundle } from "../types";

export function metric(changes: Partial<Metric> = {}): Metric {
  return {
    metric_id: "M1",
    label: "德国BEV注册量",
    value: 545000,
    unit: "辆",
    currency: null,
    geography: "德国",
    period: "2025",
    value_type: "ACTUAL",
    verification_status: "SUPPORTED",
    temporal_status: "HISTORICAL",
    source_fact_ids: ["F1"],
    source_grade: "A",
    confidence: "HIGH",
    ...changes,
  };
}

export function bundle(revision = "rev_001", quality: "PASS" | "WARN" | "FAIL" = "PASS"): ReportBundle {
  return {
    schema_version: "1.0",
    run_id: "test-run",
    revision,
    revision_count: 2,
    scope: { topic: "测试", analysis_date: "2026-08-06" },
    run_manifest: { final_status: quality === "FAIL" ? "NEEDS_REVISION" : "COMPLETED" },
    revision_manifest: { revision_id: revision },
    quality: { overall_status: quality, quality_issues: [] },
    dashboard: {
      schema_version: "1.0",
      dashboard_status: quality === "FAIL" ? "BLOCKED_BY_QUALITY" : "READY",
      quality_status: quality,
      scope: {},
      report_version: revision,
      template_id: "automotive",
      components: [],
      excluded_metrics: [],
      validation_errors: [],
      report_data: {
        schema_version: "1.0",
        scope: { topic: "测试", analysis_type: "市场进入分析", industry: "汽车", geography: "德国", analysis_date: "2026-08-06", selected_template: "automotive" },
        executive_summary: "测试摘要",
        kpis: [metric()],
        time_series: [],
        market_segments: [],
        competitor_comparisons: [],
        risks: [],
        opportunities: [],
        recommendations: [],
        roadmap: [],
        evidence_summary: { verified: 1, partial: 0, unsupported: 0, superseded: 0 },
        data_gaps: [],
      },
    },
  };
}

export function catalog(): Catalog {
  return {
    schema_version: "1.0",
    generated_at: "2026-08-06T00:00:00Z",
    reports: ["rev_001", "rev_002"].map((revision) => ({
      run_id: "test-run", topic: "测试", revision, revision_count: 2,
      quality_status: "PASS", final_status: "COMPLETED", analysis_date: "2026-08-06",
      industry: "汽车", geography: "德国", data_url: `./data/${revision}.json`,
    })),
  };
}
