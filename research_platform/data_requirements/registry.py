"""Route normalized analysis types to deterministic dataset requirements."""

from copy import deepcopy

from dashboard.analysis_types import normalize_analysis_type
from research_platform.data_acquisition.search_vocabulary import route_industry

from .business_model import REQUIREMENTS as BUSINESS_MODEL
from .company_strategy import (
    AVIATION_OPERATING_COMPONENTS,
    AVIATION_OPERATING_METRICS,
    AVIATION_OPERATING_MINIMUMS,
    REQUIREMENTS as COMPANY_STRATEGY,
)
from .competitor_analysis import REQUIREMENTS as COMPETITOR_ANALYSIS
from .generic_strategy import REQUIREMENTS as GENERIC_STRATEGY
from .growth_strategy import REQUIREMENTS as GROWTH_STRATEGY
from .industry_analysis import REQUIREMENTS as INDUSTRY_ANALYSIS
from .investment_ma import REQUIREMENTS as INVESTMENT_MA
from .market_entry import REQUIREMENTS as MARKET_ENTRY
from .product_strategy import REQUIREMENTS as PRODUCT_STRATEGY


REGISTRY = {
    "COMPETITOR_ANALYSIS": COMPETITOR_ANALYSIS,
    "MARKET_ENTRY": MARKET_ENTRY,
    "INDUSTRY_ANALYSIS": INDUSTRY_ANALYSIS,
    "COMPANY_STRATEGY": COMPANY_STRATEGY,
    "PRODUCT_STRATEGY": PRODUCT_STRATEGY,
    "GROWTH_STRATEGY": GROWTH_STRATEGY,
    "BUSINESS_MODEL": BUSINESS_MODEL,
    "INVESTMENT_MA": INVESTMENT_MA,
    "GENERIC_STRATEGY": GENERIC_STRATEGY,
}


def get_requirement_template(analysis_type):
    normalized = normalize_analysis_type(analysis_type)
    return normalized, REGISTRY.get(normalized, GENERIC_STRATEGY)


def build_requirements(scope):
    normalized, template = get_requirement_template(scope.get("analysis_type"))
    datasets = [item.to_dict() for item in template]
    if normalized == "COMPANY_STRATEGY":
        operating = next(
            (row for row in datasets if row["dataset_id"] == "operating_metrics"), None
        )
        if operating and route_industry(scope.get("industry")) == "aviation":
            operating["required_metrics"] = list(AVIATION_OPERATING_METRICS)
            operating["dashboard_components"] = list(AVIATION_OPERATING_COMPONENTS)
            operating["component_minimums"] = deepcopy(AVIATION_OPERATING_MINIMUMS)
    if normalized == "GENERIC_STRATEGY":
        questions = scope.get("focus_questions") or []
        sections = scope.get("required_sections") or []
        for index, label in enumerate([*questions, *sections], 1):
            datasets.append({
                "dataset_id": f"dynamic_requirement_{index}",
                "priority": "IMPORTANT",
                "purpose": f"为范围问题提供证据：{label}",
                "required_fields": ["entity", "metric", "text_value", "source_id"],
                "minimum_entities": 1,
                "minimum_observations_per_entity": 1,
                "minimum_periods": 1,
                "required_comparability_fields": [],
                "preferred_sources": ["原始或官方来源"],
                "fallback_sources": ["可信二手来源"],
                "proxy_allowed": True,
                "dashboard_components": [],
                "component_minimums": {},
            })
    return {
        "schema_version": "1.0",
        "analysis_type": normalized,
        "topic": scope.get("topic", ""),
        "industry": scope.get("industry", ""),
        "geography": scope.get("geography", ""),
        "analysis_date": scope.get("analysis_date", ""),
        "datasets": deepcopy(datasets),
    }
