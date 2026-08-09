from .types import COMMON_FALLBACK, COMMON_PRIMARY, requirement


REQUIREMENTS = (
    requirement("competitor_profiles", "CRITICAL", "界定竞争者、业务范围和可比边界", entities=3, primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK, components=("CompetitorProfileTable",)),
    requirement("product_portfolios", "CRITICAL", "比较目标公司与竞品的产品组合", fields=("entity", "product_name", "category", "geography", "period", "source_id"), entities=3, per_entity=3, primary=("官方产品页", "官方菜单", "官方点单公开页面"), fallback=COMMON_FALLBACK, components=("ProductPortfolioChart", "ProductFeatureHeatmap")),
    requirement("price_observations", "CRITICAL", "比较目标公司和竞品的价格带", fields=("entity", "product_name", "category", "value", "currency", "geography", "period", "source_id"), entities=3, per_entity=5, comparable=("geography", "period", "currency", "channel", "price_type"), primary=("官方价格表", "官方菜单", "官方点单公开页面"), fallback=("商场门店菜单", "外卖平台公开页面", "可信媒体实测", "带日期的价格报道"), proxy=True, components=("PriceBandChart", "ProductPriceDotPlot", "PricePositioningMatrix", "PriceRanking"), component_minimums={"PriceBandChart": {"entities": 1}, "ProductPriceDotPlot": {"entities": 2, "requires_comparability": True}, "PricePositioningMatrix": {"entities": 3, "requires_comparability": True}, "PriceRanking": {"entities": 3, "comparability_rate": 0.85, "requires_comparability": True}}),
    requirement("positioning", "CRITICAL", "形成有依据的竞争定位", fields=("entity", "metric", "value", "metric_definition", "source_id"), entities=3, per_entity=2, primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK, components=("PositioningMatrix",)),
    requirement("channel_or_store_coverage", "CRITICAL", "比较渠道、门店和城市覆盖", fields=("entity", "metric", "value", "unit", "geography", "period", "channel", "source_id"), entities=3, comparable=("geography", "period", "unit", "channel"), primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK, components=("GeographicMap", "StoreCoverageDotPlot")),
    requirement("customer_segments", "IMPORTANT", "识别各品牌主要客户群", proxy=True),
    requirement("product_features", "IMPORTANT", "比较产品卖点和功能覆盖", entities=2, per_entity=3, proxy=True, components=("ProductFeatureHeatmap",)),
    requirement("marketing_activity", "IMPORTANT", "比较可观察营销活动", proxy=True),
    requirement("financial_or_operational_metrics", "IMPORTANT", "比较可验证经营指标", entities=2, primary=COMMON_PRIMARY),
    requirement("capabilities", "IMPORTANT", "识别能力差距及可防守壁垒", entities=2, proxy=True, components=("CapabilityHeatmap",)),
    requirement("social_media_metrics", "OPTIONAL", "补充公开社交媒体代理指标", proxy=True),
    requirement("customer_reviews", "OPTIONAL", "补充有样本说明的消费者认知", proxy=True),
    requirement("unit_economics", "OPTIONAL", "在有可靠数据时比较单位经济性"),
    requirement("supply_chain", "OPTIONAL", "识别供应链差异和风险", proxy=True),
)
