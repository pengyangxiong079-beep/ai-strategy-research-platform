import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiSummary } from "../components/KpiSummary";
import { priceCoverageLevel } from "../components/AdaptivePriceChart";
import { competitorAnalysisDemo } from "../fixtures/competitorAnalysis";
import { marketEntryDemo } from "../fixtures/marketEntry";
import { comparisonCanRank, filterReportData, toDashboardView, validateMetric } from "../lib/validation";
import { getAvailablePages, getDashboardTemplate, normalizeAnalysisType } from "../templates";
import { metric } from "./fixtures";

describe("analysis type template registry", () => {
  it("loads the competitor analysis template from Chinese aliases", () => {
    expect(normalizeAnalysisType("竞争对手分析")).toBe("COMPETITOR_ANALYSIS");
    const template = getDashboardTemplate("竞品分析");
    expect(template.id).toBe("COMPETITOR_ANALYSIS");
    expect(template.pages.map((page) => page.id)).toContain("competitive-actions");
  });

  it("loads the market entry template", () => {
    const template = getDashboardTemplate("国际市场进入");
    expect(template.id).toBe("MARKET_ENTRY");
    expect(template.pages.map((page) => page.id)).toContain("scenario-roadmap");
  });

  it("falls back to generic strategy for unknown input", () => {
    expect(getDashboardTemplate("完全未知类型").id).toBe("GENERIC_STRATEGY");
  });

  it("accepts missing optional datasets without throwing", () => {
    const value = structuredClone(competitorAnalysisDemo);
    value.dashboard.geographies = [];
    value.dashboard.matrices = [];
    expect(() => toDashboardView(value.dashboard)).not.toThrow();
  });

  it("shows an Empty State when core KPI data is missing", () => {
    render(<KpiSummary metrics={[]} locale="zh" />);
    expect(screen.getByText(/没有同时具备数值/)).toBeInTheDocument();
  });

  it("excludes unsupported data from core charts", () => {
    const report = structuredClone(competitorAnalysisDemo.dashboard.report_data!);
    report.kpis = [metric({ verification_status: "UNSUPPORTED" })];
    expect(filterReportData(report).report.kpis).toHaveLength(0);
  });

  it("keeps supported historical observations in trends", () => {
    expect(validateMetric(metric({ temporal_status: "HISTORICAL", verification_status: "SUPPORTED" }))).toEqual([]);
  });

  it("does not rank non-comparable competitor values", () => {
    const comparison = structuredClone(competitorAnalysisDemo.dashboard.comparisons![0]);
    comparison.is_comparable = false;
    comparison.comparable = false;
    comparison.comparability_issues = ["全国门店数与区域门店数不可比"];
    expect(comparisonCanRank(comparison)).toBe(false);
  });

  it("hides revision comparison for one revision and shows it for two", () => {
    const template = getDashboardTemplate("MARKET_ENTRY");
    expect(getAvailablePages(template, 1).some((page) => page.id === "revision")).toBe(false);
    expect(getAvailablePages(template, 2).some((page) => page.id === "revision")).toBe(true);
  });

  it("keeps demo numbers explicitly isolated from formal reports", () => {
    expect(competitorAnalysisDemo.dashboard.meta?.is_demo).toBe(true);
    expect(marketEntryDemo.dashboard.meta?.is_demo).toBe(true);
    expect(competitorAnalysisDemo.dashboard.metrics?.every((item) => item.is_demo === true)).toBe(true);
    expect(marketEntryDemo.dashboard.scenarios).toHaveLength(3);
  });

  it("degrades price charts from one-brand summaries to strict comparable views", () => {
    expect(priceCoverageLevel(0, false)).toBe(0);
    expect(priceCoverageLevel(1, false)).toBe(1);
    expect(priceCoverageLevel(2, false)).toBe(2);
    expect(priceCoverageLevel(3, false)).toBe(3);
    expect(priceCoverageLevel(3, true)).toBe(4);
    const productPrice = getDashboardTemplate("竞品分析").pages.find((page) => page.id === "product-price");
    expect(productPrice?.widgets[0].component).toBe("AdaptivePriceChart");
  });
});
