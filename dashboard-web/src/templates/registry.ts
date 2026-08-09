import type { AnalysisType } from "../types";
import { businessModelTemplate } from "./businessModel";
import { companyStrategyTemplate } from "./companyStrategy";
import { competitorAnalysisTemplate } from "./competitorAnalysis";
import { genericStrategyTemplate } from "./genericStrategy";
import { growthStrategyTemplate } from "./growthStrategy";
import { industryAnalysisTemplate } from "./industryAnalysis";
import { investmentMATemplate } from "./investmentMA";
import { marketEntryTemplate } from "./marketEntry";
import { productStrategyTemplate } from "./productStrategy";
import type { DashboardTemplate } from "./types";

const aliases: Record<string, AnalysisType> = {};
const aliasGroups: Record<AnalysisType, string[]> = {
  COMPETITOR_ANALYSIS: ["竞品分析", "竞争分析", "竞争对手分析", "竞品比较", "竞争格局分析"],
  MARKET_ENTRY: ["市场进入分析", "市场进入", "区域进入分析", "国际市场进入", "海外市场进入"],
  INDUSTRY_ANALYSIS: ["行业分析", "行业研究", "产业分析", "产业研究"],
  COMPANY_STRATEGY: ["公司战略", "公司分析", "企业战略", "战略诊断", "公司战略分析"],
  PRODUCT_STRATEGY: ["产品分析", "产品战略", "产品竞争力分析", "产品战略分析"],
  GROWTH_STRATEGY: ["增长战略", "增长机会分析", "增长战略分析"],
  BUSINESS_MODEL: ["商业模式分析", "盈利模式分析", "商业模式"],
  INVESTMENT_MA: ["投资分析", "并购分析", "投资并购分析", "投资与并购", "investmentma"],
  GENERIC_STRATEGY: ["通用战略", "战略分析", "综合分析"],
};

function key(value: unknown) {
  return String(value ?? "").toLowerCase().replace(/[^0-9a-zA-Z\u4e00-\u9fff]+/g, "");
}

Object.entries(aliasGroups).forEach(([type, values]) => {
  [type, ...values].forEach((value) => { aliases[key(value)] = type as AnalysisType; });
});

export function normalizeAnalysisType(value: unknown): AnalysisType {
  return aliases[key(value)] ?? "GENERIC_STRATEGY";
}

export const dashboardTemplates: Record<AnalysisType, DashboardTemplate> = {
  COMPETITOR_ANALYSIS: competitorAnalysisTemplate,
  MARKET_ENTRY: marketEntryTemplate,
  INDUSTRY_ANALYSIS: industryAnalysisTemplate,
  COMPANY_STRATEGY: companyStrategyTemplate,
  PRODUCT_STRATEGY: productStrategyTemplate,
  GROWTH_STRATEGY: growthStrategyTemplate,
  BUSINESS_MODEL: businessModelTemplate,
  INVESTMENT_MA: investmentMATemplate,
  GENERIC_STRATEGY: genericStrategyTemplate,
};

export function getDashboardTemplate(value: unknown): DashboardTemplate {
  return dashboardTemplates[normalizeAnalysisType(value)];
}

export function getAvailablePages(template: DashboardTemplate, revisionCount: number) {
  return template.pages.filter((page) => page.id !== "revision" || revisionCount >= 2);
}
