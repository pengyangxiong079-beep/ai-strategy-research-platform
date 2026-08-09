import { demoBundle, demoMetric } from "./demoFactory";

export const competitorAnalysisDemo = (() => {
  const value = demoBundle("COMPETITOR_ANALYSIS", "茶颜悦色在湖南省现制茶饮市场的竞品分析");
  const metrics = [
    demoMetric("demo_competitors", "核心竞品数量", 4, "家", { geography: "湖南省" }),
    demoMetric("demo_comparable_coverage", "可比指标覆盖率", 75, "%", { geography: "湖南省" }),
  ];
  const comparisons = [{
    comparison_id: "demo_price", metric_id: "standard_drink_price", entities: ["茶颜悦色", "竞品A", "竞品B"], metric: "标准门店代表产品价格",
    geography: "湖南省", period: "2026演示期", unit: "元/杯", currency: "CNY", comparable: true, is_comparable: true,
    comparability_issues: [], comparison_basis: "演示：同地区、同期间、标准门店价", ranking_claim: false,
    source_fact_ids: ["F9001"], values: [{ entity: "茶颜悦色", value: 18 }, { entity: "竞品A", value: 20 }, { entity: "竞品B", value: 16 }], is_demo: true,
  }];
  value.dashboard.metrics = metrics;
  value.dashboard.comparisons = comparisons;
  value.dashboard.matrices = [{ matrix_id: "demo_position", label: "竞争定位（演示）", points: [
    { item_id: "brand", label: "茶颜悦色", x: 7, y: 8, x_label: "价格水平", y_label: "品牌差异化", methodology: "演示评分：开发测试固定值", source_fact_ids: ["F9001"], is_analyst_judgment: true },
    { item_id: "peer", label: "竞品A", x: 8, y: 6, x_label: "价格水平", y_label: "品牌差异化", methodology: "演示评分：开发测试固定值", source_fact_ids: ["F9001"], is_analyst_judgment: true },
  ] }];
  value.dashboard.geographies = [{ geography_id: "changsha", label: "长沙（演示）", value: 100, unit: "演示覆盖点", longitude: 112.94, latitude: 28.23, period: "2026演示期", source_fact_ids: ["F9001"], is_demo: true }];
  value.dashboard.opportunities = [{ item_id: "demo_gap", label: "演示差异化机会", description: "仅验证竞争差距页面。", priority: "HIGH", source_fact_ids: ["F9001"] }];
  value.dashboard.recommendations = [{ item_id: "demo_action", recommendation_id: "demo_action", label: "演示竞争行动", title: "演示竞争行动", description: "仅验证行动卡片。", rationale: "演示依据", priority: "HIGH", source_fact_ids: ["F9001"] }];
  value.dashboard.report_data!.kpis = metrics;
  value.dashboard.report_data!.competitor_comparisons = comparisons;
  value.dashboard.report_data!.opportunities = value.dashboard.opportunities;
  value.dashboard.report_data!.recommendations = value.dashboard.recommendations;
  return value;
})();

