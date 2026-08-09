"""Canonical analysis-type identifiers shared by dashboard compilation."""

from __future__ import annotations

import re
from enum import Enum


class AnalysisType(str, Enum):
    COMPETITOR_ANALYSIS = "COMPETITOR_ANALYSIS"
    MARKET_ENTRY = "MARKET_ENTRY"
    INDUSTRY_ANALYSIS = "INDUSTRY_ANALYSIS"
    COMPANY_STRATEGY = "COMPANY_STRATEGY"
    PRODUCT_STRATEGY = "PRODUCT_STRATEGY"
    GROWTH_STRATEGY = "GROWTH_STRATEGY"
    BUSINESS_MODEL = "BUSINESS_MODEL"
    INVESTMENT_MA = "INVESTMENT_MA"
    GENERIC_STRATEGY = "GENERIC_STRATEGY"


ALIASES = {
    AnalysisType.COMPETITOR_ANALYSIS: {
        "竞品分析", "竞争分析", "竞争对手分析", "竞品比较", "竞争格局分析",
    },
    AnalysisType.MARKET_ENTRY: {
        "市场进入分析", "市场进入", "区域进入分析", "国际市场进入", "海外市场进入",
    },
    AnalysisType.INDUSTRY_ANALYSIS: {"行业分析", "行业研究", "产业分析", "产业研究"},
    AnalysisType.COMPANY_STRATEGY: {
        "公司战略", "公司分析", "企业战略", "战略诊断", "公司战略分析",
    },
    AnalysisType.PRODUCT_STRATEGY: {
        "产品分析", "产品战略", "产品竞争力分析", "产品战略分析",
    },
    AnalysisType.GROWTH_STRATEGY: {"增长战略", "增长机会分析", "增长战略分析"},
    AnalysisType.BUSINESS_MODEL: {"商业模式分析", "盈利模式分析", "商业模式"},
    AnalysisType.INVESTMENT_MA: {
        "投资分析", "并购分析", "投资并购分析", "投资与并购", "investmentma",
    },
    AnalysisType.GENERIC_STRATEGY: {"通用战略", "战略分析", "综合分析"},
}


def _key(value) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "")).lower()


ALIAS_LOOKUP = {
    _key(alias): analysis_type.value
    for analysis_type, aliases in ALIASES.items()
    for alias in {*aliases, analysis_type.value}
}


def normalize_analysis_type(value) -> str:
    """Return a stable enum value; unknown input safely falls back to generic."""
    return ALIAS_LOOKUP.get(_key(value), AnalysisType.GENERIC_STRATEGY.value)

