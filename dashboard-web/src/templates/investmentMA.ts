import { finalizeTemplate, widget } from "./commonTemplate";

export const investmentMATemplate = finalizeTemplate({
  id: "INVESTMENT_MA", title: "投资并购看板",
  decisionQuestion: "目标公司是否值得投资或收购，价值、协同和风险分别是什么？",
  storyline: ["投资命题", "经营表现", "市场位置", "估值", "协同", "风险", "交易情景"],
  priorityMetrics: ["收入", "利润", "估值", "协同", "回报"],
  requiredDatasets: ["metrics", "risks"], optionalDatasets: ["time_series", "comparisons", "scenarios", "initiatives"],
  emptyStateMessage: "缺少支持投资判断的历史表现、估值或风险数据。",
  pages: [
    { id: "investment-overview", label: "投资总览", purpose: "呈现投资命题及其证据边界。", widgets: [widget("kpis", "KpiSummary", "投资关键指标", "metrics", 1, true)] },
    { id: "business-performance", label: "经营表现", purpose: "区分历史事实、指引与预测。", widgets: [widget("trend", "TimeSeriesChart", "收入与利润趋势", "time_series", 1, true)] },
    { id: "market-position", label: "市场位置", purpose: "在可比口径下比较市场位置。", widgets: [widget("comparison", "DotComparisonChart", "可比公司", "comparisons", 1, true)] },
    { id: "valuation", label: "估值", purpose: "呈现估值区间及假设，不输出单点确定性结论。", widgets: [widget("valuation-range", "HorizontalBarChart", "估值区间", "comparisons", 1, true)] },
    { id: "synergies", label: "协同", purpose: "拆解协同来源并说明实现条件。", widgets: [widget("synergy", "WaterfallChart", "协同拆解", "metrics", 1, true)] },
    { id: "deal-risks", label: "风险", purpose: "识别交易、整合和执行风险。", widgets: [widget("risk", "RiskMatrix", "交易风险", "risks", 1, true)] },
    { id: "deal-scenarios", label: "交易情景", purpose: "比较回报情景和整合路线图。", widgets: [widget("scenario", "ScenarioChart", "回报情景", "scenarios", 1, true), widget("roadmap", "InitiativeRoadmap", "整合路线图", "initiatives", 2)] },
  ],
});

