import { describe, expect, it } from "vitest";
import { reportBundleSchema } from "../schema";
import { filterReportData, validateMetric } from "../lib/validation";
import { valueTypeStyles } from "../lib/styles";
import { bundle, metric } from "./fixtures";

describe("structured dashboard schema", () => {
  it("parses a valid report bundle", () => {
    expect(reportBundleSchema.parse(bundle()).run_id).toBe("test-run");
  });

  it("handles empty structured arrays", () => {
    const value = bundle();
    value.dashboard.report_data!.kpis = [];
    expect(reportBundleSchema.parse(value).dashboard.report_data?.kpis).toEqual([]);
  });

  it("rejects rendering when unit is missing", () => {
    expect(validateMetric(metric({ unit: null }))).toContain("缺少单位");
  });

  it("rejects rendering when period is missing", () => {
    expect(validateMetric(metric({ period: null }))).toContain("缺少年份/期间");
  });

  it("filters unsupported and superseded metrics", () => {
    const report = bundle().dashboard.report_data!;
    report.kpis = [metric({ metric_id: "bad", verification_status: "UNSUPPORTED" }), metric({ metric_id: "old", verification_status: "SUPERSEDED" })];
    const filtered = filterReportData(report);
    expect(filtered.report.kpis).toHaveLength(0);
    expect(filtered.excluded.map((item) => item.metric_id)).toEqual(["bad", "old"]);
  });

  it("distinguishes actual, forecast and target by color, line and text", () => {
    expect(valueTypeStyles.ACTUAL).not.toEqual(valueTypeStyles.FORECAST);
    expect(valueTypeStyles.FORECAST.lineType).toBe("dashed");
    expect(valueTypeStyles.TARGET.label).toBe("目标");
  });

  it("keeps a FAIL report in draft dashboard state", () => {
    const value = reportBundleSchema.parse(bundle("rev_001", "FAIL"));
    expect(value.dashboard.dashboard_status).toBe("BLOCKED_BY_QUALITY");
    expect(value.dashboard.report_data).not.toBeNull();
  });
});
