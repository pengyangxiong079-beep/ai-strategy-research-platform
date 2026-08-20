import json
from pathlib import Path
import tempfile

from streamlit.testing.v1 import AppTest
import shutil

from pipeline_v2.model import create_run_state, save_run_state
from pipeline_v2.service import PipelineV2Service
from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.fake_agent_registry import FakeAgentRegistry
from dashboard.schema import validate_dashboard_data, validate_report_data
from ui.view_models.decisions_vm import decisions_view_model
from ui.view_models.project_vm import project_view_model
from ui.view_models.quality_vm import quality_view_model
from ui.actions import record_decision
from ui.view_models.revision_vm import revision_view_model
from ui.view_models.results_vm import results_view_model
from ui.view_models.run_vm import overview_view_model
from ui.state import format_run_option, preferred_revision_for_run, resolve_run_selection
from ui.workspace import run_view_for_revision

SCOPE = {"analysis_type_id": "COMPANY_STRATEGY", "topic": "Fixture", "industry": "aviation", "geography": "Europe", "analysis_date": "2026-08-09", "required_sections": ["overview"]}


def test_pending_run_selection_overrides_persisted_failed_widget():
    ids = ["new_running", "old_failed"]
    assert resolve_run_selection(
        ids, requested="new_running", widget="old_failed", selected="new_running"
    ) == "new_running"
    assert resolve_run_selection(
        ids, widget="old_failed", selected="new_running", migrate=True
    ) == "new_running"


def test_same_topic_run_option_exposes_status_and_timestamp():
    label = format_run_option({
        "run_id": "20260812_232726_lufthansa", "topic": "Lufthansa",
        "overall_status": "FAILED_TECHNICAL",
    })
    assert label == "Lufthansa · FAILED_TECHNICAL · 20260812 232726"


def test_known_bad_base_prefers_available_repaired_revision():
    run = create_run_state("r", SCOPE)
    run["overall_status"] = "BLOCKED_QUALITY"
    run["stages"]["fact_check"]["status"] = "BLOCKED"
    assert preferred_revision_for_run(run, ["current", "rev_001"]) == "rev_001"
    run["stages"]["fact_check"]["status"] = "COMPLETE"
    assert preferred_revision_for_run(run, ["current", "rev_001"]) == "current"


def test_selected_revision_view_replaces_failed_base_status(tmp_path, monkeypatch):
    base = tmp_path / "base"; revision = base / "revisions" / "rev_001"
    base.mkdir(parents=True); revision.mkdir(parents=True)
    base_state = create_run_state("base", SCOPE)
    base_state["overall_status"] = "FAILED_TECHNICAL"
    save_run_state(base, base_state)
    revision_state = create_run_state("base", SCOPE, revision_id="rev_001")
    revision_state["overall_status"] = "AWAITING_HUMAN_REVIEW"
    save_run_state(revision, revision_state)
    monkeypatch.setenv("WORKSPACE_OUTPUTS_ROOT", str(tmp_path))
    view = run_view_for_revision(
        {**base_state, "folder": str(base), "project_id": "base"}, "rev_001"
    )
    assert view["overall_status"] == "AWAITING_HUMAN_REVIEW"
    assert view["revision_id"] == "rev_001"
    assert view["base_folder"] == str(base)


def _portable_v2_run(root):
    """Build a complete run from versioned inputs without network or outputs/."""
    folder = root / "v2-company-strategy-run"
    scope = json.loads((Path(__file__).parent / "fixtures/v2_company_strategy/scope.json").read_text(encoding="utf-8"))
    folder.mkdir(parents=True)
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope, ensure_ascii=False), encoding="utf-8")
    PipelineV2Service(root).initialize(folder, "fixture_company_strategy", scope)
    feedback = {"schema_version": "2.0", "feedback": [{"feedback_id": "HFB_fixture", "decision_id": "DEC_fixture", "claim_ids": [], "choice": "accept", "status": "RESOLVED"}]}
    PipelineV2Orchestrator(FakeAgentRegistry()).execute(folder, human_feedback=feedback)
    return folder


def _fixture(root, *, status="AWAITING_HUMAN_REVIEW"):
    folder = root / "run_fixture"; folder.mkdir()
    state = create_run_state("run_fixture", SCOPE)
    state["overall_status"] = status
    state["current_stage"] = "human" if status == "AWAITING_HUMAN_REVIEW" else "quality"
    save_run_state(folder, state)
    (folder / "review").mkdir(); (folder / "human").mkdir(); (folder / "quality").mkdir(); (folder / "research").mkdir(); (folder / "data").mkdir(); (folder / "revisions").mkdir()
    (folder / "review/review_issues.json").write_text(json.dumps({"issues": [{"review_id": "REV_x", "title": "Choose", "reason": "Conflict", "status": "OPEN"}]}), encoding="utf-8")
    (folder / "human/feedback.json").write_text(json.dumps({"feedback": []}), encoding="utf-8")
    return {**state, "folder": str(folder), "read_only": False}


def test_status_maps_to_single_primary_action():
    for status, page in [("AWAITING_HUMAN_REVIEW", "decisions"), ("BLOCKED_DATA", "data_quality"), ("COMPLETED", "results")]:
        run = create_run_state("r", SCOPE); run["overall_status"] = status
        assert overview_view_model(run)["primary_action"]["page"] == page


def test_project_empty_state_and_filtering():
    assert project_view_model([])["empty"]
    run = {"run_id": "r", "project_id": "r", "topic": "Lufthansa", "normalized_analysis_type": "COMPANY_STRATEGY", "overall_status": "COMPLETED"}
    assert project_view_model([run], query="lufthansa")["count"] == 1
    assert project_view_model([run], query="xpeng")["empty"]


def test_decisions_pending_then_resolved():
    with tempfile.TemporaryDirectory() as temp:
        run = _fixture(Path(temp))
        vm = decisions_view_model(run)
        assert len(vm["pending"]) == 1 and not vm["resolved"]
        decision_id = vm["pending"][0]["decision_id"]
        Path(run["folder"], "human/feedback.json").write_text(json.dumps({"feedback": [{"decision_id": decision_id, "feedback_id": "HFB_x", "status": "RESOLVED"}]}), encoding="utf-8")
        vm = decisions_view_model(run)
        assert not vm["pending"] and len(vm["resolved"]) == 1


def test_decision_view_exposes_issue_evidence_and_required_action():
    with tempfile.TemporaryDirectory() as temp:
        run = _fixture(Path(temp))
        folder = Path(run["folder"])
        (folder / "review/review_issues.json").write_text(json.dumps({"issues": [{
            "review_id": "R1", "severity": "MEDIUM", "category": "metadata",
            "issue": "Observation date conflicts with publication date.",
            "evidence": "OBS_1 predates SRC_1 publication.",
            "required_action": "Correct the date or change the source.", "status": "OPEN",
        }]}), encoding="utf-8")
        decision = decisions_view_model(run)["pending"][0]
        assert decision["title"] == "Observation date conflicts with publication date."
        assert decision["evidence"] == "OBS_1 predates SRC_1 publication."
        assert decision["required_action"] == "Correct the date or change the source."
        assert decision["severity"] == "MEDIUM"


def test_gap_queries_survive_live_candidate_denormalization():
    with tempfile.TemporaryDirectory() as temp:
        run = _fixture(Path(temp))
        folder = Path(run["folder"])
        sufficiency = {
            "datasets": [{
                "dataset_id": "competitors", "priority": "IMPORTANT", "status": "INSUFFICIENT",
                "gaps": [{
                    "gap_id": "G_competitors_001", "missing_field": "dataset",
                    "recommended_queries": [{"query": "Example competitor annual report"}],
                }],
            }],
            # Mirrors the incomplete denormalized list observed in a live run.
            "gap_search_candidates": [{
                "gap_id": "G_competitors_001", "dataset_id": "competitors",
                "priority": "IMPORTANT", "missing_field": "dataset",
            }],
        }
        (folder / "data/sufficiency.json").write_text(json.dumps(sufficiency), encoding="utf-8")
        (folder / "review/review_issues.json").write_text(json.dumps({"issues": [{
            "review_id": "R1", "severity": "MEDIUM", "category": "sufficiency",
            "issue": "Competitor evidence is insufficient.",
            "evidence": "G_competitors_001 for dataset_id competitors is INSUFFICIENT.",
            "required_action": "Add supported competitor evidence.", "status": "OPEN",
        }]}), encoding="utf-8")

        gap_search = quality_view_model(run)["targeted_gap_search"]
        assert gap_search["query_count"] == 1
        assert gap_search["targets"][0]["recommended_queries"][0]["query"] == "Example competitor annual report"
        decision = decisions_view_model(run)["pending"][0]
        assert "具体缺口数据集：competitors" in decision["evidence"]
        assert "建议定向查询：Example competitor annual report" in decision["required_action"]


def test_repeated_identical_deferred_decision_is_idempotent():
    with tempfile.TemporaryDirectory() as temp:
        run = _fixture(Path(temp))
        decision = decisions_view_model(run)["pending"][0]
        first = record_decision(run, decision, "暂缓，返回补充或修正", "请补充运营指标")
        second = record_decision(run, decision, "暂缓，返回补充或修正", "请补充运营指标")
        feedback = json.loads(Path(run["folder"], "human/feedback.json").read_text(encoding="utf-8"))["feedback"]
        assert first["feedback_id"] == second["feedback_id"]
        assert len(feedback) == 1
        vm = decisions_view_model(run)
        assert len(vm["deferred"]) == 1
        assert not vm["pending"]
        assert not vm["resolved"]
        assert not vm["can_continue"]


def test_results_artifact_levels_and_one_revision_hides_comparison():
    with tempfile.TemporaryDirectory() as temp:
        run = _fixture(Path(temp), status="COMPLETED")
        folder = Path(run["folder"])
        (folder / "04_final_report.md").write_text("# Final", encoding="utf-8")
        (folder / "01_research_brief.md").write_text("# Research", encoding="utf-8")
        (folder / "04_report_data.json").write_text(json.dumps({"executive_summary": "Summary"}), encoding="utf-8")
        revision = folder / "revisions/rev_000"; revision.mkdir()
        (revision / "revision_manifest.json").write_text("{}", encoding="utf-8")
        assert results_view_model(run)["final_markdown"] == "# Final"
        assert len(results_view_model(run)["supporting"]) == 1
        assert revision_view_model(run)["show_comparison"] is False


def test_professional_example_exposes_conditional_decision_and_quality_gate():
    root = Path(__file__).resolve().parents[1] / "examples/professional_case"
    run = PipelineV2Service(root).list_runs()[0]
    results = results_view_model(run)
    quality = quality_view_model(run)
    overview = overview_view_model(run)
    assert results["decision_brief"]["posture"] == "有条件推进"
    assert results["decision_brief"]["primary"]["priority"] == "P0"
    assert results["decision_brief"]["scenario_count"] == 3
    assert len(quality["decision_gaps"]) == 1
    assert quality["support_rate"] == 6 / 7
    assert overview["decision_brief"]["critical_gap"]["gap_id"] == "GAP_CHANNEL_CONVERSION"
    validate_report_data(json.loads(Path(run["folder"], "04_report_data.json").read_text(encoding="utf-8")))
    validate_dashboard_data(json.loads(Path(run["folder"], "06_dashboard_data.json").read_text(encoding="utf-8")))


def test_blocking_quality_view_model_and_legacy_fixture():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); run = _fixture(root, status="BLOCKED_QUALITY")
        Path(run["folder"], "quality/issues.json").write_text(json.dumps({"issues": [{"rule_id": "Q1", "severity": "ERROR"}]}), encoding="utf-8")
        assert len(quality_view_model(run)["blocking"]) == 1
        legacy = root / "legacy"; legacy.mkdir()
        (legacy / "run_manifest.json").write_text(json.dumps({"run_id": "legacy", "topic": "Old", "final_status": "COMPLETED"}), encoding="utf-8")
        view = PipelineV2Service(root).load(legacy)
        assert view["read_only"] and view["legacy"]


def test_workspace_entrypoint_and_wizard_render_without_agent_calls():
    from unittest.mock import patch
    with patch.dict("os.environ", {"WORKSPACE_V2": "1"}):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py")).run(timeout=30)
        assert not app.exception
        assert app.title[0].value == "项目"
        app.switch_page("app_pages/new_analysis.py").run(timeout=30)
        assert not app.exception
        assert app.title[0].value == "新建分析"
        assert any(x.label == "分析主题" for x in app.text_input)


def test_all_workspace_pages_load_against_offline_v2_fixture(tmp_path):
    from unittest.mock import patch
    fixture_root = tmp_path / "artifacts"
    _portable_v2_run(fixture_root)
    env = {"WORKSPACE_V2": "1", "WORKSPACE_OUTPUTS_ROOT": str(fixture_root)}
    expected = {
        "app_pages/projects.py": "项目", "app_pages/new_analysis.py": "新建分析",
        "app_pages/overview.py": "运行概览", "app_pages/pipeline.py": "研究流程",
        "app_pages/decisions.py": "人工决策", "app_pages/results.py": "研究成果",
        "app_pages/data_quality.py": "数据与质量", "app_pages/revisions.py": "修订与版本",
    }
    with patch.dict("os.environ", env):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py")).run(timeout=30)
        for page, title in expected.items():
            app.switch_page(page).run(timeout=30)
            assert not app.exception, page
            assert app.title and app.title[0].value == title


def test_revision_ui_preview_create_and_execute_real_local_plan(tmp_path):
    from unittest.mock import patch
    fixture_root = tmp_path / "artifacts"
    _portable_v2_run(fixture_root)
    env = {"WORKSPACE_V2": "1", "WORKSPACE_OUTPUTS_ROOT": str(fixture_root)}
    with patch.dict("os.environ", env):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py")).run(timeout=30)
        app.switch_page("app_pages/revisions.py").run(timeout=30)
        next(x for x in app.text_input if x.label == "修订目标").set_value("重建本地产物")
        next(x for x in app.button if x.label == "生成影响预览").click().run(timeout=30)
        assert any(x.value == "Impact preview" for x in app.subheader)
        next(x for x in app.checkbox if x.label == "我确认影响范围并保留原版本").check()
        next(x for x in app.button if x.label == "确认并创建Revision").click().run(timeout=30)
        assert (fixture_root / "v2-company-strategy-run/revisions/rev_001/execution_state.json").is_file()
        next(x for x in app.button if x.label == "执行Revision").click().run(timeout=30)
        execution = json.loads((fixture_root / "v2-company-strategy-run/revisions/rev_001/execution_state.json").read_text(encoding="utf-8"))
        assert execution["plan_status"] == "COMPLETED"
