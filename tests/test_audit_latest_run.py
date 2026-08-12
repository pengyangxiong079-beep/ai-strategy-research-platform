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


def test_nested_public_fixture_resolves_repository_root(tmp_path):
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    for relative in ("README.md", ".gitignore", ".env.example", "CONTRIBUTING.md", "SECURITY.md", ".github/workflows/offline-ci.yml"):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture", encoding="utf-8")
    folder = _complete_run(repository / "examples/professional_case", "nested_run", "2026-08-09T00:00:00+00:00")
    payload = audit_run(discover_runs(repository / "examples/professional_case")[0], "current", folder)
    assert "GITHUB_FILES_MISSING" not in {issue["rule_id"] for issue in payload["raw_issues"]}


def test_incomplete_run_reports_gate_cause_not_missing_downstream_derivatives(tmp_path):
    root = tmp_path / "outputs"
    folder = root / "blocked"
    folder.mkdir(parents=True)
    _write_json(folder / "run_manifest.json", {
        "run_id": "blocked", "updated_at": "2026-08-09T00:00:00+00:00",
        "current_stage": "scope", "final_status": "AWAITING_SCOPE_CONFIRMATION",
    })
    _write_json(folder / "run_state.json", {
        "run_id": "blocked", "current_stage": "review", "overall_status": "BLOCKED_QUALITY",
    })
    _write_json(folder / "quality/issues.json", {"issues": [{
        "rule_id": "REVIEW_SEVERITY_INVALID", "stage": "review", "artifact": "02_review_notes.json",
        "location": "/issues/0/severity", "reason": "unsupported severity: BLOCKER",
        "severity": "ERROR", "repair_type": "STAGE_RETRY",
    }]})
    row = discover_runs(root)[0]
    payload = audit_run(row, "current", folder, incomplete_latest=row)
    rules = {issue["rule_id"] for issue in payload["raw_issues"]}
    assert rules >= {"REVIEW_SEVERITY_INVALID", "RUN_INCOMPLETE_AT_GATE"}
    assert "REPORT_HASH_MISMATCH" not in rules
    assert "OBSERVATION_LINEAGE_COUNT_MISMATCH" not in rules
    assert payload["incomplete_latest_run"]["current_stage"] == "review"
    assert payload["incomplete_latest_run"]["overall_status"] == "BLOCKED_QUALITY"


def test_blocked_data_incomplete_summary_requires_live_rerun(tmp_path):
    root = tmp_path / "outputs"
    folder = root / "blocked_data"
    folder.mkdir(parents=True)
    _write_json(folder / "run_manifest.json", {
        "run_id": "blocked_data", "updated_at": "2026-08-09T00:00:00+00:00",
        "current_stage": "data", "final_status": "BLOCKED_DATA",
    })
    _write_json(folder / "run_state.json", {
        "run_id": "blocked_data", "current_stage": "data", "overall_status": "BLOCKED_DATA",
    })
    _write_json(folder / "quality/issues.json", {"issues": []})
    row = discover_runs(root)[0]
    payload = audit_run(row, "current", folder, incomplete_latest=row)
    summary = next(issue for issue in payload["raw_issues"] if issue["rule_id"] == "RUN_INCOMPLETE_AT_GATE")
    assert summary["repair_type"] == "REQUIRES_LIVE_RERUN"
    assert any(issue["rule_id"] == "RUN_INCOMPLETE_AT_GATE" for issue in payload["remaining_gaps"])
