from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from pipeline_v2.model import load_run_state, save_run_state
from pipeline_v2.orchestrator import PipelineV2Orchestrator
from pipeline_v2.revision import RevisionExecutor, plan_revision
from pipeline_v2.service import PipelineV2Service
from pipeline_v2.agent_provider import describe_agent_error
from pipeline_v2.fact_check import normalize_fact_check
from pipeline_v2.envelope import AgentOutputError, make_envelope, parse_envelope
from pipeline_v2.contracts.validators import fact_check_gate
from pipeline_v2.ids import stable_id
from pipeline_v2.report_model import normalize_report_model
from pipeline_v2.report_protocol import normalize_scenarios, normalize_strategic_items
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
    assert report_data["risks"][0]["item_id"] == "RISK_fixture_margin"
    assert report_data["opportunities"][0]["item_id"] == "OPP_fixture_margin"
    assert report_data["risks"][0]["source_fact_ids"] == ["F1"]
    assert dashboard["risks"] == report_data["risks"]
    assert dashboard["opportunities"] == report_data["opportunities"]
    assert dashboard["report_data"]["risks"] == report_data["risks"]
    assert dashboard["report_data"]["opportunities"] == report_data["opportunities"]
    assert dashboard["executive_summary"]["conclusion"] == "Protect fixture margin."
    assert len(dashboard["observations"]) == len(dashboard["evidence"]) == 1
    assert dashboard["evidence"][0]["source_fact_ids"] == ["F1"]
    claim_a = json.loads((folder / "research/claims.json").read_text(encoding="utf-8"))["claims"][0]["claim_id"]
    claim_b = json.loads((folder / "fact_check/verified_claims.json").read_text(encoding="utf-8"))["claims"][0]["claim_id"]
    assert claim_a == claim_b
    for agent in registry.agents.values():
        for call in agent.calls:
            assert all(not key.endswith(".md") for key in call["inputs"])


def test_parse_envelope_recovers_only_a_missing_final_root_brace():
    raw = json.dumps(make_envelope(
        run_id="run", revision_id="rev_001", stage="data", attempt=1,
        artifacts={
            "requirements": {"datasets": []}, "source_registry": {"sources": []},
            "observations": {"observations": []}, "sufficiency": {"datasets": []},
        }, agent_role="Data Agent",
    ), ensure_ascii=False)
    parsed = parse_envelope(raw[:-1], stage="data", attempt=1, run_id="run", revision_id="rev_001")
    assert parsed["artifacts"]["observations"] == {"observations": []}
    assert "trailing_root_brace" in parsed["metadata"]["normalized_fields"]
    with pytest.raises(AgentOutputError):
        parse_envelope(raw[:-2], stage="data", attempt=1, run_id="run", revision_id="rev_001")


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


def test_missing_envelope_provenance_is_normalized_without_live_retry(tmp_path):
    registry = FakeAgentRegistry()
    agent = registry.get("research")
    original_run = agent.run

    def omit_metadata(request):
        payload = json.loads(original_run(request))
        payload.pop("metadata", None)
        return json.dumps(payload, ensure_ascii=False)

    agent.run = omit_metadata
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "metadata"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "metadata", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research"])
    assert state["stages"]["research"]["status"] == "COMPLETE"
    assert registry.call_count("research") == 1
    candidate = json.loads((folder / "quality/candidates/research_attempt_1.json").read_text(encoding="utf-8"))
    assert candidate["metadata"]["normalized_by"] == "PipelineV2Orchestrator"
    assert set(candidate["metadata"]["normalized_fields"]) == {"generated_at", "agent_role"}


def test_exact_same_name_list_wrapper_is_normalized_without_retry():
    payload = make_envelope(
        run_id="run", revision_id="rev_000", stage="strategy", attempt=1,
        artifacts={
            "recommendations": {"recommendations": [{"recommendation_id": "REC_1"}]},
            "report_model": {"paragraphs": []},
        },
        agent_role="strategy",
    )
    parsed = parse_envelope(
        json.dumps(payload), stage="strategy", attempt=1,
        run_id="run", revision_id="rev_000",
    )
    assert parsed["artifacts"]["recommendations"] == [{"recommendation_id": "REC_1"}]
    assert parsed["metadata"]["normalized_artifacts"] == ["recommendations"]


def test_ambiguous_list_wrapper_still_fails_strict_contract():
    payload = make_envelope(
        run_id="run", revision_id="rev_000", stage="strategy", attempt=1,
        artifacts={
            "recommendations": {"recommendations": [], "extra": "unsafe"},
            "report_model": {"paragraphs": []},
        },
        agent_role="strategy",
    )
    try:
        parse_envelope(
            payload, stage="strategy", attempt=1,
            run_id="run", revision_id="rev_000",
        )
    except AgentOutputError as error:
        assert error.code == "AGENT_ARTIFACT_SCHEMA_INVALID"
    else:
        raise AssertionError("Ambiguous wrappers must not be normalized")


def test_qualitative_scenario_is_preserved_without_inventing_numeric_points():
    scenarios, errors = normalize_scenarios([{
        "scenario_id": "SCN_BASE", "name": "基准情景", "label": "INFERENCE",
        "conditions": "需求转化通过内部审查", "implications": "维持审慎投入",
        "actions": ["按需求配置资源"], "claim_ids": ["CLM_1"],
    }])
    assert errors == []
    assert scenarios[0]["label"] == "基准情景"
    assert scenarios[0]["claim_type"] == "INFERENCE"
    assert scenarios[0]["value_type"] == "QUALITATIVE"
    assert scenarios[0]["annual_points"] == []
    assert scenarios[0]["starting_value"] is None
    assert scenarios[0]["source_fact_ids"] == ["CLM_1"]


def test_strategy_cannot_bypass_incomplete_human_gate(tmp_path):
    folder, _, registry = make_run(tmp_path)
    state = load_run_state(folder)
    state["stages"]["human"]["status"] = "AWAITING_USER"
    state["overall_status"] = "AWAITING_HUMAN_REVIEW"
    save_run_state(folder, state)
    before = registry.call_count("strategy")
    try:
        PipelineV2Orchestrator(registry).execute(folder, stages=["strategy"])
    except RuntimeError as error:
        assert "Human Review" in str(error)
    else:
        raise AssertionError("Strategy must not bypass Human Review")
    assert registry.call_count("strategy") == before


def test_targeted_gap_search_preserves_evidence_and_stops_for_new_human_review(tmp_path):
    folder, _, _ = make_run(tmp_path)
    registry = FakeAgentRegistry()
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    targets = [{
        "gap_id": "G_operating_metrics_001", "dataset_id": "operating_metrics",
        "priority": "IMPORTANT", "missing_field": "dataset", "needed_observations": 1,
        "recommended_queries": [{"query_text": "Example Group operating metrics official"}],
    }]
    plan, revision = executor.create_targeted_gap_search(folder, folder, targets)
    result = executor.execute(folder, plan.revision_id)
    assert result["plan_status"] == "AWAITING_HUMAN_REVIEW"
    assert result["pending_stages"][0] == "human"
    assert registry.call_count("data") == 1
    assert registry.call_count("research") == 1
    assert registry.call_count("review") == 1
    assert registry.call_count("fact_check") == 1
    assert registry.call_count("strategy") == 0
    request = registry.get("data").calls[0]
    assert request["repair_context"]["mode"] == "TARGETED_GAP_SEARCH"
    assert request["repair_context"]["target_dataset_ids"] == ["operating_metrics"]
    assert request["inputs"]["data/observations.json"]["observations"]
    observations = json.loads((revision / "data/observations.json").read_text(encoding="utf-8"))["observations"]
    assert {row["observation_id"] for row in observations} >= {"OBS_fixture_revenue"}
    marker = json.loads((revision / "data/targeted_gap_search.json").read_text(encoding="utf-8"))
    assert marker["status"] == "COMPLETED"
    assert json.loads((revision / "human/feedback.json").read_text(encoding="utf-8"))["feedback"] == []
    second, _ = executor.create_targeted_gap_search(folder, folder, targets, max_rounds=2)
    assert second.revision_id == "rev_002"
    second_result = executor.execute(folder, second.revision_id)
    assert second_result["plan_status"] == "AWAITING_HUMAN_REVIEW"
    try:
        executor.create_targeted_gap_search(folder, folder, targets, max_rounds=2)
    except RuntimeError as error:
        assert "limit reached" in str(error)
    else:
        raise AssertionError("Gap-search limit must apply across the full revision history")


def test_list_shaped_data_artifacts_are_repairable_contract_errors(tmp_path):
    registry = FakeAgentRegistry()
    agent = registry.get("data")
    original_run = agent.run

    def list_first_then_valid(request):
        payload = json.loads(original_run(request))
        if request["attempt"] == 1:
            for name, key in {
                "requirements": "datasets", "source_registry": "sources",
                "observations": "observations",
            }.items():
                payload["artifacts"][name] = payload["artifacts"][name][key]
        return json.dumps(payload, ensure_ascii=False)

    agent.run = list_first_then_valid
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "list_data"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "list_data", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data"])
    assert state["stages"]["data"]["status"] == "COMPLETE"
    assert state["overall_status"] != "FAILED_TECHNICAL"
    assert registry.call_count("data") == 2
    retry = registry.get("data").calls[1]
    assert retry["error_packet"][0]["rule_id"] == "AGENT_ARTIFACT_SCHEMA_INVALID"
    assert "/artifacts/requirements" in retry["error_packet"][0]["reason"]


def test_review_receives_canonical_source_observation_and_sufficiency_inputs(tmp_path):
    registry = FakeAgentRegistry()
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "review_evidence"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "review_evidence", scope)
    PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research", "review"])
    inputs = registry.get("review").calls[0]["inputs"]
    assert set(inputs) >= {
        "data/source_registry.json", "data/observations.json", "data/sufficiency.json",
        "research/claims.json", "research/research_model.json",
    }


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


def test_fact_check_verification_records_wrapper_is_normalized_without_retry(tmp_path):
    """Regression for the live Schneider response shape seen on 2026-08-13."""
    registry = FakeAgentRegistry()
    agent = registry.get("fact_check")
    original_run = agent.run

    def observation_centric_run(request):
        payload = json.loads(original_run(request))
        payload["artifacts"]["verified_claims"] = {
            "schema_version": "2.0",
            "verification_records": [{
                "observation_id": "OBS_fixture_revenue",
                "claim_ids": ["CLM_fixture_revenue"],
                "verification_status": "SUPPORTED",
                "temporal_status": "HISTORICAL",
                "source_ids": ["SRC_fixture"],
            }],
        }
        return json.dumps(payload, ensure_ascii=False)

    agent.run = observation_centric_run
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "fact_wrapper"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "fact_wrapper", scope)
    state = PipelineV2Orchestrator(registry).execute(
        folder, stages=["scope", "data", "research", "review", "fact_check"]
    )

    assert state["stages"]["fact_check"]["status"] == "COMPLETE"
    assert registry.call_count("fact_check") == 1
    saved = json.loads((folder / "fact_check/verified_claims.json").read_text(encoding="utf-8"))
    assert [row["claim_id"] for row in saved["claims"]] == ["CLM_fixture_revenue"]
    assert saved["claims"][0]["verification_status"] == "SUPPORTED"
    assert saved["observation_verifications"][0]["observation_id"] == "OBS_fixture_revenue"


def test_bare_observation_fact_list_accounts_for_unclaimed_observations():
    sources = [{"source_id": "SRC_A", "source_grade": "GRADE_A"}]
    observations = [
        {"observation_id": "OBS_CLAIMED", "source_id": "SRC_A"},
        {"observation_id": "OBS_UNCLAIMED", "source_id": "SRC_A"},
    ]
    research_claims = [{
        "claim_id": "CLM_A", "statement": "A supported atomic claim.",
        "observation_ids": ["OBS_CLAIMED"], "source_ids": ["SRC_A"],
        "claim_type": "FACT", "atomicity_status": "ATOMIC",
    }]
    live_artifact = [
        {"observation_id": "OBS_CLAIMED", "claim_ids": ["CLM_A"], "verification_status": "SUPPORTED", "source_ids": ["SRC_A"]},
        {"observation_id": "OBS_UNCLAIMED", "claim_ids": [], "verification_status": "NOT_CHECKED", "source_ids": ["SRC_A"]},
    ]

    normalized = normalize_fact_check(live_artifact, research_claims, observations, sources)
    result = fact_check_gate(normalized, {
        "sources": sources, "observations": observations, "research_claims": research_claims,
    })

    assert result.can_continue is True
    assert normalized["claims"][0]["text"] == "A supported atomic claim."
    assert {row["observation_id"] for row in normalized["observation_verifications"]} == {
        "OBS_CLAIMED", "OBS_UNCLAIMED",
    }
    unclaimed = next(row for row in normalized["observation_verifications"] if row["observation_id"] == "OBS_UNCLAIMED")
    assert unclaimed["claim_ids"] == []
    assert unclaimed["verification_status"] == "NOT_CHECKED"


def test_blocked_fact_check_candidate_recovers_in_immutable_revision(tmp_path):
    registry = FakeAgentRegistry()
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "blocked_fact"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "blocked_fact", scope)
    PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research", "review"])
    candidate = json.loads(registry.get("fact_check").run({
        "run_id": "blocked_fact", "revision_id": "rev_000", "attempt": 2,
        "inputs": {},
    }))
    candidate["artifacts"]["verified_claims"] = [{
        "observation_id": "OBS_fixture_revenue",
        "claim_ids": ["CLM_fixture_revenue"],
        "verification_status": "SUPPORTED",
        "source_ids": ["SRC_fixture"],
    }]
    candidates = folder / "quality/candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    (candidates / "fact_check_attempt_2.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )
    state = load_run_state(folder)
    state["overall_status"] = "BLOCKED_QUALITY"
    state["current_stage"] = "fact_check"
    state["stages"]["fact_check"].update(
        status="BLOCKED", validation_status="BLOCKED",
        error_codes=["FACT_OBSERVATION_COVERAGE"], attempt=2,
    )
    save_run_state(folder, state)
    base_state_before = (folder / "run_state.json").read_bytes()

    recovery_registry = FakeAgentRegistry()
    executor = RevisionExecutor(PipelineV2Orchestrator(recovery_registry))
    result = executor.recover_blocked_fact_check(folder)
    revision = folder / "revisions" / result["revision_id"]

    assert result["plan_status"] == "AWAITING_HUMAN_REVIEW"
    assert recovery_registry.call_count() == 0
    assert (folder / "run_state.json").read_bytes() == base_state_before
    revision_state = load_run_state(revision)
    assert revision_state["stages"]["fact_check"]["status"] == "COMPLETE"
    assert revision_state["overall_status"] == "AWAITING_HUMAN_REVIEW"
    saved = json.loads((revision / "fact_check/verified_claims.json").read_text(encoding="utf-8"))
    assert saved["claims"][0]["claim_id"] == "CLM_fixture_revenue"
    assert saved["observation_verifications"][0]["verification_status"] == "SUPPORTED"


def test_continue_strategy_completes_and_activates_recovered_revision(tmp_path, monkeypatch):
    from ui.actions import continue_strategy

    registry = FakeAgentRegistry()
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "resume_fact"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "resume_fact", scope)
    PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data", "research", "review"])
    candidate = json.loads(registry.get("fact_check").run({
        "run_id": "resume_fact", "revision_id": "rev_000", "attempt": 2, "inputs": {},
    }))
    candidates = folder / "quality/candidates"; candidates.mkdir(parents=True, exist_ok=True)
    (candidates / "fact_check_attempt_2.json").write_text(json.dumps(candidate), encoding="utf-8")
    state = load_run_state(folder)
    state.update(overall_status="BLOCKED_QUALITY", current_stage="fact_check")
    state["stages"]["fact_check"].update(status="BLOCKED", validation_status="BLOCKED", attempt=2)
    save_run_state(folder, state)
    recovery = RevisionExecutor(PipelineV2Orchestrator(FakeAgentRegistry())).recover_blocked_fact_check(folder)
    revision_id = recovery["revision_id"]
    revision = folder / "revisions" / revision_id
    (revision / "human/feedback.json").write_text(
        json.dumps({"schema_version": "2.0", "feedback": []}), encoding="utf-8"
    )
    continuation_registry = FakeAgentRegistry()
    monkeypatch.setattr("ui.actions.create_ready_agent_registry", lambda: continuation_registry)
    run = {
        **load_run_state(revision), "folder": str(revision), "base_folder": str(folder),
        "revision_id": revision_id, "read_only": False,
    }

    result = continue_strategy(run)

    assert result["plan_status"] == "COMPLETED"
    assert continuation_registry.call_count("strategy") == 1
    assert continuation_registry.call_count("fact_check") == 0
    assert load_run_state(folder)["active_revision_id"] == revision_id
    assert load_run_state(revision)["overall_status"] == "COMPLETED"


def test_continue_strategy_builds_quality_before_dashboard(tmp_path, monkeypatch):
    from ui.actions import continue_strategy

    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "ordered"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "ordered", scope)
    registry = FakeAgentRegistry()
    PipelineV2Orchestrator(registry).execute(
        folder, stages=["scope", "data", "research", "review", "fact_check"],
    )
    state = load_run_state(folder)
    state["overall_status"] = "AWAITING_HUMAN_REVIEW"
    state["stages"]["human"]["status"] = "AWAITING_USER"
    save_run_state(folder, state)
    (folder / "human/feedback.json").write_text(
        json.dumps({"schema_version": "2.0", "feedback": []}), encoding="utf-8",
    )
    monkeypatch.setattr("ui.actions.create_ready_agent_registry", lambda: registry)

    result = continue_strategy({**state, "folder": str(folder), "read_only": False})

    assert result["overall_status"] == "COMPLETED"
    events = [row["stage"] for row in result["events"] if row.get("event") == "STAGE_STARTED"]
    assert events.index("quality") < events.index("dashboard")
    dashboard = json.loads((folder / "dashboard/dashboard_data.json").read_text(encoding="utf-8"))
    assert dashboard["quality_status"] != "PENDING"
    assert dashboard["quality"]["overall_status"] != "PENDING"
    assert Path(result["dashboard_html"]).is_file()


def test_continue_strategy_refuses_unpassed_fact_check_before_agent_creation(tmp_path, monkeypatch):
    from ui.actions import continue_strategy

    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "unsafe"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "unsafe", scope)
    state = load_run_state(folder)
    state["stages"]["fact_check"]["status"] = "BLOCKED"
    save_run_state(folder, state)
    monkeypatch.setattr(
        "ui.actions.create_ready_agent_registry",
        lambda: (_ for _ in ()).throw(AssertionError("Agent registry must not be created")),
    )
    import pytest
    with pytest.raises(RuntimeError, match="Fact Check 尚未通过"):
        continue_strategy({**state, "folder": str(folder), "read_only": False})


def test_orchestrator_refuses_strategy_when_fact_check_is_not_complete(tmp_path):
    import pytest

    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "direct_unsafe"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "direct_unsafe", scope)
    registry = FakeAgentRegistry()
    with pytest.raises(RuntimeError, match="Fact Check must pass"):
        PipelineV2Orchestrator(registry).execute(folder, stages=["strategy"])
    assert registry.call_count("strategy") == 0


def test_migrate_decisions_to_revision_enriches_legacy_feedback(tmp_path):
    from ui.actions import migrate_decisions_to_revision

    folder, _, _ = make_run(tmp_path)
    decision_id = "DEC_legacy"
    review = {
        "schema_version": "2.0", "issues": [{
            "review_id": "R1", "issue": "Concrete issue", "evidence": "Concrete evidence",
            "required_action": "Concrete action", "severity": "MEDIUM", "category": "metadata",
            "status": "OPEN",
        }],
    }
    # Align the stored ID with the stable UI mapping.
    decision_id = stable_id("decision", "fixture_run", "R1")
    (folder / "review/review_issues.json").write_text(json.dumps(review), encoding="utf-8")
    (folder / "human/feedback.json").write_text(json.dumps({
        "schema_version": "2.0", "feedback": [{
            "feedback_id": "HFB_old", "decision_id": decision_id,
            "choice": "接受", "status": "RESOLVED",
        }],
    }), encoding="utf-8")
    plan = plan_revision(folder, "LOCAL_REPAIR")
    revision = RevisionExecutor(PipelineV2Orchestrator(FakeAgentRegistry())).create(folder, plan)
    (revision / "human/feedback.json").write_text(
        json.dumps({"schema_version": "2.0", "feedback": []}), encoding="utf-8"
    )

    result = migrate_decisions_to_revision(
        {"folder": str(folder), "run_id": "fixture_run"}, plan.revision_id
    )
    migrated = json.loads((revision / "human/feedback.json").read_text(encoding="utf-8"))["feedback"][0]

    assert result["migrated"] == 1
    assert migrated["review_id"] == "R1"
    assert migrated["decision_snapshot"]["issue"] == "Concrete issue"
    assert migrated["decision_snapshot"]["required_action"] == "Concrete action"


def test_running_revision_agent_cannot_be_resumed_twice(tmp_path):
    import pytest

    folder, _, _ = make_run(tmp_path)
    plan = plan_revision(folder, "STRATEGY_ONLY")
    executor = RevisionExecutor(PipelineV2Orchestrator(FakeAgentRegistry()))
    revision = executor.create(folder, plan)
    execution_path = revision / "execution_state.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution.update(plan_status="RUNNING", current_stage="strategy")
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    state = load_run_state(revision)
    state["stages"]["strategy"]["status"] = "RUNNING"
    save_run_state(revision, state)

    with pytest.raises(RuntimeError, match="already running"):
        executor.resume(folder, plan.revision_id)


def test_human_feedback_process_paragraph_is_not_treated_as_external_fact():
    model = {"paragraphs": [
        {"section_id": "Human Feedback处理情况", "label": "FACT", "claim_ids": [], "text": "三项 Human Feedback 均记录为接受且状态为 RESOLVED。"},
        {"section_id": "市场事实", "label": "FACT", "claim_ids": [], "text": "External market fact."},
    ]}
    normalized = normalize_report_model(model)
    assert normalized["paragraphs"][0]["label"] == "PROCESS"
    assert normalized["paragraphs"][1]["label"] == "FACT"


def test_structured_risk_opportunity_fallback_uses_report_model_not_markdown():
    claims = [{"claim_id": "CLM_1", "display_id": "F1"}]
    model = {"paragraphs": [{
        "section_id": "risk-opportunity", "section_title": "风险与机会",
        "label": "INFERENCE", "text": "Evidence-linked strategic boundary.",
        "claim_ids": ["CLM_1"],
    }]}

    risks = normalize_strategic_items(model, claims, "risks")
    opportunities = normalize_strategic_items(model, claims, "opportunities")

    assert risks[0]["description"] == "Evidence-linked strategic boundary."
    assert opportunities[0]["description"] == "Evidence-linked strategic boundary."
    assert risks[0]["source_fact_ids"] == opportunities[0]["source_fact_ids"] == ["F1"]


def test_failed_report_revision_repairs_locally_without_agent_calls(tmp_path):
    folder, _, _ = make_run(tmp_path)
    plan = plan_revision(folder, "LOCAL_REPAIR")
    registry = FakeAgentRegistry()
    executor = RevisionExecutor(PipelineV2Orchestrator(registry))
    revision = executor.create(folder, plan)
    model_path = revision / "strategy/report_model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["paragraphs"].append({
        "section_id": "Human Feedback处理情况", "section_title": "Human Feedback处理情况",
        "label": "FACT", "text": "Human Feedback 已记录为接受且状态为 RESOLVED。",
        "claim_ids": [], "recommendation_ids": [],
    })
    model_path.write_text(json.dumps(model), encoding="utf-8")
    failed = executor.execute(folder, plan.revision_id)
    assert failed["failed_stage"] == "report"
    assert registry.call_count() == 0

    result = executor.repair_report_and_resume_locally(folder, plan.revision_id)

    assert result["plan_status"] == "COMPLETED"
    assert registry.call_count() == 0
    saved = json.loads(model_path.read_text(encoding="utf-8"))
    assert saved["paragraphs"][-1]["label"] == "PROCESS"


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


def test_forbidden_transport_is_recorded_without_html(tmp_path):
    registry = FakeAgentRegistry()
    registry.get("data").run = lambda request: (_ for _ in ()).throw(
        RuntimeError("unexpected status 403 Forbidden: <html><head>proxy page</head></html>")
    )
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "forbidden"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "forbidden", scope)
    state = PipelineV2Orchestrator(registry).execute(folder, stages=["scope", "data"])
    latest = state["events"][-1]
    assert state["overall_status"] == "FAILED_TECHNICAL"
    assert latest["detail"].startswith("CODEX_AUTH_FORBIDDEN")
    assert "<html>" not in latest["detail"]


def test_failed_base_run_recovery_uses_immutable_revision(tmp_path):
    failing_registry = FakeAgentRegistry({"research": "technical"})
    scope = json.loads(FIXTURE.read_text(encoding="utf-8")); folder = tmp_path / "resume_base"; folder.mkdir()
    (folder / "00_analysis_scope.json").write_text(json.dumps(scope), encoding="utf-8")
    PipelineV2Service(tmp_path).initialize(folder, "resume_base", scope)
    failed = PipelineV2Orchestrator(failing_registry).execute(
        folder, stages=["scope", "data", "research"]
    )
    assert failed["overall_status"] == "FAILED_TECHNICAL"
    state_before = (folder / "run_state.json").read_bytes()
    manifest_before = (folder / "run_manifest.json").read_bytes()
    data_before = (folder / "data/observations.json").read_bytes()

    recovering_registry = FakeAgentRegistry()
    plan = plan_revision(folder, "TECHNICAL_RETRY")
    executor = RevisionExecutor(PipelineV2Orchestrator(recovering_registry))
    revision = executor.create(folder, plan)
    recovered = executor.execute(folder, plan.revision_id)
    assert recovered["plan_status"] == "AWAITING_HUMAN_REVIEW"
    assert recovering_registry.call_count("data") == 0
    assert recovering_registry.call_count("research") == 1
    assert recovering_registry.call_count("review") == 1
    assert recovering_registry.call_count("fact_check") == 1
    assert (folder / "run_state.json").read_bytes() == state_before
    assert (folder / "run_manifest.json").read_bytes() == manifest_before
    assert (folder / "data/observations.json").read_bytes() == data_before
    revision_state = load_run_state(revision)
    assert revision_state["overall_status"] == "AWAITING_HUMAN_REVIEW"
    assert revision_state["revision_id"] == plan.revision_id


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
