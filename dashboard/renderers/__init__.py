from .common import (
    CompetitorComparisonRenderer,
    DataGapRenderer,
    EvidenceQualityRenderer,
    KpiSummaryRenderer,
    MarketCompositionRenderer,
    RiskOpportunityRenderer,
    RoadmapRenderer,
    TimeTrendRenderer,
)


RENDERERS = {
    "kpi_summary": KpiSummaryRenderer,
    "time_trend": TimeTrendRenderer,
    "market_composition": MarketCompositionRenderer,
    "competitor_comparison": CompetitorComparisonRenderer,
    "risk_opportunity": RiskOpportunityRenderer,
    "strategy_roadmap": RoadmapRenderer,
    "evidence_quality": EvidenceQualityRenderer,
    "data_gaps": DataGapRenderer,
}
