"""Development-only scenarios. Values and URLs are synthetic and marked is_demo."""

from datetime import date


TODAY = date.today().isoformat()
CASES = {
    "tea_competitor": {
        "analysis_type": "COMPETITOR_ANALYSIS",
        "topic": "茶颜悦色在湖南省现制茶饮市场的竞品分析",
        "industry": "现制茶饮",
        "geography": "湖南省，重点长沙",
        "analysis_date": TODAY,
        "depth": "深度版",
        "currency": "CNY",
        "competitors": ["霸王茶姬", "果呀呀", "柠季", "蜜雪冰城", "古茗", "喜茶"],
        "focus_questions": ["产品与价格", "渠道与城市覆盖", "竞争定位"],
    },
    "xpeng_germany": {"analysis_type": "MARKET_ENTRY", "topic": "小鹏汽车进入德国乘用车市场", "industry": "汽车", "geography": "德国", "analysis_date": TODAY, "depth": "深度版", "currency": "EUR", "competitors": ["Volkswagen", "Tesla", "BYD"]},
    "lufthansa_strategy": {"analysis_type": "COMPANY_STRATEGY", "topic": "Lufthansa公司战略", "industry": "航空", "geography": "德国及全球", "analysis_date": TODAY, "depth": "深度版", "currency": "EUR"},
    "ai_product_competition": {"analysis_type": "COMPETITOR_ANALYSIS", "topic": "AI产品竞品分析", "industry": "AI软件", "geography": "全球", "analysis_date": TODAY, "depth": "标准版", "currency": "USD", "competitors": ["产品A", "产品B", "产品C"]},
    "scarce_private_company": {"analysis_type": "COMPANY_STRATEGY", "topic": "数据稀缺私营企业", "industry": "自动判断", "geography": "中国", "analysis_date": TODAY, "depth": "标准版", "currency": "CNY"},
}


TEA_COMPETITOR_ACQUISITION = {
    "schema_version": "1.0",
    "search_round": 2,
    "sources": [
        {"source_id": "S_DEMO_1", "title": "演示菜单观测A", "publisher": "Demo", "url": "https://example.test/demo-menu-a", "source_type": "OFFICIAL_MENU", "source_grade": "GRADE_B", "publication_date": TODAY, "accessed_at": TODAY, "language": "zh", "geography": "长沙", "is_primary_source": True, "datasets_supported": ["price_observations", "product_portfolios"], "access_status": "SUCCESS", "access_issue": "", "is_demo": True},
        {"source_id": "S_DEMO_2", "title": "演示菜单观测B", "publisher": "Demo", "url": "https://example.test/demo-menu-b", "source_type": "PLATFORM_MENU", "source_grade": "GRADE_D", "publication_date": TODAY, "accessed_at": TODAY, "language": "zh", "geography": "长沙", "is_primary_source": False, "datasets_supported": ["price_observations"], "access_status": "SUCCESS", "access_issue": "", "is_demo": True},
    ],
    "observations": [
        {"dataset_id": "price_observations", "entity": entity, "metric": "标准门店单品价格", "product_name": f"演示产品{index}", "category": "现制茶饮", "value": value, "text_value": "", "unit": "元", "currency": "CNY", "period": TODAY, "observed_at": TODAY, "geography": "长沙", "channel": "线下标准门店", "price_type": "标准价", "value_type": "ACTUAL", "metric_definition": "长沙线下标准门店公开菜单单品标价", "source_id": source_id, "source_url": f"https://example.test/{source_id.lower()}", "evidence_excerpt": "演示Fixture，不代表真实菜单或价格。", "source_grade": grade, "verification_status": "SUPPORTED", "temporal_status": "CURRENT", "confidence": "LOW", "comparability_group": "CG_DEMO_CHANGSHA_STANDARD", "notes": "is_demo: true", "source_fact_ids": ["F1"], "is_demo": True}
        for entity, source_id, grade, base in (("茶颜悦色", "S_DEMO_1", "GRADE_B", 15), ("霸王茶姬", "S_DEMO_2", "GRADE_D", 17))
        for index, value in enumerate(range(base, base + 5), 1)
    ],
    "search_log_entries": [{"round": 1, "query": "DEMO only", "language": "zh", "candidate_sources": ["S_DEMO_1", "S_DEMO_2"], "opened_sources": ["S_DEMO_1", "S_DEMO_2"], "rejected_sources": [], "rejection_reasons": [], "extracted_observation_count": 10, "remaining_gaps": ["其余品牌数据缺失"], "is_demo": True}],
    "resolved_datasets": ["price_observations"],
    "remaining_gaps": ["果呀呀、柠季、蜜雪冰城、古茗、喜茶缺少可比价格样本"],
    "stop_reason": "演示Fixture达到预设样本边界；未进行真实网络搜索。",
    "is_demo": True,
}
