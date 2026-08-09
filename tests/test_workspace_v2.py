import json
from pathlib import Path
import tempfile

from streamlit.testing.v1 import AppTest
import shutil

from pipeline_v2.model import create_run_state, save_run_state
from pipeline_v2.service import PipelineV2Service
from ui.view_models.decisions_vm import decisions_view_model
from ui.view_models.project_vm import project_view_model
from ui.view_models.quality_vm import quality_view_model
from ui.view_models.revision_vm import revision_view_model
from ui.view_models.results_vm import results_view_model
from ui.view_models.run_vm import overview_view_model

SCOPE = {"analysis_type_id": "COMPANY_STRATEGY", "topic": "Fixture", "industry": "aviation", "geography": "Europe", "analysis_date": "2026-08-09", "required_sections": ["overview"]}


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
    source = Path(__file__).parent / "artifacts/v2-company-strategy-run"
    fixture_root = tmp_path / "artifacts"
    shutil.copytree(source, fixture_root / "v2-company-strategy-run")
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
    source = Path(__file__).parent / "artifacts/v2-company-strategy-run"
    fixture_root = tmp_path / "artifacts"
    shutil.copytree(source, fixture_root / "v2-company-strategy-run")
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
