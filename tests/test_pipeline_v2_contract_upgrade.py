import json
from pathlib import Path

import main
from pipeline_v2.contracts import validate_stage
from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.quality import aggregate_quality
from pipeline_v2.report_protocol import hash_consistent, report_data_payload, render_content_blocks
from pipeline_v2.review import validate_review_notes
from pipeline_v2.revision import RevisionExecutor, plan_revision
from pipeline_v2.service import PipelineV2Service
from pipeline_v2.agent_outputs import persist_review_model
from research_platform.data_acquisition.search_vocabulary import build_dataset_queries
from research_platform.report_adapter import enrich_report_data
from tests.fakes.fake_agent_registry import FakeAgentRegistry
from ui.view_models.revision_vm import revision_view_model


SOLAR_SCOPE = {
    "analysis_type": "行业分析",
    "analysis_type_id": "INDUSTRY_ANALYSIS",
    "topic": "德国光伏行业战略分析",
    "industry": "光伏能源",
    "geography": "德国及欧洲市场",
    "analysis_date": "2026-08-09",
    "time_horizon": "2025-2030",
    "required_sections": ["overview", "strategy"],
    "focus_questions": [f"问题{i}，包含完整中文标点？" for i in range(1, 14)],
    "competitors": [],
    "target_entity": "Germany photovoltaic market",
    "is_test_fixture": True,
}


def test_scope_parser_keeps_13_chinese_questions_and_does_not_split_punctuation():
    raw = "\n".join(f"{i}. 问题{i}，包含逗号；也包含分号？" for i in range(1, 14))
    rows = main.split_scope_list(raw)
    assert len(rows) == 13
    assert rows[0] == "问题1，包含逗号；也包含分号？"


def test_review_range_id_is_rejected_as_one_invalid_id():
    errors = validate_review_notes([{
        "review_id": "R1—R11", "severity": "HIGH", "category": "coverage",
        "issue": "eleven issues collapsed", "evidence": "fixture",
        "required_action": "split into atomic issues", "status": "OPEN",
    }])
    assert [row["rule_id"] for row in errors] == ["REVIEW_ID_RANGE_FORBIDDEN"]


def test_legacy_review_agent_fields_are_normalized_to_canonical_contract(tmp_path):
    raw = '<review_issues_json>{"schema_version":"2.0","issues":[{"review_id":"legacy_hash","title":"缺少证据","severity":"WARNING","dataset_id":"market_size","reason":"只有单一来源","suggested_action":"补充交叉验证","status":"OPEN"}]}</review_issues_json>'
    payload = persist_review_model(tmp_path, raw)
    assert payload is not None
    issue = json.loads((tmp_path / "02_review_notes.json").read_text(encoding="utf-8"))["issues"][0]
    assert issue == {
        "review_id": "R1", "severity": "WARNING", "category": "market_size",
        "issue": "缺少证据", "evidence": "只有单一来源",
        "required_action": "补充交叉验证", "status": "OPEN",
    }


def test_review_gate_retries_once_then_persists_canonical_json(tmp_path):
    service = PipelineV2Service(tmp_path)
    folder = tmp_path / "solar_contract"
    folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(SOLAR_SCOPE, ensure_ascii=False), encoding="utf-8")
    service.initialize(folder, "solar_contract", SOLAR_SCOPE)
    fake = FakeAgentRegistry({"review": ["semantic_error", "success"]})
    state = PipelineV2Orchestrator(fake).execute(folder, stages=["scope", "data", "research", "review"])
    assert state["stages"]["review"]["status"] == "COMPLETE"
    assert fake.call_count("review") == 2
    assert fake.get("review").calls[1]["error_packet"][0]["rule_id"] == "REVIEW_ID_RANGE_FORBIDDEN"
    assert json.loads((folder / "02_review_notes.json").read_text(encoding="utf-8"))["issues"] == []


def test_german_solar_gap_queries_are_short_local_and_agency_led():
    rows = build_dataset_queries(SOLAR_SCOPE, "market_size", missing_metric="installed_capacity", period="2025", gap_id="G1", limit=5)
    text = "\n".join(row["query_text"] for row in rows)
    assert "site:bundesnetzagentur.de Photovoltaik MaStR Juni 2026 PDF" in text
    assert "Deutschland Photovoltaik installierte Leistung Bundesland 2025 MaStR" in text
    assert "Germany solar electricity generation 2025 Fraunhofer PDF" in text
    assert SOLAR_SCOPE["topic"] not in text
    assert all(row["query_id"] and row["gap_id"] == "G1" for row in rows)


def test_coverage_count_mismatch_blocks_data_gate():
    gate = validate_stage("data", {"observations": []}, {"sources": [], "sufficiency": {"observation_count": 4, "datasets": []}})
    assert not gate.can_continue
    assert {row["rule_id"] for row in gate.errors} >= {"DATA_COVERAGE_COUNT_MISMATCH", "DATA_COVERAGE_WITHOUT_OBSERVATIONS"}


def test_structured_scenarios_fact_tags_and_hash_are_deterministic():
    scenario = {
        "scenario_id": "SC_BASE", "label": "基准情景", "base_period": "2025", "end_period": "2030",
        "starting_value": 100, "annual_points": [{"period": "2030", "value": 190}],
        "assumptions": ["annual additions remain elevated"], "formula": "start + annual additions",
        "target_value": 215, "target_gap": 25, "trigger_conditions": ["auction awards slow"],
        "risks": ["grid bottleneck"], "source_fact_ids": ["F1"],
        "source_observation_ids": ["OBS_1"], "confidence": "MEDIUM",
    }
    claims = [{"claim_id": "CLM_1", "display_id": "F1", "observation_ids": ["OBS_1"]}]
    model = {"title": "德国光伏离线夹具", "paragraphs": [{"section_id": "overview", "section_title": "概览", "label": "FACT", "text": "装机数据来自结构化观测。", "claim_ids": ["CLM_1"]}], "scenarios": [scenario]}
    blocks = report_data_payload(model, claims, [], "", run_id="solar", revision_id="rev_000")["content_blocks"]
    markdown = render_content_blocks(model["title"], blocks)
    payload = report_data_payload(model, claims, [], markdown, run_id="solar", revision_id="rev_000")
    assert "【事实｜F1】" in markdown
    assert main.FACT_TAG_PATTERN.search(markdown)
    assert payload["scenarios"][0]["value_type"] == "MODELLED"
    assert payload["scenarios"][0]["target_value"] == 215
    assert hash_consistent(markdown, payload)
    assert not hash_consistent(markdown + "changed", payload)


def test_scenario_narrative_without_structured_scenarios_fails():
    report = {"paragraphs": [{"section_id": "overview", "label": "INFERENCE", "text": "保守、基准和乐观情景。", "claim_ids": []}], "scenarios": []}
    gate = validate_stage("report", report, {"claims": [], "required_sections": ["overview"], "requires_scenarios": True})
    assert {row["rule_id"] for row in gate.errors} == {"REPORT_SCENARIOS_REQUIRED"}


def test_time_series_preserves_periods_with_strict_metric_partitioning():
    observations = []
    for metric, unit in (("installed_capacity", "GW"), ("net_additions", "GW")):
        for period, value in (("2024", 80), ("2025", 100)):
            observations.append({
                "observation_id": f"OBS_{metric}_{period}", "dataset_id": "historical_growth",
                "entity": "Germany", "entity_scope": "COUNTRY", "metric": metric, "metric_id": metric,
                "metric_definition": metric, "value": value, "unit": unit, "currency": "",
                "geography": "Germany", "period": period, "period_type": "CALENDAR_YEAR",
                "channel": "official", "comparability_group": f"CG_{metric}",
                "verification_status": "SUPPORTED", "source_fact_ids": ["F1"],
                "source_grade": "GRADE_A", "confidence": "HIGH", "value_type": "HISTORICAL",
            })
    result = enrich_report_data({"data_gaps": [], "time_series": [], "competitor_comparisons": []}, observations, {"datasets": []})
    assert len(result["time_series"]) == 2
    assert result["_meta"]["coverage_periods"] == ["2024", "2025"]
    assert result["_meta"]["exported_time_series_periods"] == ["2024", "2025"]
    assert result["_meta"]["time_series_exclusions"] == []


def test_verified_observations_generate_professional_industry_core_views():
    observations = []
    for period, value, dataset, value_type in (
        ("2020", 274.7, "market_size", "HISTORICAL"),
        ("2021", 360.5, "historical_growth", "HISTORICAL"),
        ("2022", 421.3, "historical_growth", "HISTORICAL"),
        ("2023", 517.5, "market_size", "HISTORICAL"),
        ("2024", 627.9, "forecast_growth", "FORECAST"),
        ("2025", 746.4, "forecast_growth", "FORECAST"),
        ("2026", 876.2, "forecast_growth", "FORECAST"),
        ("2027", 1016.8, "forecast_growth", "FORECAST"),
        ("2028", 1163.4, "forecast_growth", "FORECAST"),
    ):
        observations.append({
            "observation_id": f"O_{period}", "dataset_id": dataset,
            "entity": "中国现制饮品市场", "entity_scope": "MARKET",
            "metric": "GMV", "metric_id": "freshly_made_drinks_gmv",
            "metric_definition": "中国现制饮品GMV", "value": value,
            "unit": "CNY_billion", "currency": "CNY", "geography": "China",
            "period": period, "period_type": "CALENDAR_YEAR", "channel": "ALL",
            "comparability_group": "CG_GMV", "verification_status": "SUPPORTED",
            "source_fact_ids": [f"F{int(period) - 2019}"], "source_grade": "GRADE_C",
            "confidence": "HIGH", "value_type": value_type,
        })
    for suffix, entity, value, fact_id in (("TEA", "中国现制茶饮市场", 258.5, "F20"), ("COFFEE", "中国现制咖啡市场", 172.1, "F21")):
        observations.append({
            "observation_id": f"O_{suffix}", "dataset_id": "market_segments",
            "entity": entity, "entity_scope": "MARKET", "metric": "GMV",
            "metric_id": f"{suffix.lower()}_gmv", "metric_definition": "细分市场GMV",
            "value": value, "unit": "CNY_billion", "currency": "CNY",
            "geography": "China", "period": "2023", "period_type": "CALENDAR_YEAR",
            "channel": "ALL", "comparability_group": "CG_SEGMENT_GMV",
            "verification_status": "SUPPORTED", "source_fact_ids": [fact_id],
            "source_grade": "GRADE_C", "confidence": "HIGH", "value_type": "HISTORICAL",
        })
    result = enrich_report_data(
        {"kpis": [], "data_gaps": [], "time_series": [], "market_segments": [], "competitor_comparisons": []},
        observations, {"datasets": []},
    )
    assert len(result["kpis"]) == 4
    assert len(result["time_series"]) == 1
    assert len(result["time_series"][0]["points"]) == 9
    assert {point["value_type"] for point in result["time_series"][0]["points"]} == {"ACTUAL", "FORECAST"}
    assert {item["label"] for item in result["market_segments"]} == {"中国现制茶饮市场", "中国现制咖啡市场"}


def test_initial_snapshot_revision_semantics_and_rerun_stages(tmp_path):
    folder = tmp_path / "solar_revision"
    folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(SOLAR_SCOPE, ensure_ascii=False), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "solar_revision", SOLAR_SCOPE)
    vm = revision_view_model({"folder": str(folder), "read_only": False})
    assert vm["versions"][0]["label"] == "Initial Snapshot"
    assert vm["revision_count"] == 0
    fact = plan_revision(folder, "FACT_VERIFICATION")
    full = plan_revision(folder, "FULL_RESEARCH")
    assert fact.revision_id == "rev_001"
    assert fact.execution_stages == ["fact_check", "human", "strategy", "report", "quality", "dashboard"]
    assert full.execution_stages[0] == "data"


def test_quality_issues_are_grouped_into_one_review_root_cause():
    issues = [{"rule_id": "REVIEW_ID_SEQUENCE", "stage": "review", "reason": "missing", "location": f"/issues/{index}", "severity": "ERROR", "repair_type": "STAGE_RETRY"} for index in range(9)]
    result = aggregate_quality(issues)
    assert len(result["raw_issues"]) == 9
    assert len(result["root_causes"]) == 1
    assert len(result["root_causes"][0]["affected_items"]) == 9
    assert result["recommended_revision_type"] == "RETRY_REVIEW"


def test_offline_solar_fixture_completes_initial_fact_and_full_revisions(tmp_path):
    folder = tmp_path / "solar_e2e"
    folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(SOLAR_SCOPE, ensure_ascii=False), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "solar_e2e", SOLAR_SCOPE)
    fake = FakeAgentRegistry()
    orchestrator = PipelineV2Orchestrator(fake)
    state = orchestrator.execute(folder, human_feedback={"schema_version": "2.0", "feedback": []})
    assert state["stages"]["quality"]["validation_status"] == "PASS"
    assert state["stages"]["dashboard"]["status"] == "COMPLETE"
    assert (folder / "06_dashboard_data.json").is_file()

    executor = RevisionExecutor(orchestrator)
    fact_plan = plan_revision(folder, "FACT_VERIFICATION")
    executor.create(folder, fact_plan)
    fact_result = executor.execute(folder, fact_plan.revision_id, human_feedback={"schema_version": "2.0", "feedback": []})
    assert fact_plan.revision_id == "rev_001"
    assert fact_result["plan_status"] == "COMPLETED"

    full_plan = plan_revision(folder, "FULL_RESEARCH")
    executor.create(folder, full_plan)
    full_result = executor.execute(folder, full_plan.revision_id, human_feedback={"schema_version": "2.0", "feedback": []})
    assert full_plan.revision_id == "rev_002"
    assert full_result["plan_status"] == "COMPLETED"
    manifest = json.loads((folder / "revisions" / "rev_002" / "revision_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED"
    assert manifest["parent_revision"] == "rev_001"
    assert manifest["input_hashes"] and manifest["output_hashes"]
