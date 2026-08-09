export type Language = "zh" | "en";

const messages = {
  zh: {
    overview: "总览",
    market: "市场",
    competition: "竞争",
    risk: "风险与机会",
    roadmap: "战略路线图",
    evidence: "证据质量",
    revision: "版本比较",
    noData: "数据不足",
    draft: "草稿看板，报告尚未通过质量检查",
    warn: "部分数据待核验",
  },
  en: {
    overview: "Overview",
    market: "Market",
    competition: "Competition",
    risk: "Risk & opportunity",
    roadmap: "Strategy roadmap",
    evidence: "Evidence quality",
    revision: "Revision comparison",
    noData: "Insufficient data",
    draft: "Draft dashboard — the report has not passed quality checks",
    warn: "Some data requires verification",
  },
} as const;

export function t(language: Language, key: keyof typeof messages.zh): string {
  return messages[language][key];
}
