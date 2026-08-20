import json
import tempfile
import unittest
from pathlib import Path

from dashboard.analysis_types import normalize_analysis_type
from research_platform.data_requirements import build_requirements
from research_platform.data_acquisition.search_vocabulary import build_dataset_queries, route_industry
from research_platform.fixtures import CASES, TEA_COMPETITOR_ACQUISITION
from research_platform.normalization import (
    dedupe_observations,
    dedupe_sources,
    normalize_currency,
    normalize_unit,
    normalize_observation,
    canonicalize_entity,
    normalize_source,
)
from research_platform.pipeline import (
    apply_observation_verification,
    data_files,
    initialize_data_pipeline,
    process_acquisition_response,
)
from research_platform.schemas import DataSchemaError, validate_payload
from research_platform.search import search_budget, search_languages
from research_platform.search import build_search_plan
from research_platform.sufficiency import build_gap_search_plan, evaluate_sufficiency


class DataPipelineTests(unittest.TestCase):
    def test_requirement_registry_routes_all_analysis_types(self):
        expected = {
            "COMPETITOR_ANALYSIS", "MARKET_ENTRY", "INDUSTRY_ANALYSIS",
            "COMPANY_STRATEGY", "PRODUCT_STRATEGY", "GROWTH_STRATEGY",
            "BUSINESS_MODEL", "INVESTMENT_MA", "GENERIC_STRATEGY",
        }
        for analysis_type in expected:
            payload = build_requirements({**CASES["tea_competitor"], "analysis_type": analysis_type})
            self.assertEqual(payload["analysis_type"], analysis_type)
            self.assertTrue(payload["datasets"])
            validate_payload("requirements", payload)

    def test_chinese_alias_and_unknown_routing(self):
        self.assertEqual(normalize_analysis_type("竞争对手分析"), "COMPETITOR_ANALYSIS")
        self.assertEqual(normalize_analysis_type("国际市场进入"), "MARKET_ENTRY")
        self.assertEqual(normalize_analysis_type("完全未知"), "GENERIC_STRATEGY")

    def test_additional_case_requirements_cover_expected_evidence(self):
        cases = {
            "xpeng_germany": {"market_size", "competitors", "regulation", "customer_demand"},
            "lufthansa_strategy": {"financial_time_series", "business_segments", "geographic_structure"},
            "ai_product_competition": {"competitor_profiles", "product_portfolios", "price_observations"},
            "scarce_private_company": {"company_profile", "financial_time_series", "products_or_services"},
        }
        for case_id, expected in cases.items():
            dataset_ids = {item["dataset_id"] for item in build_requirements(CASES[case_id])["datasets"]}
            self.assertTrue(expected <= dataset_ids)

    def test_company_strategy_airline_metrics_are_industry_specific(self):
        industrial = build_requirements({
            "analysis_type": "COMPANY_STRATEGY",
            "industry": "energy management and industrial automation",
        })
        industrial_operating = next(
            row for row in industrial["datasets"] if row["dataset_id"] == "operating_metrics"
        )
        self.assertEqual(industrial_operating["required_metrics"], [])
        self.assertEqual(industrial_operating["dashboard_components"], [])

        aviation = build_requirements({
            "analysis_type": "COMPANY_STRATEGY", "industry": "aviation",
        })
        aviation_operating = next(
            row for row in aviation["datasets"] if row["dataset_id"] == "operating_metrics"
        )
        self.assertIn("passenger_count", aviation_operating["required_metrics"])
        self.assertIn("OperatingMetricsTimeSeries", aviation_operating["dashboard_components"])

    def test_observation_schema_validation(self):
        row = dict(TEA_COMPETITOR_ACQUISITION["observations"][0])
        row.setdefault("observation_id", "O1")
        validate_payload("observations", {"schema_version": "1.0", "observations": [row]})
        with self.assertRaises(DataSchemaError):
            validate_payload("observations", {"schema_version": "1.0", "observations": [{"value": 1}]})

    def test_source_url_and_observation_deduplication(self):
        source = TEA_COMPETITOR_ACQUISITION["sources"][0]
        duplicate = {**source, "source_id": "OTHER", "url": source["url"] + "/?utm_source=test"}
        sources = dedupe_sources([source, duplicate])
        self.assertEqual(len(sources), 1)
        observation = TEA_COMPETITOR_ACQUISITION["observations"][0]
        self.assertEqual(len(dedupe_observations([observation, dict(observation)], sources)), 1)

    def test_unit_and_currency_normalization(self):
        self.assertEqual(normalize_currency("人民币"), "CNY")
        self.assertEqual(normalize_currency("€"), "EUR")
        self.assertEqual(normalize_unit("stores"), "家")
        self.assertEqual(canonicalize_entity("XPENG Motors Ltd", ["XPENG Motors"]), "XPENG Motors")

    def test_search_budget_and_multilingual_localization(self):
        self.assertEqual(search_budget("标准版")["max_gap_rounds"], 1)
        self.assertEqual(search_budget("深度版")["max_gap_rounds"], 2)
        self.assertEqual(search_languages("德国"), ["de", "en", "zh"])
        self.assertEqual(search_languages("湖南省长沙市"), ["zh", "en"])
        requirements = build_requirements(CASES["xpeng_germany"])
        plan = build_search_plan(CASES["xpeng_germany"], requirements)
        query_text = "\n".join(item["query"] for item in plan["queries"])
        self.assertIn("KBA Neuzulassungen", query_text)
        self.assertIn("XPeng Deutschland Preise", query_text)

    def test_deep_competitor_plan_covers_required_cohort_with_unique_query_ids(self):
        scope = {
            "analysis_type": "竞品分析", "analysis_type_id": "COMPETITOR_ANALYSIS",
            "topic": "Alpha Cloud与主要竞品分析", "target_entity": "Alpha Cloud",
            "industry": "software SaaS", "geography": "全球", "analysis_date": "2026-08-20",
            "depth": "深度版", "competitors": ["Beta Cloud", "Gamma Cloud", "Delta Cloud"],
        }
        plan = build_search_plan(scope, build_requirements(scope))
        critical = [row for row in plan["coverage_targets"] if row["priority"] == "CRITICAL"]
        self.assertTrue(critical)
        self.assertTrue(all(row["expected_entities"] == ["Alpha Cloud", "Beta Cloud", "Gamma Cloud"] for row in critical))
        self.assertTrue(all(row["coverage_complete"] for row in critical))
        query_ids = [row["query_id"] for row in plan["queries"]]
        self.assertEqual(len(query_ids), len(set(query_ids)))

    def test_competitor_sufficiency_uses_required_cohort_not_every_extra_peer(self):
        scope = {
            "analysis_type": "COMPETITOR_ANALYSIS", "topic": "Alpha竞品分析",
            "target_entity": "Alpha", "competitors": ["Beta", "Gamma", "Delta"],
        }
        requirements = {"analysis_type": "COMPETITOR_ANALYSIS", "datasets": [{
            "dataset_id": "competitor_profiles", "priority": "CRITICAL",
            "required_fields": ["entity", "metric", "text_value", "source_id"],
            "minimum_entities": 3, "minimum_observations_per_entity": 1,
            "minimum_periods": 0, "required_comparability_fields": [],
            "dashboard_components": [],
        }]}
        source = {"source_id": "S1", "source_grade": "GRADE_A"}
        observations = [{
            "observation_id": f"O{index}", "dataset_id": "competitor_profiles",
            "entity": entity, "metric": "business_scope", "text_value": "verified profile",
            "source_id": "S1", "verification_status": "SUPPORTED",
        } for index, entity in enumerate(("Alpha Inc", "Beta", "Gamma"), 1)]
        result = evaluate_sufficiency(requirements, observations, [source], scope)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["status"], "PASS")
        self.assertEqual(dataset["expected_entities"], ["Alpha", "Beta", "Gamma"])
        self.assertEqual(dataset["missing_entities"], [])

    def test_empty_dataset_gap_ids_remain_unique_after_entity_gaps(self):
        scope = {
            "analysis_type": "COMPETITOR_ANALYSIS", "target_entity": "Alpha",
            "competitors": ["Beta", "Gamma"],
        }
        requirements = {"analysis_type": "COMPETITOR_ANALYSIS", "datasets": [{
            "dataset_id": "competitor_profiles", "priority": "CRITICAL",
            "required_fields": ["entity", "source_id"], "minimum_entities": 3,
            "minimum_observations_per_entity": 1, "minimum_periods": 0,
            "required_comparability_fields": [], "dashboard_components": [],
        }]}
        dataset = evaluate_sufficiency(requirements, [], [], scope)["datasets"][0]
        gap_ids = [row["gap_id"] for row in dataset["gaps"]]
        self.assertEqual(len(gap_ids), len(set(gap_ids)))

    def test_scope_topic_routes_auto_detected_food_beverage_queries(self):
        scope = {
            "analysis_type": "行业分析", "topic": "中国咖啡及茶饮行业",
            "industry": "自动判断", "geography": "中国", "analysis_date": "2026-08-09",
        }
        queries = build_dataset_queries(scope, "market_size", limit=5)
        query_text = "\n".join(item["query"] for item in queries)
        self.assertIn("China freshly made coffee and tea market", query_text)
        self.assertTrue("market size" in query_text or "市场规模" in query_text)
        self.assertNotIn("price data", query_text.lower())

    def test_successful_source_synonyms_and_execution_evidence_are_normalized(self):
        self.assertEqual(normalize_source({"access_status": "OPENED"})["access_status"], "SUCCESS")
        scope = CASES["tea_competitor"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            initialize_data_pipeline(output, scope)
            payload = json.loads(json.dumps(TEA_COMPETITOR_ACQUISITION))
            payload["sources"] = [{**row, "access_status": "ACCEPTED"} for row in payload["sources"]]
            payload["search_log_entries"] = [{
                "query": "official menu", "language": "zh",
                "opened_sources": [payload["sources"][0]["url"]],
                "accepted_sources": [payload["sources"][0]["url"]],
                "extracted_observation_count": 1,
            }]
            processed = process_acquisition_response(output, scope, payload)
            self.assertTrue(all(row["access_status"] == "SUCCESS" for row in processed["sources"]))
            self.assertEqual(processed["search_log"]["entries"][0]["execution_status"], "COMPLETED")

    def test_exact_required_metric_reconciles_misclassified_dataset(self):
        scope = {
            "analysis_type": "行业分析", "topic": "中国咖啡及茶饮行业",
            "industry": "自动判断", "geography": "中国", "analysis_date": "2026-08-09",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            initialize_data_pipeline(output, scope)
            source = {
                "source_id": "S_DEF", "title": "Industry definition", "publisher": "Association",
                "url": "https://example.test/definition", "source_type": "INDUSTRY_ASSOCIATION",
                "source_grade": "GRADE_B", "publication_date": "2026-01-01", "accessed_at": "2026-08-09",
                "language": "zh", "geography": "China", "is_primary_source": True,
                "datasets_supported": ["industry_definition"], "access_status": "SUCCESS", "access_issue": "",
            }
            observation = {
                "dataset_id": "market_segments", "entity": "中国现制饮品市场",
                "metric": "industry_definition", "metric_id": "industry_definition",
                "text_value": "门店现场制作的非酒精饮品。", "geography": "China",
                "period": "2026", "source_id": "S_DEF",
            }
            result = process_acquisition_response(output, scope, {
                "sources": [source], "observations": [observation], "search_round": 1,
            })
            self.assertEqual(result["observations"][0]["dataset_id"], "industry_definition")
            definition = next(item for item in result["sufficiency"]["datasets"] if item["dataset_id"] == "industry_definition")
            self.assertEqual(definition["observation_count"], 1)

    def test_lufthansa_queries_use_aviation_vocabulary_without_global_price_suffix(self):
        scope = {
            **CASES["lufthansa_strategy"],
            "topic": "汉莎航空集团盈利能力、运营效率与业务组合战略分析",
            "industry": "航空运输与航空服务",
            "geography": "欧洲及全球航空市场；重点分析德国、欧洲航线和主要洲际航线",
            "analysis_date": "2026-08-09",
            "depth": "深度版",
        }
        plan = build_search_plan(scope, build_requirements(scope))
        query_text = "\n".join(item["query"] for item in plan["queries"])
        self.assertEqual(route_industry(scope["industry"]), "aviation")
        self.assertNotIn(scope["topic"], query_text)
        self.assertNotIn(scope["geography"], query_text)
        self.assertNotIn("price data", query_text.lower())
        self.assertIn("Lufthansa RASK CASK Yield", query_text)
        self.assertIn("Passagiere Flüge Sitzladefaktor", query_text)
        price_queries = build_dataset_queries(scope, "prices")
        self.assertTrue(any("price" in item["query"].lower() or "preise" in item["query"].lower() for item in price_queries))

    def test_optional_gaps_are_not_auto_searched_and_qualitative_comparability_is_na(self):
        scope = {**CASES["lufthansa_strategy"], "industry": "航空运输与航空服务", "depth": "深度版"}
        requirements = build_requirements(scope)
        sufficiency = evaluate_sufficiency(requirements, [], [], scope)
        plan = build_gap_search_plan(sufficiency, build_search_plan(scope, requirements))
        self.assertFalse(any(query.get("priority") == "OPTIONAL" for query in plan["queries"]))
        optional_ids = {"employee_metrics", "ESG_metrics", "detailed_unit_economics"}
        self.assertFalse(any(query.get("dataset_id") in optional_ids for query in plan["queries"]))
        strategic = next(item for item in sufficiency["datasets"] if item["dataset_id"] == "strategic_initiatives")
        risks = next(item for item in sufficiency["datasets"] if item["dataset_id"] == "risks")
        self.assertIsNone(strategic["comparability_rate"])
        self.assertIsNone(risks["comparability_rate"])

    def test_financial_comparability_is_calculated_within_each_metric(self):
        scope = {**CASES["lufthansa_strategy"], "industry": "航空运输与航空服务"}
        requirements = build_requirements(scope)
        source = {**TEA_COMPETITOR_ACQUISITION["sources"][0], "source_id": "S_FIN", "url": "https://example.test/annual-report"}
        rows = []
        for metric_id, unit in (("revenue", "EUR million"), ("adjusted_ebit", "EUR million"), ("passenger_count", "passengers")):
            for period, value in (("FY2022", 1), ("FY2023", 2), ("FY2024", 3), ("FY2025", 4)):
                rows.append(normalize_observation({
                    "dataset_id": "financial_time_series", "entity": "Lufthansa Group",
                    "metric": metric_id, "metric_id": metric_id, "value": value,
                    "unit": unit, "currency": "EUR" if "EUR" in unit else "",
                    "period": period, "geography": "global", "entity_scope": "GROUP",
                    "source_id": "S_FIN", "verification_status": "SUPPORTED",
                }, {"S_FIN": source}, scope["industry"]))
        result = evaluate_sufficiency(requirements, rows, [source], scope)
        financial = next(item for item in result["datasets"] if item["dataset_id"] == "financial_time_series")
        self.assertEqual(financial["comparability_rate"], 1.0)
        self.assertTrue(financial["dashboard_readiness"]["TimeSeriesChart"])

    def test_compound_aviation_observation_is_split_and_units_are_normalized(self):
        source = {**TEA_COMPETITOR_ACQUISITION["sources"][0], "source_id": "S_AV", "url": "https://example.test/traffic"}
        rows = dedupe_observations([{
            "dataset_id": "operating_metrics", "entity": "Lufthansa Group",
            "metric": "运力、客流与客座率",
            "text_value": "2025年航班1,014,831架次，旅客135.035百万；ASK 338,552百万、RPK 281,765百万，客座率83.2%。",
            "period": "FY2025", "geography": "全球", "source_id": "S_AV",
            "verification_status": "SUPPORTED",
        }], [source], "航空运输")
        values = {row["metric_id"]: (row["value"], row["unit"]) for row in rows}
        self.assertEqual(values["passenger_count"], (135035000.0, "passengers"))
        self.assertEqual(values["available_seat_km"], (338552.0, "million seat-km"))
        self.assertEqual(values["passenger_load_factor"], (83.2, "%"))
        self.assertEqual(normalize_observation({"dataset_id": "operating_metrics", "entity": "Lufthansa Group", "metric": "RASK", "value": "8,3", "unit": "欧分", "source_id": "S_AV"}, {"S_AV": source}, "航空")["value"], 8.3)

    def test_tea_fixture_end_to_end_creates_level_two_price_coverage_and_gaps(self):
        scope = CASES["tea_competitor"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            state = initialize_data_pipeline(output, scope)
            critical = [item["dataset_id"] for item in state["requirements"]["datasets"] if item["priority"] == "CRITICAL"]
            self.assertEqual(critical, ["competitor_profiles", "product_portfolios", "price_observations", "positioning", "channel_or_store_coverage"])
            result = process_acquisition_response(output, scope, TEA_COMPETITOR_ACQUISITION)
            price = next(item for item in result["sufficiency"]["datasets"] if item["dataset_id"] == "price_observations")
            self.assertEqual(price["status"], "PARTIAL")
            self.assertTrue(price["dashboard_readiness"]["PriceBandChart"])
            self.assertTrue(price["dashboard_readiness"]["ProductPriceDotPlot"])
            self.assertFalse(price["dashboard_readiness"]["PricePositioningMatrix"])
            self.assertTrue(result["sufficiency"]["critical_gaps"])
            files = data_files(output)
            self.assertTrue(files["requirements"].is_file())
            self.assertTrue((files["datasets"] / "price_observations.json").is_file())
            self.assertTrue(files["gap_search_plan"].is_file())
            gap_plan = json.loads(files["gap_search_plan"].read_text(encoding="utf-8"))
            self.assertTrue(gap_plan["queries"])
            search_plan = json.loads(files["search_plan"].read_text(encoding="utf-8"))
            self.assertLessEqual(len(search_plan["queries"]) + len(gap_plan["queries"]), search_plan["budget"]["max_queries"])

    def test_historical_observation_is_supported_not_expired(self):
        scope = CASES["tea_competitor"]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            initialize_data_pipeline(output, scope)
            payload = json.loads(json.dumps(TEA_COMPETITOR_ACQUISITION))
            payload["observations"] = [payload["observations"][0]]
            payload["observations"][0]["verification_status"] = "NOT_CHECKED"
            payload["observations"][0]["temporal_status"] = "HISTORICAL"
            processed = process_acquisition_response(output, scope, payload)
            observation_id = processed["observations"][0]["observation_id"]
            verified = apply_observation_verification(output, [{"observation_id": observation_id, "fact_id": "F9", "verification_status": "HISTORICAL", "temporal_status": "HISTORICAL"}])
            self.assertEqual(verified["observations"][0]["verification_status"], "SUPPORTED")
            self.assertEqual(verified["observations"][0]["temporal_status"], "HISTORICAL")

    def test_private_company_can_stop_partial_without_inventing_data(self):
        scope = CASES["scarce_private_company"]
        with tempfile.TemporaryDirectory() as temp_dir:
            state = initialize_data_pipeline(Path(temp_dir), scope)
            self.assertEqual(state["sufficiency"]["overall_status"], "INSUFFICIENT")
            self.assertTrue(state["sufficiency"]["critical_gaps"])
            self.assertEqual((state["files"]["observations"].read_text(encoding="utf-8").count("observation_id")), 0)


if __name__ == "__main__":
    unittest.main()
