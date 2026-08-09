import hashlib
import json
from pathlib import Path

from dashboard.registry import prepare_components
from tools.audit_latest_run import audit_run, discover_runs, select_run


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _complete_run(root: Path, run_id: str, updated_at: str):
    folder = root / run_id
    folder.mkdir(parents=True)
    final = "# Fixture\n\n【推断】保守、基准和乐观情景。\n"
    (folder / "01_research_brief.md").write_text("# Research\n", encoding="utf-8")
    (folder / "02_review_notes.md").write_text("# Review\n", encoding="utf-8")
    (folder / "04_final_report.md").write_text(final, encoding="utf-8")
    _write_json(folder / "00_analysis_scope.json", {
        "analysis_type": "公司战略", "industry": "测试", "geography": "全球",
        "analysis_date": "2026-08-09", "time_horizon": "2026-2030",
        "selected_template": "company_strategy", "required_sections": ["overview"],
        "focus_questions": ["如何增长？"], "competitors": [],
    })
    _write_json(folder / "03_fact_check.json", {"facts": [], "observation_verifications": []})
    _write_json(folder / "04_report_data.json", {
        "_meta": {"final_report_sha256": hashlib.sha256((folder / "04_final_report.md").read_bytes()).hexdigest()},
        "time_series": [], "scenarios": [],
    })
    _write_json(folder / "05_quality_check.json", {"overall_status": "PASS", "issues": []})
    _write_json(folder / "06_dashboard_data.json", {
        "dashboard_status": "READY", "observations": [], "scenarios": [],
        "components": [{"component_id": "kpi", "status": "READY", "reason": "missing data"}],
    })
    _write_json(folder / "run_manifest.json", {
        "run_id": run_id, "created_at": updated_at, "updated_at": updated_at,
        "latest_revision": "rev_000",
    })
    return folder


def test_latest_run_uses_parsed_manifest_timestamp_not_folder_name(tmp_path):
    older = _complete_run(tmp_path, "zzz_old", "2026-01-01T00:00:00+00:00")
    newer = _complete_run(tmp_path, "aaa_new", "2026-08-09T00:00:00+00:00")
    selected, incomplete = select_run(discover_runs(tmp_path))
    assert selected["folder"] == newer
    assert selected["folder"] != older
    assert incomplete is None


def test_audit_detects_scenario_gap_and_ready_reason(tmp_path):
    folder = _complete_run(tmp_path / "outputs", "run", "2026-08-09T00:00:00+00:00")
    row = discover_runs(tmp_path / "outputs")[0]
    payload = audit_run(row, "current", folder)
    rules = {issue["rule_id"] for issue in payload["raw_issues"]}
    assert "REPORT_SCENARIOS_MISSING" in rules
    assert "DASHBOARD_SCENARIOS_MISSING" in rules
    assert "DASHBOARD_READY_WITH_MISSING_REASON" in rules


def test_gap_search_without_opened_source_log_cannot_be_completed(tmp_path):
    folder = _complete_run(tmp_path / "outputs", "run", "2026-08-09T00:00:00+00:00")
    _write_json(folder / "data" / "data_coverage.json", {"observation_count": 0, "gap_search_rounds_completed": 1, "datasets": []})
    _write_json(folder / "data" / "search_log.json", {"entries": [{"execution_status": "COMPLETED", "executed_at": "2026-08-09T00:00:00Z", "result_count": 1, "opened_sources": []}]})
    payload = audit_run(discover_runs(tmp_path / "outputs")[0], "current", folder)
    assert "GAP_SEARCH_FALSE_COMPLETION" in {issue["rule_id"] for issue in payload["raw_issues"]}


def test_prepare_components_clears_missing_reason_when_ready():
    prepared = prepare_components(
        {"kpis": [{"metric_id": "m", "label": "Metric", "value": 1, "source_fact_ids": ["F1"]}]},
        {"components": [{"component_id": "kpi_summary", "renderer": "kpi_summary"}]},
    )
    assert prepared[0]["status"] == "READY"
    assert prepared[0]["reason"] == ""
