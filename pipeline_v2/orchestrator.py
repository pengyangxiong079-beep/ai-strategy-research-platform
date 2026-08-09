"""Strict, resumable and dependency-injected Pipeline V2 orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .agents import AgentRegistry
from .contracts import validate_stage
from .envelope import AgentOutputError, parse_envelope
from .model import STAGE_ORDER, load_run_state, now_iso, save_run_state
from .renderer import render_fact_check, render_report, render_research, render_review
from .report_protocol import hash_file_consistent, report_data_payload, render_content_blocks, sha256_file, validate_report_data
from .quality import aggregate_quality
from .service import PipelineV2Service


AGENT_STAGES = ("data", "research", "review", "fact_check", "strategy")


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _write(path: Path, payload):
    from main import atomic_write_json
    atomic_write_json(path, payload)


class PipelineV2Orchestrator:
    def __init__(self, registry: AgentRegistry, *, max_attempts: int = 2):
        self.registry = registry
        self.max_attempts = max(1, int(max_attempts))

    def execute(self, folder, *, stages: Iterable[str] | None = None,
                human_feedback: dict | None = None, stop_before_human: bool = False) -> dict:
        folder = Path(folder)
        state = load_run_state(folder)
        if not state or state.get("pipeline_version") != "2.0":
            raise ValueError("严格V2编排器只能执行Canonical Pipeline V2运行")
        config = state.get("configuration", {})
        if not config.get("strict_structured_output") or config.get("allow_legacy_agent_output"):
            raise ValueError("V2严格结构化输出配置未启用")
        wanted = list(stages or STAGE_ORDER)
        for stage in wanted:
            if stage == "scope":
                if not self._run_scope(folder, state):
                    break
            elif stage in AGENT_STAGES:
                if not self._run_agent_stage(folder, state, stage):
                    break
            elif stage == "human":
                if stop_before_human and human_feedback is None:
                    self._await_human(folder, state)
                    break
                if not self._run_human(folder, state, human_feedback):
                    break
            elif stage == "report":
                if not self._run_report(folder, state):
                    break
            elif stage == "dashboard":
                if not self._run_dashboard(folder, state):
                    break
            elif stage == "quality":
                if not self._run_quality(folder, state):
                    break
        self._finish_if_possible(folder, state, wanted)
        return load_run_state(folder)

    def _begin(self, folder: Path, state: dict, stage: str, attempt: int | None = None):
        current = state["stages"][stage]
        current["status"] = "RUNNING"
        current["started_at"] = current.get("started_at") or now_iso()
        if attempt is not None:
            current["attempt"] = attempt
        state["current_stage"] = stage
        state["overall_status"] = "RUNNING" if state.get("revision_id") == "rev_000" else "REVISION_IN_PROGRESS"
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "STAGE_STARTED", "attempt": attempt})
        save_run_state(folder, state)

    def _run_scope(self, folder: Path, state: dict) -> bool:
        self._begin(folder, state, "scope")
        payload = _read(folder / "00_analysis_scope.json", {})
        return self._commit_gate(folder, state, "scope", payload, {})

    def _request(self, folder: Path, state: dict, stage: str, attempt: int,
                 previous_output=None, errors=None) -> dict:
        return {
            "pipeline_version": "2.0", "strict_structured_output": True,
            "run_id": state["run_id"], "revision_id": state["revision_id"],
            "stage": stage, "attempt": attempt,
            "inputs": self._stage_inputs(folder, stage),
            "previous_structured_output": previous_output,
            "error_packet": errors or [],
            "stage_contract": self._contract_description(stage),
            "output_schema": {"envelope": "2.0", "required_artifacts": self._expected(stage)},
            "remaining_attempts": self.max_attempts - attempt,
        }

    def _run_agent_stage(self, folder: Path, state: dict, stage: str) -> bool:
        previous = None
        last_errors = []
        start_attempt = max(1, int(state["stages"][stage].get("attempt", 0)) + 1)
        for attempt in range(start_attempt, self.max_attempts + 1):
            self._begin(folder, state, stage, attempt)
            request = self._request(folder, state, stage, attempt, previous, last_errors)
            calls = state.setdefault("agent_calls", {"total": 0, "by_stage": {}})
            calls["total"] = int(calls.get("total", 0)) + 1
            calls.setdefault("by_stage", {})[stage] = int(calls["by_stage"].get(stage, 0)) + 1
            save_run_state(folder, state)
            try:
                raw = self.registry.get(stage).run(request)
                envelope = parse_envelope(
                    raw, stage=stage, attempt=attempt, run_id=state["run_id"],
                    revision_id=state["revision_id"],
                )
                previous = envelope
                payload, context = self._gate_payload(folder, stage, envelope["artifacts"])
                gate = validate_stage(stage, payload, context)
                if gate.can_continue:
                    self._persist_artifacts(folder, stage, envelope["artifacts"])
                    return self._commit_gate(folder, state, stage, payload, context, gate=gate)
                last_errors = [self._normalize_issue(x, attempt) for x in gate.errors]
            except AgentOutputError as error:
                last_errors = [error.to_issue()]
                previous = None
            except Exception as error:  # technical failures stay distinct
                state["stages"][stage]["status"] = "FAILED_TECHNICAL"
                state["overall_status"] = "FAILED_TECHNICAL"
                state["stages"][stage]["error_codes"] = ["AGENT_TECHNICAL_FAILURE"]
                state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "FAILED_TECHNICAL", "detail": str(error)[:300], "attempt": attempt})
                save_run_state(folder, state)
                return False

            repair_types = {x.get("repair_type") for x in last_errors}
            state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "GATE_RETRY_REQUIRED", "attempt": attempt, "error_codes": [x.get("rule_id") for x in last_errors]})
            if repair_types != {"STAGE_RETRY"}:
                if "HUMAN_REQUIRED" in repair_types:
                    self._request_human(folder, state, stage, last_errors)
                else:
                    if "UPSTREAM_DATA_REQUIRED" in repair_types:
                        _write(folder / "quality/upstream_action.json", {
                            "schema_version": "2.0", "stage": stage, "status": "PLANNED",
                            "recommended_action": "GAP_SEARCH" if stage == "data" else "CREATE_REVISION_PLAN",
                            "errors": last_errors,
                        })
                    self._block(folder, state, stage, last_errors, "BLOCKED_DATA" if "UPSTREAM_DATA_REQUIRED" in repair_types and stage == "data" else "BLOCKED_QUALITY")
                return False
            if attempt >= self.max_attempts:
                self._block(folder, state, stage, last_errors, "BLOCKED_QUALITY")
                return False
            save_run_state(folder, state)
        return False

    def _run_human(self, folder: Path, state: dict, feedback: dict | None) -> bool:
        self._begin(folder, state, "human")
        payload = feedback or _read(folder / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
        _write(folder / "human/feedback.json", payload)
        return self._commit_gate(folder, state, "human", payload, {})

    def _await_human(self, folder: Path, state: dict):
        state["current_stage"] = "human"
        state["stages"]["human"]["status"] = "AWAITING_USER"
        state["overall_status"] = "AWAITING_HUMAN_REVIEW"
        state["primary_action"] = "REVIEW_DECISIONS"
        state.setdefault("events", []).append({"at": now_iso(), "stage": "human", "event": "AWAITING_HUMAN_REVIEW"})
        save_run_state(folder, state)

    def _request_human(self, folder: Path, state: dict, stage: str, errors: list[dict]):
        decisions = [{
            "decision_id": x.get("error_id"), "source_stage": stage,
            "title": x.get("reason") or x.get("rule_id"), "why": x.get("reason"),
            "options": ["接受限制", "要求修改", "取消"], "status": "PENDING",
        } for x in errors]
        _write(folder / "human/decisions.json", {"schema_version": "2.0", "decisions": decisions})
        state["stages"][stage]["status"] = "AWAITING_USER"
        state["overall_status"] = "AWAITING_HUMAN_REVIEW"
        state["current_stage"] = stage
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "HUMAN_DECISION_REQUIRED"})
        save_run_state(folder, state)

    def _run_report(self, folder: Path, state: dict) -> bool:
        self._begin(folder, state, "report")
        report_model = _read(folder / "strategy/report_model.json", {})
        claims = _read(folder / "fact_check/verified_claims.json", {"claims": []}).get("claims", [])
        scope = _read(folder / "00_analysis_scope.json", {})
        narrative = " ".join(str(row.get("text") or "") for row in report_model.get("paragraphs", []))
        scenario_terms = ("保守", "基准", "乐观")
        requires_scenarios = all(term in narrative for term in scenario_terms) or all(term in narrative.lower() for term in ("conservative", "base", "optimistic"))
        report_context = {"claims": claims, "required_sections": scope.get("required_sections", []), "requires_scenarios": requires_scenarios}
        gate = validate_stage("report", report_model, report_context)
        if not gate.can_continue:
            self._block(folder, state, "report", gate.errors, "BLOCKED_QUALITY")
            return False
        sources = _read(folder / "data/sources.json", _read(folder / "data/source_registry.json", {"sources": []})).get("sources", [])
        recs = _read(folder / "strategy/recommendations.json", {"recommendations": []}).get("recommendations", [])
        rendered = folder / "rendered"
        rendered.mkdir(parents=True, exist_ok=True)
        research = _read(folder / "research/research_model.json", {"sections": []}).get("sections", [])
        research_claims = _read(folder / "research/claims.json", {"claims": []}).get("claims", [])
        review = _read(folder / "02_review_notes.json", _read(folder / "review/review_notes.json", {"issues": []})).get("issues", [])
        (rendered / "01_research_brief.md").write_text(render_research(research, research_claims), encoding="utf-8")
        (rendered / "02_review_notes.md").write_text(render_review(review), encoding="utf-8")
        (rendered / "03_fact_check.md").write_text(render_fact_check(claims, sources), encoding="utf-8")
        blocks = report_data_payload(report_model, claims, recs, "", run_id=state["run_id"], revision_id=state["revision_id"])["content_blocks"]
        markdown = render_content_blocks(report_model.get("title", "战略研究报告"), blocks)
        (rendered / "04_final_report.md").write_text(markdown, encoding="utf-8")
        (folder / "04_final_report.md").write_text(markdown, encoding="utf-8")
        report_data = report_data_payload(report_model, claims, recs, markdown, run_id=state["run_id"], revision_id=state["revision_id"])
        report_data["meta"]["final_report_sha256"] = sha256_file(folder / "04_final_report.md")
        schema_errors = validate_report_data(report_data)
        if schema_errors:
            self._block(folder, state, "report", [{"rule_id": "REPORT_DATA_SCHEMA_INVALID", "reason": error, "stage": "report", "repair_type": "STAGE_RETRY"} for error in schema_errors], "BLOCKED_QUALITY")
            return False
        _write(folder / "04_report_data.json", report_data)
        return self._commit_gate(folder, state, "report", report_model, report_context, gate=gate)

    def _run_dashboard(self, folder: Path, state: dict) -> bool:
        self._begin(folder, state, "dashboard")
        observations = _read(folder / "data/observations.json", {"observations": []}).get("observations", [])
        usable = [x for x in observations if x.get("verification_status", "NOT_CHECKED") != "UNSUPPORTED"]
        scope = _read(folder / "00_analysis_scope.json", {})
        sources = _read(folder / "data/sources.json", _read(folder / "data/source_registry.json", {"sources": []})).get("sources", [])
        source_map = {row.get("source_id"): row for row in sources}
        report_data = _read(folder / "04_report_data.json", {})
        final_markdown = (folder / "04_final_report.md").read_text(encoding="utf-8") if (folder / "04_final_report.md").is_file() else ""
        if not hash_file_consistent(folder / "04_final_report.md", report_data):
            self._block(folder, state, "dashboard", [{"rule_id": "REPORT_HASH_MISMATCH", "reason": "04_final_report.md changed after report_data was frozen", "stage": "dashboard", "repair_type": "STAGE_RETRY"}], "BLOCKED_QUALITY")
            return False
        payload = {
            "schema_version": "2.0", "derived_from_markdown": False,
            "dashboard_status": "READY_WITH_GAPS" if report_data.get("validation_errors") else "READY",
            "meta": {"run_id": state["run_id"], "revision_id": state["revision_id"], "analysis_type": scope.get("analysis_type_id", "GENERIC_STRATEGY"), "topic": scope.get("topic", ""), "is_demo": bool(scope.get("is_test_fixture"))},
            "executive_summary": {},
            "metrics": [{**x, "metric_id": x.get("metric_id") or x.get("metric"), "label": x.get("label") or x.get("metric") or x.get("metric_id"), "source_fact_ids": list(x.get("source_fact_ids") or []), "source_observation_ids": [x.get("observation_id")] if x.get("observation_id") else []} for x in usable if x.get("value") is not None],
            "time_series": report_data.get("time_series", []), "comparisons": report_data.get("comparisons", []),
            "matrices": [], "segments": [], "geographies": [], "risks": [], "opportunities": [], "strategic_options": [],
            "recommendations": _read(folder / "strategy/recommendations.json", {"recommendations": []}).get("recommendations", []),
            "initiatives": [],
            "scenarios": report_data.get("scenarios", []), "content_blocks": report_data.get("content_blocks", []),
            "evidence": [{"observation_id": row.get("observation_id"), "source_id": row.get("source_id"), "source": source_map.get(row.get("source_id"), {}), "verification_status": row.get("verification_status"), "source_fact_ids": row.get("source_fact_ids", [])} for row in usable],
            "quality": _read(folder / "quality/summary.json", {}),
            "revision": {"revision_id": state["revision_id"], "revision_count": sum(path.name != "rev_000" for path in (folder / "revisions").glob("rev_*") if path.is_dir()) if (folder / "revisions").is_dir() else 0},
        }
        gate = validate_stage("dashboard", payload, {})
        if not gate.can_continue:
            self._block(folder, state, "dashboard", gate.errors, "BLOCKED_QUALITY")
            return False
        _write(folder / "dashboard/dashboard_data.json", payload)
        _write(folder / "06_dashboard_data.json", payload)
        return self._commit_gate(folder, state, "dashboard", payload, {}, gate=gate)

    def _run_quality(self, folder: Path, state: dict):
        self._begin(folder, state, "quality")
        issues = _read(folder / "quality/issues.json", {"issues": []}).get("issues", [])
        report_data = _read(folder / "04_report_data.json", {})
        final_path = folder / "04_final_report.md"
        if final_path.is_file() and not hash_file_consistent(final_path, report_data):
            issues.append({"rule_id": "REPORT_HASH_MISMATCH", "stage": "quality", "artifact": "04_report_data.json", "location": "/meta/final_report_sha256", "reason": "Final Markdown hash differs from frozen structured report", "severity": "ERROR", "repair_type": "LOCAL_REPAIRABLE"})
        for row in report_data.get("validation_errors", []):
            issues.append({**row, "stage": "quality", "artifact": "04_report_data.json", "severity": "ERROR", "repair_type": "STAGE_RETRY"})
        coverage = _read(folder / "data/data_coverage.json", _read(folder / "data/sufficiency.json", {}))
        observation_count = len(_read(folder / "data/observations.json", {"observations": []}).get("observations", []))
        if coverage.get("observation_count") is not None and int(coverage.get("observation_count")) != observation_count:
            issues.append({"rule_id": "DATA_COVERAGE_COUNT_MISMATCH", "stage": "quality", "artifact": "data/data_coverage.json", "location": "/observation_count", "reason": "Coverage count does not equal canonical Observation count", "severity": "ERROR", "repair_type": "STAGE_RETRY"})
        _write(folder / "quality/issues.json", {"schema_version": "2.0", "issues": issues})
        blocking = [x for x in issues if x.get("severity") == "ERROR" and not x.get("resolved")]
        aggregation = aggregate_quality(issues)
        summary = {"schema_version": "2.0", **aggregation, "status": "FAIL" if blocking else aggregation["status"]}
        _write(folder / "quality/summary.json", summary)
        current = state["stages"]["quality"]
        if blocking:
            current.update(status="BLOCKED", validation_status="BLOCKED", completed_at=now_iso(), error_codes=[row.get("rule_id") for row in blocking])
            state["overall_status"] = "BLOCKED_QUALITY"
            state["quality_summary"] = summary
            save_run_state(folder, state)
            return False
        current.update(status="COMPLETE_WITH_WARNINGS" if issues else "COMPLETE", validation_status="PASS", completed_at=now_iso())
        state["quality_summary"] = summary
        state["dependency_state"]["quality"] = "CURRENT"
        save_run_state(folder, state)
        return True

    def _finish_if_possible(self, folder: Path, state: dict, wanted: list[str]):
        if "quality" not in wanted or state["stages"]["quality"]["status"] not in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}:
            return
        state["overall_status"] = "COMPLETED_WITH_WARNINGS" if state["quality_summary"].get("warnings") else "COMPLETED"
        state["primary_action"] = "VIEW_RESULTS"
        state["current_stage"] = "quality"
        state.setdefault("events", []).append({"at": now_iso(), "stage": "quality", "event": "RUN_COMPLETED"})
        _write(folder / "run_manifest.json", {
            "schema_version": "2.0", "pipeline_version": "2.0", "run_id": state["run_id"],
            "revision_id": state["revision_id"], "topic": state["topic"], "final_status": state["overall_status"],
            "is_test_fixture": bool(_read(folder / "00_analysis_scope.json", {}).get("is_test_fixture")),
        })
        save_run_state(folder, state)

    def _commit_gate(self, folder, state, stage, payload, context, gate=None) -> bool:
        gate = gate or validate_stage(stage, payload, context)
        if not gate.can_continue:
            self._block(folder, state, stage, gate.errors, "BLOCKED_DATA" if stage == "data" else "BLOCKED_QUALITY")
            return False
        current = state["stages"][stage]
        current.update(status="COMPLETE_WITH_WARNINGS" if gate.warnings else "COMPLETE", validation_status=gate.status, completed_at=now_iso(), error_codes=[])
        state["dependency_state"][stage] = "CURRENT"
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "GATE_VALIDATED", "detail": gate.status})
        save_run_state(folder, state)
        return True

    def _block(self, folder: Path, state: dict, stage: str, errors: list[dict], overall: str):
        normalized = [self._normalize_issue(x, state["stages"][stage].get("attempt", 0)) for x in errors]
        current = state["stages"][stage]
        current.update(status="BLOCKED", validation_status="BLOCKED", error_codes=[x.get("rule_id") for x in normalized])
        state["overall_status"] = overall
        existing = _read(folder / "quality/issues.json", {"issues": []}).get("issues", [])
        _write(folder / "quality/issues.json", {"schema_version": "2.0", "issues": [x for x in existing if x.get("stage") != stage] + normalized})
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "STAGE_BLOCKED", "error_codes": current["error_codes"]})
        save_run_state(folder, state)

    @staticmethod
    def _normalize_issue(issue: dict, attempt: int) -> dict:
        payload = dict(issue)
        payload.setdefault("error_id", f"{payload.get('stage')}:{attempt}:{payload.get('rule_id')}")
        payload.setdefault("attempt", attempt)
        payload.setdefault("json_pointer", payload.get("location", "/"))
        payload.setdefault("allowed_actions", ["RETRY_STAGE", "REQUEST_HUMAN_REVIEW"])
        payload.setdefault("repair_strategy", payload.get("repair_type", "STAGE_RETRY"))
        return payload

    @staticmethod
    def _expected(stage):
        from .envelope import EXPECTED_ARTIFACTS
        return list(EXPECTED_ARTIFACTS.get(stage, ()))

    @staticmethod
    def _contract_description(stage):
        from .contracts import REGISTRY
        contract = REGISTRY[stage]
        return {"stage": stage, "required_inputs": list(contract.required_inputs), "postconditions": list(contract.postconditions), "repair_strategy": contract.repair_strategy}

    @staticmethod
    def _stage_inputs(folder: Path, stage: str) -> dict:
        paths = {
            "data": ["00_analysis_scope.json"],
            "research": ["data/requirements.json", "data/source_registry.json", "data/observations.json", "data/sufficiency.json"],
            "review": ["research/claims.json", "research/research_model.json"],
            "fact_check": ["research/claims.json", "02_review_notes.json", "data/sources.json", "data/observations.json"],
            "strategy": ["fact_check/verified_claims.json", "human/feedback.json", "data/observations.json", "02_review_notes.json"],
        }.get(stage, [])
        return {path: _read(folder / path, {}) for path in paths}

    @staticmethod
    def _gate_payload(folder: Path, stage: str, artifacts: dict):
        if stage == "data":
            observations = artifacts["observations"]
            sources = artifacts["source_registry"]
            return observations, {"sources": sources.get("sources", []), "sufficiency": artifacts["sufficiency"]}
        if stage == "research":
            obs = _read(folder / "data/observations.json", {"observations": []}).get("observations", [])
            src = _read(folder / "data/source_registry.json", {"sources": []}).get("sources", [])
            return {"claims": artifacts["claims"]}, {"observations": obs, "sources": src}
        if stage == "review":
            return {"issues": artifacts["review_notes"]}, {}
        if stage == "fact_check":
            src = _read(folder / "data/sources.json", _read(folder / "data/source_registry.json", {"sources": []})).get("sources", [])
            obs = _read(folder / "data/observations.json", {"observations": []}).get("observations", [])
            return {"claims": artifacts["verified_claims"]}, {"sources": src, "observations": obs}
        if stage == "strategy":
            claims = _read(folder / "fact_check/verified_claims.json", {"claims": []}).get("claims", [])
            review_ids = [row.get("review_id") for row in _read(folder / "02_review_notes.json", {"issues": []}).get("issues", [])]
            return {"recommendations": artifacts["recommendations"]}, {"claims": claims, "review_ids": review_ids}
        return artifacts, {}

    @staticmethod
    def _persist_artifacts(folder: Path, stage: str, artifacts: dict):
        paths = {
            "data": {
                "requirements": "data/requirements.json", "source_registry": "data/source_registry.json",
                "observations": "data/observations.json", "sufficiency": "data/sufficiency.json",
            },
            "research": {"claims": "research/claims.json", "research_sections": "research/research_model.json"},
            "review": {"review_notes": "review/review_notes.json"},
            "fact_check": {"verified_claims": "fact_check/verified_claims.json"},
            "strategy": {"recommendations": "strategy/recommendations.json", "report_model": "strategy/report_model.json"},
        }[stage]
        for name, relative in paths.items():
            value = artifacts[name]
            if name in {"claims", "verified_claims", "recommendations", "review_notes"}:
                key = {"review_notes": "issues", "verified_claims": "claims"}.get(name, name)
                value = {"schema_version": "2.0", key: value}
            elif name == "research_sections":
                value = {"schema_version": "2.0", "sections": value}
            _write(folder / relative, value)
            if name == "review_notes":
                _write(folder / "02_review_notes.json", value)
                _write(folder / "review/review_issues.json", value)
            elif name == "source_registry":
                _write(folder / "data/sources.json", value)
            elif name == "sufficiency":
                _write(folder / "data/data_coverage.json", value)
            elif name == "verified_claims":
                claims = value.get("claims", [])
                observation_verifications = []
                for claim in claims:
                    for observation_id in claim.get("observation_ids", []):
                        observation_verifications.append({
                            "observation_id": observation_id,
                            "claim_id": claim.get("claim_id"),
                            "verification_status": claim.get("verification_status", "NOT_CHECKED"),
                            "temporal_status": claim.get("temporal_status", "UNKNOWN"),
                            "source_ids": list(claim.get("source_ids") or []),
                        })
                _write(folder / "03_fact_check.json", {"schema_version": "2.0", "claims": claims, "observation_verifications": observation_verifications})
