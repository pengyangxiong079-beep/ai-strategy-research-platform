from .types import COMMON_FALLBACK, COMMON_PRIMARY, requirement

REQUIREMENTS = tuple(
    requirement(dataset, "CRITICAL", purpose, entities=entities, periods=periods, primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK, proxy=proxy, components=components)
    for dataset, purpose, entities, periods, proxy, components in (
        ("market_size", "量化目标市场规模及口径", 1, 2, False, ("MarketSizeChart",)),
        ("market_growth", "验证历史与预测增长", 1, 3, False, ("TimeSeriesChart",)),
        ("market_segments", "识别可进入的细分市场", 2, 1, False, ("SegmentCompositionChart",)),
        ("competitors", "识别本地主要竞争者", 3, 1, False, ("CompetitorComparison",)),
        ("regulation", "识别准入和运营监管要求", 1, 1, False, ("RegulatoryTimeline",)),
        ("entry_barriers", "评估准入壁垒", 1, 1, True, ("EntryBarrierHeatmap",)),
        ("customer_demand", "验证目标客户需求", 2, 1, True, ("DemandChart",)),
    )
) + tuple(requirement(x, "IMPORTANT", f"市场进入所需的{x}数据", proxy=x in {"local_partners", "entry_costs"}) for x in ("prices", "channels", "geographic_distribution", "taxes_and_tariffs", "supply_chain", "local_partners", "entry_costs")) + tuple(requirement(x, "OPTIONAL", f"补充{x}数据", proxy=True) for x in ("detailed_unit_economics", "consumer_review_data", "acquisition_targets"))
