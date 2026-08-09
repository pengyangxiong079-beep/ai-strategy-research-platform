import { finalizeTemplate, widget } from "./commonTemplate";

export const competitorAnalysisTemplate = finalizeTemplate({
  id: "COMPETITOR_ANALYSIS",
  title: "竞品分析战略看板",
  decisionQuestion: "我们与哪些竞争者竞争，相对优势、劣势和差异化机会在哪里？",
  storyline: ["竞争范围", "竞争者分组", "市场定位", "产品与价格", "渠道与区域", "能力差距", "战略机会", "行动建议"],
  priorityMetrics: ["竞品数量", "可比指标覆盖率", "价格", "渠道覆盖", "市场位置"],
  requiredDatasets: ["observations", "recommendations"],
  optionalDatasets: ["metrics", "comparisons", "matrices", "geographies", "opportunities", "initiatives", "data_coverage"],
  comparisonRules: [{ fields: ["geography", "period", "unit", "currency", "metric_definition", "channel_scope", "entity_scope"], behavior: "NO_RANKING", message: "口径不一致时仅展示并列信息，不生成排名。" }],
  emptyStateMessage: "缺少统一口径的竞品结构化数据；不会生成虚假排名或定位。",
  pages: [
    { id: "competition-overview", label: "竞争总览", labelEn: "Competition overview", purpose: "界定竞争范围并识别相对位置。", widgets: [widget("competition-kpis", "KpiSummary", "竞争判断摘要", "metrics", 1, true), widget("positioning", "PositioningMatrix", "竞争定位", "matrices", 2, true), widget("core-comparison", "DotComparisonChart", "核心指标比较", "comparisons", 3, true), widget("capability-heatmap", "CompetitorHeatmap", "竞争能力比较", "comparisons", 4)] },
    { id: "product-price", label: "产品与价格", labelEn: "Product and price", purpose: "比较产品组合、价格带和可验证差异。", widgets: [widget("price-band", "AdaptivePriceChart", "产品价格覆盖与比较", "observations", 1, true), widget("product-features", "CompetitorHeatmap", "产品与功能覆盖", "comparisons", 2)] },
    { id: "channel-geography", label: "渠道与区域", labelEn: "Channel and geography", purpose: "检查城市、渠道和区域覆盖差异。", widgets: [widget("geography", "GeographicMap", "区域覆盖", "geographies", 1, true), widget("channel-mix", "StackedCompositionChart", "渠道结构", "segments", 2), widget("store-coverage", "DotComparisonChart", "可比覆盖指标", "comparisons", 3)] },
    { id: "competitive-gaps", label: "竞争差距", labelEn: "Competitive gaps", purpose: "识别能力短板、壁垒和可差异化空间。", widgets: [widget("gap-matrix", "PositioningMatrix", "重要性与表现", "matrices", 1, true), widget("opportunity", "OpportunityMatrix", "差异化机会", "opportunities", 2, true)] },
    { id: "competitive-actions", label: "竞争行动", labelEn: "Competitive actions", purpose: "形成防守、差异化与进攻行动。", widgets: [widget("recommendations", "RecommendationsPanel", "竞争行动建议", "recommendations", 1, true), widget("roadmap", "InitiativeRoadmap", "行动路线图", "initiatives", 2)] },
  ],
});
