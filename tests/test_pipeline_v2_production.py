from __future__ import annotations

import json
from pathlib import Path
import shutil

from pipeline_v2.model import load_run_state
from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.revision import RevisionExecutor, plan_revision
from pipeline_v2.service import PipelineV2Service
from tests.fakes import FakeAgentRegistry


FIXTURE = Path(__file__).parent / "fixtures/v2_company_strategy/scope.json"


def make_run(tmp_path, *, human_feedback=None, registry=None):
    scope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    folder = tmp_path / "fixture_run"
    folder.mkdir(parents=True)
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope, ensure_ascii=False), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "fixture_run", scope)
    feedback = human_feedback or {"schema_version": "2.0", "feedback": [{"feedback_id": "HFB_fixture", "decision_id": "DEC_fixture", "claim_ids": [], "choice": "接受", "status": "RESOLVED"}]}
    registry = registry or FakeAgentRegistry()
    orchestrator = PipelineV2Orchestrator(registry)
    state = orchestrator.execute(folder, human_feedback=feedback)
    return folder, state, registry


def test_canonical_offline_e2e_uses_only_structured_artifacts(tmp_path):
    folder, state, registry = make_run(tmp_path)
    assert state["overall_status"] == "COMPLETED"
    expected = [
        "run_state.json", "00_analysis_scope.json", "data/requirements.json",
        "data/source_registry.json", "data/observations.json", "data/sufficiency.json",
        "research/claims.json", "research/research_model.json", "review/review_issues.json",
        "fact_check/verified_claims.json", "human/feedback.json",
        "strategy/recommendations.json", "strategy/report_model.json",
        "quality/issues.json", "quality/summary.json", "dashboard/dashboard_data.json",
        "rendered/01_research_brief.md", "rendered/02_review_notes.md",
        "rendered/03_fact_check.md", "rendered/04_final_report.md", "run_manifest.json",
    ]
    assert all((folder / x).is_file() for x in expected)
    assert registry.call_count() == 5
    assert all(x["status"] in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} for x in state["stages"].values())
    manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
    report_data = json.loads((folder / "04_report_data.json").read_text(encoding="utf-8"))
    dashboard = json.loads((folder / "06_dashboard_data.json").read_text(encoding="utf-8"))
    assert manifest["final_status"] == "COMPLETED" and manifest["current_stage"] == "quality"
    assert report_data["metrics"] and report_data["_meta"]["observation_ids"] == ["OBS_fixture_revenue"]
    assert report_data["metrics"][0]["verification_status"] == "SUPPORTED"
    assert report_data["metrics"][0]["temporal_status"] == "HISTORICAL"
    assert report_data["metrics"][0]["confidence"] == "HIGH"
    assert dashboard["executive_summary"]["conclusion"] == "Protect fixture margin."
    assert len(dashboard["observations"]) == len(dashboard["evidence"]) == 1
    assert dashboard["evidence"][0]["source_fact_ids"] == ["F1"]
    claim_a = json.loads((folder / "research/claims.json").read_text(encoding="utf-8"))["claims"][0]["claim_id"]
    claim_b = json.loads((folder / "fact_check/verified_claims.json").read_text(encoding="utf-8"))["claims"][0]["claim_id"]
    assert claim_a == claim_b
    for agent in registry.agents.values():
        for call in agent.calls:
            assert all(not key.endswith(".md") for key in call["inputs"])


def test_strict_v2_rejects_legacy_markdown_without_persisting_success(tmp_path):
    registry = FakeAgentRegistry({"research": "legacy"})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "strict"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "strict", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research"])
    assert state["stages"]["research"]["status"] == "BLOCKED"
    assert state["stages"]["research"]["attempt"] == 2
    assert state["stages"]["research"]["error_codes"] == ["AGENT_OUTPUT_NOT_STRUCTURED"]
    assert json.loads((folder / "research/claims.json").read_text())["claims"] == []


def test_stage_retry_invalid_json_then_success_and_current_stage_only(tmp_path):
    registry = FakeAgentRegistry({"research": ["invalid_json", "success"]})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "retry"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "retry", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research"])
    assert state["stages"]["research"]["status"] == "COMPLETE"
    assert registry.call_count("research") == 2
    assert registry.call_count("data") == 1
    assert registry.call_count("review") == 0
    request = registry.get("research").calls[1]
    assert request["output_schema"]["artifact_contract"]
    assert request["error_packet"][0]["json_pointer"] == "/"


def test_blocked_state_is_projected_to_manifest_for_audit_discovery(tmp_path):
    registry = FakeAgentRegistry({"review": ["semantic_error", "semantic_error"]})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "blocked"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "blocked", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research", "review"])
    manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
    assert state["overall_status"] == manifest["final_status"] == "BLOCKED_QUALITY"
    assert state["current_stage"] == manifest["current_stage"] == "review"
    assert manifest["review_status"] == "FAILED"


def test_review_blocker_alias_completes_without_spending_retry(tmp_path):
    registry = FakeAgentRegistry()
    artifacts = registry.get("review")
    original_run = artifacts.run

    def blocker_run(request):
        raw = json.loads(original_run(request))
        raw["artifacts"]["review_notes"] = [{
            "review_id": "R1", "severity": "BLOCKER", "category": "evidence",
            "issue": "Material gap", "evidence": "CLM_fixture_revenue",
            "required_action": "Narrow claim", "status": "OPEN",
        }]
        return json.dumps(raw)

    artifacts.run = blocker_run
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "alias"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "alias", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research", "review"])
    assert state["stages"]["review"]["status"] == "COMPLETE"
    saved = json.loads((folder / "02_review_notes.json").read_text(encoding="utf-8"))
    assert saved["issues"][0]["severity"] == "CRITICAL"


def test_semantic_retry_fact_source_and_atomic_claim(tmp_path):
    for stage in ("research", "fact_check"):
        registry = FakeAgentRegistry({stage: ["semantic_error", "success"]})
        folder, state, registry = make_run(tmp_path / stage, registry=registry)
        assert state["overall_status"] == "COMPLETED"
        assert registry.call_count(stage) == 2


def test_retry_limit_technical_and_upstream_are_distinct(tmp_path):
    for label, modes, expected, calls in [
        ("semantic", {"research": ["semantic_error", "semantic_error"]}, "BLOCKED_QUALITY", 2),
        ("technical", {"research": "technical"}, "FAILED_TECHNICAL", 2),
        ("upstream", {"data": "semantic_error"}, "BLOCKED_DATA", 2),
    ]:
        root = tmp_path / label; root.mkdir()
        scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = root / "run"; folder.mkdir()
        (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
        PipelineV2Service(root).initialize(folder, label, scope)
        registry = FakeAgentRegistry(modes)
        state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research"])
        assert state["overall_status"] == expected
        target = "data" if label == "upstream" else "research"
        assert registry.call_count(target) == calls


def test_data_critical_gap_runs_one_bounded_search_then_promotes_only_passing_candidate(tmp_path):
    registry = FakeAgentRegistry({"data": ["semantic_error", "success"]})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "gap_search"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "gap_search", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data"])
    assert state["stages"]["data"]["status"] == "COMPLETE"
    assert registry.call_count("data") == 2
    retry = registry.get("data").calls[1]
    assert retry["previous_structured_output"]
    assert {row["rule_id"] for row in retry["error_packet"]} == {"DATA_CRITICAL_INSUFFICIENT"}
    assert retry["repair_context"]["mode"] == "BOUNDED_CRITICAL_GAP_SEARCH"
    assert retry["repair_context"]["targets"][0]["gaps"][0]["recommended_queries"]
    assert (folder / "quality/candidates/data_attempt_1.json").is_file()
    assert (folder / "quality/candidates/data_attempt_2.json").is_file()
    canonical = json.loads((folder / "data/sufficiency.json").read_text(encoding="utf-8"))
    assert canonical["overall_status"] == "PASS"
    assert any(row["event"] == "BOUNDED_GAP_SEARCH_STARTED" for row in state["events"])


def test_data_schema_retry_does_not_consume_the_single_bounded_gap_search(tmp_path):
    registry = FakeAgentRegistry({"data": ["invalid_json", "semantic_error", "success"]})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "late_gap"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "late_gap", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data"])
    assert state["stages"]["data"]["status"] == "COMPLETE"
    assert registry.call_count("data") == 3
    assert (folder / "quality/candidates/data_attempt_1_invalid.json").is_file()
    repair = registry.get("data").calls[2]
    assert repair["repair_context"]["mode"] == "BOUNDED_CRITICAL_GAP_SEARCH"
    assert repair["repair_context"]["target_dataset_ids"]
    assert any(row["event"] == "BOUNDED_GAP_SEARCH_STARTED" for row in state["events"])


def test_fact_revision_preserves_upstream_and_revalidates_related_feedback(tmp_path):
    feedback = {"schema_version": "2.0", "feedback": [
        {"feedback_id": "HFB_related", "claim_ids": ["CLM_fixture_revenue"], "status": "RESOLVED"},
        {"feedback_id": "HFB_other", "claim_ids": ["CLM_other"], "status": "RESOLVED"},
    ]}
    folder, _, _ = make_run(tmp_path, human_feedback=feedback)
    research_before = (folder / "research/claims.json").read_bytes()
    fact_before = (folder / "fact_check/verified_claims.json").read_bytes()
    plan = plan_revision(folder, "FACT_VERIFICATION", affected_object_ids=["CLM_fixture_revenue"])
    registry = FakeAgentRegistry()
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    revision = executor.create(folder, plan)
    copied_feedback = json.loads((revision / "human/feedback.json").read_text())["feedback"]
    assert copied_feedback[0]["status"] == "NEEDS_REVALIDATION"
    assert copied_feedback[1]["status"] == "RESOLVED"
    paused = executor.execute(folder, plan.revision_id)
    assert paused["plan_status"] == "AWAITING_HUMAN_REVIEW"
    done = executor.resume(folder, plan.revision_id, human_feedback=feedback)
    assert done["plan_status"] == "COMPLETED"
    assert registry.call_count("fact_check") == 1 and registry.call_count("strategy") == 1
    assert registry.call_count("data") == registry.call_count("research") == registry.call_count("review") == 0
    assert (folder / "research/claims.json").read_bytes() == research_before
    assert (folder / "fact_check/verified_claims.json").read_bytes() == fact_before
    assert load_run_state(folder)["active_revision_id"] == plan.revision_id


def test_failed_revision_never_becomes_active_and_can_resume(tmp_path):
    folder, _, _ = make_run(tmp_path)
    base_active = load_run_state(folder)["active_revision_id"]
    plan = plan_revision(folder, "STRATEGY_ONLY")
    registry = FakeAgentRegistry({"strategy": ["semantic_error", "semantic_error"]})
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    executor.create(folder, plan)
    failed = executor.execute(folder, plan.revision_id)
    assert failed["plan_status"] == "FAILED"
    assert load_run_state(folder)["active_revision_id"] == base_active


def test_full_research_routes_by_scope_change_and_pauses_for_human(tmp_path):
    for changed in (False, True):
        root = tmp_path / str(changed); root.mkdir()
        folder, _, _ = make_run(root)
        plan = plan_revision(folder, "FULL_RESEARCH", scope_changed=changed, scope_diff={"geography": ["Old", "New"]} if changed else {})
        registry = FakeAgentRegistry(); executor = RevisionExecutor(PipelineV2Orchestrator(registry))
        revision = executor.create(folder, plan)
        execution = json.loads((revision / "execution_state.json").read_text())
        assert (execution["pending_stages"][0] == "scope") is changed
        paused = executor.execute(folder, plan.revision_id)
        assert paused["plan_status"] == "AWAITING_HUMAN_REVIEW"
        done = executor.resume(folder, plan.revision_id, human_feedback={"schema_version": "2.0", "feedback": []})
        assert done["plan_status"] == "COMPLETED"
        assert registry.call_count() == plan.estimated_agent_calls == 5
        assert load_run_state(folder)["active_revision_id"] == plan.revision_id
