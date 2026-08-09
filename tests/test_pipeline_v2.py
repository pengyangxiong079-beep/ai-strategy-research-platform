import json
from pathlib import Path
import tempfile

from pipeline_v2.contracts import validate_stage
from pipeline_v2.dependencies import mark_stale, revision_impact
from pipeline_v2.ids import stable_id
from pipeline_v2.model import create_run_state, load_run_state
from pipeline_v2.quality import aggregate_quality, request_repair
from pipeline_v2.renderer import markdown_matches_model, render_report
from pipeline_v2.service import PipelineV2Service
from research_platform.fixtures import CASES, TEA_COMPETITOR_ACQUISITION
from research_platform.pipeline import initialize_data_pipeline, process_acquisition_response


SCOPE = {"analysis_type_id": "COMPANY_STRATEGY", "analysis_type": "公司战略", "topic": "测试公司战略", "industry": "航空", "geography": "德国", "analysis_date": "2026-08-09", "required_sections": ["overview"], "focus_questions": [], "competitors": []}


def test_stable_ids_are_deterministic_and_typed():
    assert stable_id("claim", "same") == stable_id("claim", "same")
    assert stable_id("claim", "same").startswith("CLM_")
    assert stable_id("claim", "same") != stable_id("claim", "different")


def test_scope_gate_and_verified_without_source_are_blocked():
    assert validate_stage("scope", SCOPE).status == "PASS"
    claim = {"claim_id": "CLM_x", "verification_status": "SUPPORTED", "source_ids": [], "atomicity_status": "ATOMIC"}
    result = validate_stage("fact_check", {"claims": [claim]}, {"sources": []})
    assert result.status == "BLOCKED"
    assert result.errors[0]["rule_id"] == "FACT_VERIFIED_SOURCE"


def test_unsupported_claim_cannot_support_strategy():
    rec = {"recommendation_id": "REC_x", "claim_ids": ["CLM_x"]}
    result = validate_stage("strategy", {"recommendations": [rec]}, {"claims": [{"claim_id": "CLM_x", "verification_status": "UNSUPPORTED"}]})
    assert result.status == "BLOCKED"
    assert any(x["rule_id"] == "STRATEGY_UNSUPPORTED" for x in result.errors)


def test_optional_data_is_warning_not_failure():
    context = {"sources": [], "sufficiency": {"datasets": [{"dataset_id": "esg", "priority": "OPTIONAL", "status": "INSUFFICIENT"}]}}
    result = validate_stage("data", {"observations": []}, context)
    assert result.status == "PASS_WITH_WARNINGS"
    assert not result.errors
    assert aggregate_quality(result.warnings)["status"] == "PASS_WITH_WARNINGS"


def test_revision_dependency_stale_propagation_and_impact():
    state = create_run_state("run_1", SCOPE)
    for stage in state["stages"].values():
        stage["status"] = "COMPLETE"
    mark_stale(state, "human", "feedback changed")
    assert state["stages"]["strategy"]["status"] == "STALE"
    assert state["stages"]["data"]["status"] == "COMPLETE"
    assert revision_impact("LOCAL_REPAIR")["uses_codex"] is False
    assert revision_impact("FACT_VERIFICATION")["uses_codex"] is True


def test_renderer_generates_registry_links_and_matches_model():
    source = {"source_id": "SRC_x", "title": "Official", "url": "https://example.com/source"}
    claim = {"claim_id": "CLM_x", "source_ids": ["SRC_x"], "status": "ACTIVE"}
    model = {"title": "Test", "paragraphs": [{"section_id": "overview", "section_title": "Overview", "label": "FACT", "text": "Atomic fact.", "claim_ids": ["CLM_x"], "recommendation_ids": []}]}
    rendered = render_report(model, [claim], [source])
    assert "[Official](https://example.com/source)" in rendered
    assert markdown_matches_model(rendered, model)


def test_auto_repair_is_bounded():
    state = create_run_state("run_1", SCOPE)
    assert request_repair(state, "research", "STAGE_RETRY")["allowed"]
    assert request_repair(state, "research", "STAGE_RETRY")["allowed"]
    denied = request_repair(state, "research", "STAGE_RETRY")
    assert not denied["allowed"]
    assert state["stages"]["research"]["status"] == "BLOCKED"


def test_canonical_run_initialization_and_legacy_read_only():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        service = PipelineV2Service(root)
        folder = root / "new_run"; folder.mkdir()
        service.initialize(folder, "new_run", SCOPE)
        assert load_run_state(folder)["schema_version"] == "2.0"
        assert (folder / "research/claims.json").is_file()
        legacy = root / "legacy"; legacy.mkdir()
        (legacy / "run_manifest.json").write_text(json.dumps({"run_id": "legacy", "topic": "Legacy", "final_status": "COMPLETED"}), encoding="utf-8")
        view = service.load(legacy)
        assert view["legacy"] and view["read_only"]


def test_v2_acquisition_replaces_agent_display_ids_with_stable_source_and_observation_ids():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); folder = root / "v2"; folder.mkdir()
        scope = {**CASES["tea_competitor"], "analysis_type_id": "COMPETITOR_ANALYSIS", "required_sections": []}
        PipelineV2Service(root).initialize(folder, "v2", scope)
        initialize_data_pipeline(folder, scope)
        processed = process_acquisition_response(folder, scope, TEA_COMPETITOR_ACQUISITION)
        assert all(x["source_id"].startswith("SRC_") for x in processed["sources"])
        assert all(x["observation_id"].startswith("OBS_") for x in processed["observations"])
