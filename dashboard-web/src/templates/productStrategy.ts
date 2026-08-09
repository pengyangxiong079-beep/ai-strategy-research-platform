import { finalizeTemplate, widget } from "./commonTemplate";

export const productStrategyTemplate = finalizeTemplate({
  id: "PRODUCT_STRATEGY", title: "产品战略看板",
  decisionQuestion: "产品应服务哪些用户、解决哪些需求，并形成什么差异化？",
  storyline: ["用户", "需求", "产品基准", "价值主张", "优先级", "路线图"],
  priorityMetrics: ["用户", "采用率", "留存", "价格", "满意度"],
  requiredDatasets: ["recommendations"], optionalDatasets: ["metrics", "segments", "comparisons", "matrices", "initiatives"],
  emptyStateMessage: "缺少可验证的用户、需求或产品优先级数据。",
  pages: [
    { id: "product-overview", label: "产品总览", purpose: "呈现产品战略结论。", widgets: [widget("kpis", "KpiSummary", "产品关键指标", "metrics", 1, true)] },
    { id: "user-needs", label: "用户与需求", purpose: "比较用户细分和需求满足度。", widgets: [widget("segments", "StackedCompositionChart", "用户细分", "segments", 1, true), widget("needs", "PositioningMatrix", "需求与满足度", "matrices", 2)] },
    { id: "product-benchmark", label: "产品基准", purpose: "比较功能、价格和价值。", widgets: [widget("features", "CompetitorHeatmap", "功能比较", "comparisons", 1, true), widget("price-value", "DotComparisonChart", "价格与价值", "comparisons", 2)] },
    { id: "value-proposition", label: "价值主张", purpose: "明确差异化价值主张。", widgets: [widget("opportunities", "OpportunityMatrix", "价值机会", "opportunities", 1, true)] },
    { id: "product-priorities", label: "产品优先级", purpose: "形成透明的功能优先级。", widgets: [widget("priority", "PositioningMatrix", "功能优先级", "matrices", 1, true), widget("recommendations", "RecommendationsPanel", "产品行动", "recommendations", 2, true)] },
    { id: "product-roadmap", label: "产品路线图", purpose: "连接功能、里程碑和指标。", widgets: [widget("roadmap", "InitiativeRoadmap", "产品路线图", "initiatives", 1, true)] },
  ],
});

