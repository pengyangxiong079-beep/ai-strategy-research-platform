import { describe, expect, it } from "vitest";
import { automotiveTemplate } from "../industry-templates/automotive";
import { generalTemplate } from "../industry-templates/general";
import { t } from "../lib/i18n";
import { compareBundles } from "../lib/diff";
import { loadBundle } from "../lib/loader";
import { bundle, catalog } from "./fixtures";

describe("platform behavior", () => {
  it("loads the automotive configuration without duplicated page code", () => {
    expect(automotiveTemplate.pages.map((page) => page.id)).toEqual(generalTemplate.pages.map((page) => page.id));
    expect(automotiveTemplate.pages.find((page) => page.id === "market")?.metricPatterns).toContain("BEV");
  });

  it("supports Chinese and English labels", () => {
    expect(t("zh", "overview")).toBe("总览");
    expect(t("en", "overview")).toBe("Overview");
  });

  it("switches revisions from embedded offline data", async () => {
    const left = bundle("rev_001");
    const right = bundle("rev_002");
    window.__DASHBOARD_EMBEDDED__ = {
      catalog: catalog(),
      reports: { "test-run::rev_001": left, "test-run::rev_002": right },
      selected_key: "test-run::rev_002",
    };
    expect((await loadBundle("unused", "test-run", "rev_002")).revision).toBe("rev_002");
    delete window.__DASHBOARD_EMBEDDED__;
  });

  it("reports KPI, quality, risk and recommendation field changes", () => {
    const left = bundle("rev_001");
    const right = bundle("rev_002", "WARN");
    right.dashboard.report_data!.kpis[0].value = 600000;
    right.dashboard.report_data!.risks.push({ item_id: "RISK1", label: "测试风险", description: "说明", source_fact_ids: ["F1"] });
    right.dashboard.report_data!.recommendations.push({ item_id: "REC1", label: "建议", description: "说明", source_fact_ids: ["F1"] });
    const paths = compareBundles(left, right).map((row) => row.path);
    expect(paths.some((path) => path.endsWith("kpis[0].value"))).toBe(true);
    expect(paths).toContain("quality");
    expect(paths.some((path) => path.includes("risks"))).toBe(true);
    expect(paths.some((path) => path.includes("recommendations"))).toBe(true);
  });
});
