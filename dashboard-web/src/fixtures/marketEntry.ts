import { demoBundle, demoMetric } from "./demoFactory";

export const marketEntryDemo = (() => {
  const value = demoBundle("MARKET_ENTRY", "小鹏汽车进入德国乘用车市场");
  const metrics = [demoMetric("demo_market_size", "乘用车市场规模", 100, "演示指数", { geography: "德国", period: "2026演示期" })];
  value.dashboard.metrics = metrics;
  value.dashboard.risks = [{ item_id: "demo_regulation", label: "政策监管（演示）", description: "仅验证风险矩阵。", severity: "HIGH", source_fact_ids: ["F9001"] }];
  value.dashboard.recommendations = [{ item_id: "demo_entry", recommendation_id: "demo_entry", label: "分阶段试点（演示）", title: "分阶段试点（演示）", description: "仅验证进入建议。", rationale: "演示依据", priority: "HIGH", source_fact_ids: ["F9001"] }];
  value.dashboard.scenarios = ["保守", "基准", "乐观"].map((label, index) => ({ scenario_id: `demo_${index}`, label: `${label}情景（演示）`, assumptions: ["开发测试假设"], source_fact_ids: ["F9001"], points: [2027, 2028, 2029].map((year, point) => demoMetric(`demo_${index}_${year}`, label, 70 + index * 15 + point * 5, "演示指数", { geography: "德国", period: `${year}演示`, value_type: "SCENARIO", temporal_status: "FUTURE_PLAN" })) }));
  value.dashboard.initiatives = [2027, 2028, 2029].map((year) => ({ item_id: `demo_${year}`, label: `${year}里程碑（演示）`, start: String(year), end: String(year), status: "DEMO", description: "仅验证路线图", source_fact_ids: ["F9001"], is_demo: true }));
  value.dashboard.report_data!.kpis = metrics;
  value.dashboard.report_data!.risks = value.dashboard.risks;
  value.dashboard.report_data!.recommendations = value.dashboard.recommendations;
  value.dashboard.report_data!.roadmap = value.dashboard.initiatives;
  return value;
})();
