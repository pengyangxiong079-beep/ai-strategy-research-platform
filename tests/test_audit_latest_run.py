import hashlib
import json
from pathlib import Path

from dashboard.registry import prepare_components
from tools.audit_latest_run import audit_run, discover_runs, main as audit_main, scan_repository, select_run


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


def test_awaiting_human_incomplete_summary_requires_decision_not_stage_retry(tmp_path):
    root = tmp_path / "outputs"
    folder = root / "awaiting_human"
    folder.mkdir(parents=True)
    _write_json(folder / "run_manifest.json", {
        "run_id": "awaiting_human", "updated_at": "2026-08-09T00:00:00+00:00",
        "current_stage": "human", "final_status": "AWAITING_HUMAN_REVIEW",
    })
    _write_json(folder / "run_state.json", {
        "run_id": "awaiting_human", "current_stage": "human",
        "overall_status": "AWAITING_HUMAN_REVIEW",
    })
    _write_json(folder / "quality/issues.json", {"issues": []})
    row = discover_runs(root)[0]
    payload = audit_run(row, "current", folder, incomplete_latest=row)
    summary = next(issue for issue in payload["raw_issues"] if issue["rule_id"] == "RUN_INCOMPLETE_AT_GATE")
    assert summary["repair_type"] == "HUMAN_REQUIRED"


def test_repository_scan_prunes_dependency_and_output_trees(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("print('safe')", encoding="utf-8")
    for excluded in ("node_modules", ".venv", "outputs"):
        path = tmp_path / excluded
        path.mkdir()
        (path / "secret.txt").write_text("sk-abcdefghijklmnop123456", encoding="utf-8")
    result = scan_repository(tmp_path)
    assert result["status"] == "PASS"
    assert result["findings"] == []


def test_audit_accepts_explicit_qualitative_scenarios(tmp_path):
    folder = _complete_run(tmp_path / "outputs", "run", "2026-08-09T00:00:00+00:00")
    scenario = {
        "scenario_id": "SC_1", "label": "基准", "value_type": "QUALITATIVE",
        "assumptions": ["需求通过验证"], "trigger_conditions": ["客户续费"],
        "source_fact_ids": [],
    }
    report = json.loads((folder / "04_report_data.json").read_text(encoding="utf-8"))
    dashboard = json.loads((folder / "06_dashboard_data.json").read_text(encoding="utf-8"))
    report["scenarios"] = [scenario, {**scenario, "scenario_id": "SC_2", "label": "保守"}, {**scenario, "scenario_id": "SC_3", "label": "乐观"}]
    dashboard["scenarios"] = report["scenarios"]
    _write_json(folder / "04_report_data.json", report)
    _write_json(folder / "06_dashboard_data.json", dashboard)
    payload = audit_run(discover_runs(tmp_path / "outputs")[0], "current", folder)
    assert "SCENARIO_VALUE_TYPE" not in {issue["rule_id"] for issue in payload["raw_issues"]}


def test_revision_audit_uses_revision_run_state(tmp_path):
    root = tmp_path / "outputs"
    folder = _complete_run(root, "run", "2026-08-09T00:00:00+00:00")
    _write_json(folder / "run_state.json", {
        "run_id": "run", "current_stage": "fact_check", "overall_status": "BLOCKED_QUALITY",
    })
    revision = folder / "revisions/rev_001"
    revision.mkdir(parents=True)
    for name in ("00_analysis_scope.json", "02_review_notes.md", "03_fact_check.json"):
        (revision / name).write_bytes((folder / name).read_bytes())
    _write_json(revision / "run_state.json", {
        "run_id": "run", "current_stage": "human", "overall_status": "AWAITING_HUMAN_REVIEW",
    })
    _write_json(folder / "quality/issues.json", {"issues": [{
        "rule_id": "OLD_BASE_FAILURE", "stage": "fact_check", "artifact": "03_fact_check.json",
        "severity": "ERROR", "repair_type": "STAGE_RETRY",
    }]})
    _write_json(revision / "quality/issues.json", {"issues": []})
    row = discover_runs(root)[0]
    payload = audit_run(row, "rev_001", revision, incomplete_latest=row)
    summary = next(issue for issue in payload["raw_issues"] if issue["rule_id"] == "RUN_INCOMPLETE_AT_GATE")
    assert summary["repair_type"] == "HUMAN_REQUIRED"
    assert "human" in summary["reason"]
    assert "OLD_BASE_FAILURE" not in {issue["rule_id"] for issue in payload["raw_issues"]}


def test_completed_revision_overrides_incomplete_base_in_cli_audit(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    base = outputs / "run"; base.mkdir(parents=True)
    _write_json(base / "run_manifest.json", {
        "run_id": "run", "updated_at": "2026-08-09T00:00:00+00:00",
        "current_stage": "fact_check", "final_status": "BLOCKED_QUALITY",
    })
    _write_json(base / "run_state.json", {
        "run_id": "run", "current_stage": "fact_check", "overall_status": "BLOCKED_QUALITY",
    })
    revision = _complete_run(base / "revisions", "rev_001", "2026-08-09T01:00:00+00:00")
    _write_json(revision / "run_state.json", {
        "run_id": "run", "current_stage": "quality", "overall_status": "COMPLETED",
    })
    monkeypatch.chdir(tmp_path)
    exit_code = audit_main([
        "--outputs-root", str(outputs), "--run", "run", "--revision", "rev_001", "--offline",
    ])
    payload = json.loads((tmp_path / "audit/latest_run_audit.json").read_text(encoding="utf-8"))
    assert exit_code != 3
    assert payload["incomplete_latest_run"] is None


def test_revision_audit_prefers_canonical_quality_summary_over_stale_projection(tmp_path):
    folder = _complete_run(tmp_path / "outputs", "run", "2026-08-09T00:00:00+00:00")
    _write_json(folder / "05_quality_check.json", {"overall_status": "FAIL"})
    _write_json(folder / "quality/summary.json", {"status": "PASS", "issues": []})
    payload = audit_run(discover_runs(tmp_path / "outputs")[0], "current", folder)
    assert "DASHBOARD_QUALITY_STATUS" not in {
        issue["rule_id"] for issue in payload["raw_issues"]
    }
