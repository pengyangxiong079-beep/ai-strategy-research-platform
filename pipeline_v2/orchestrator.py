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
from .report_protocol import attach_fact_verification, dashboard_report_data, hash_file_consistent, report_data_payload, render_content_blocks, sha256_file, validate_report_data
from .quality import aggregate_quality
from .review import normalize_review_notes
from .service import PipelineV2Service
from .agent_provider import describe_agent_error
from .fact_check import normalize_fact_check
from .report_model import normalize_report_model


AGENT_STAGES = ("data", "research", "review", "fact_check", "strategy")
TRANSIENT_AGENT_ERRORS = (
    "stream disconnected", "error sending request", "timed out", "timeout",
    "connection reset", "connection aborted", "temporarily unavailable",
)


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

    @staticmethod
    def _save(folder: Path, state: dict):
        saved = save_run_state(folder, state)
        PipelineV2Service(folder.parent).sync_manifest_from_state(folder, saved)
        return saved

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
        strategy_runs_before_fact_check = (
            "strategy" in wanted
            and ("fact_check" not in wanted or wanted.index("strategy") < wanted.index("fact_check"))
        )
        if strategy_runs_before_fact_check and state.get("stages", {}).get("fact_check", {}).get("status") not in {
            "COMPLETE", "COMPLETE_WITH_WARNINGS",
        }:
            raise RuntimeError("Fact Check must pass before Strategy can start")
        strategy_runs_before_human = (
            "strategy" in wanted
            and ("human" not in wanted or wanted.index("strategy") < wanted.index("human"))
        )
        if strategy_runs_before_human and state.get("stages", {}).get("human", {}).get("status") not in {
            "COMPLETE", "COMPLETE_WITH_WARNINGS",
        }:
            raise RuntimeError("Human Review must be completed before Strategy can start")
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

    def revalidate_fact_check_artifact(self, folder, artifact) -> dict:
        """Promote a saved Fact Check candidate using current local contracts.

        This performs no Agent call.  It is intentionally used only inside a
        new revision so the blocked run and its audit evidence stay immutable.
        """
        folder = Path(folder)
        state = load_run_state(folder)
        if not state or state.get("pipeline_version") != "2.0":
            raise ValueError("Fact Check local revalidation requires a Pipeline V2 run")
        artifacts = {"verified_claims": artifact}
        payload, context = self._gate_payload(folder, "fact_check", artifacts)
        gate = validate_stage("fact_check", payload, context)
        if not gate.can_continue:
            codes = ", ".join(row.get("rule_id", "UNKNOWN") for row in gate.errors)
            raise ValueError(f"Saved Fact Check candidate still fails current contracts: {codes}")
        self._persist_artifacts(folder, "fact_check", artifacts)
        issues_path = folder / "quality/issues.json"
        issues = _read(issues_path, {"issues": []}).get("issues", [])
        _write(issues_path, {
            "schema_version": "2.0",
            "issues": [row for row in issues if row.get("stage") != "fact_check"],
        })
        state.setdefault("events", []).append({
            "at": now_iso(), "stage": "fact_check",
            "event": "FACT_CHECK_CONTRACT_REVALIDATED_LOCALLY",
            "detail": "Saved candidate normalized and validated without an Agent call",
        })
        self._commit_gate(folder, state, "fact_check", payload, context, gate=gate)
        return load_run_state(folder)

    def revalidate_data_artifacts(self, folder, artifacts) -> dict:
        """Promote a locally syntax-recovered Data candidate without web calls."""
        folder = Path(folder)
        state = load_run_state(folder)
        if not state or state.get("pipeline_version") != "2.0":
            raise ValueError("Data local revalidation requires a Pipeline V2 run")
        candidate = json.loads(json.dumps(artifacts, ensure_ascii=False))
        self._merge_targeted_gap_artifacts(folder, candidate)
        self._normalize_data_artifacts(folder, candidate)
        payload, context = self._gate_payload(folder, "data", candidate)
        gate = validate_stage("data", payload, context)
        if not gate.can_continue:
            codes = ", ".join(row.get("rule_id", "UNKNOWN") for row in gate.errors)
            raise ValueError(f"Saved Data candidate still fails current contracts: {codes}")
        self._finalize_targeted_gap_search(folder, candidate)
        self._persist_artifacts(folder, "data", candidate)
        state.setdefault("events", []).append({
            "at": now_iso(), "stage": "data",
            "event": "DATA_CANDIDATE_REVALIDATED_LOCALLY",
            "detail": "A losslessly syntax-recovered candidate was normalized and validated without another Data Agent call",
        })
        self._commit_gate(folder, state, "data", payload, context, gate=gate)
        return load_run_state(folder)

    def revalidate_strategy_artifacts(self, folder, artifacts) -> dict:
        """Promote an already-generated Strategy candidate after local shape normalization."""
        folder = Path(folder)
        state = load_run_state(folder)
        if not state or state.get("pipeline_version") != "2.0":
            raise ValueError("Strategy local revalidation requires a Pipeline V2 run")
        if not isinstance(artifacts, dict):
            raise ValueError("Saved Strategy candidate has no artifact object")
        candidate = {
            "recommendations": artifacts.get("recommendations"),
            "report_model": artifacts.get("report_model"),
        }
        if not isinstance(candidate["recommendations"], list) or not isinstance(candidate["report_model"], dict):
            raise ValueError("Saved Strategy candidate is not recoverable under the current contract")
        payload, context = self._gate_payload(folder, "strategy", candidate)
        gate = validate_stage("strategy", payload, context)
        if not gate.can_continue:
            codes = ", ".join(row.get("rule_id", "UNKNOWN") for row in gate.errors)
            raise ValueError(f"Saved Strategy candidate still fails current contracts: {codes}")
        self._persist_artifacts(folder, "strategy", candidate)
        issues = _read(folder / "quality/issues.json", {"issues": []}).get("issues", [])
        _write(folder / "quality/issues.json", {
            "schema_version": "2.0",
            "issues": [row for row in issues if row.get("stage") != "strategy"],
        })
        state.setdefault("events", []).append({
            "at": now_iso(), "stage": "strategy",
            "event": "STRATEGY_CONTRACT_REVALIDATED_LOCALLY",
            "detail": "Saved candidate shape normalized and validated without an Agent call",
        })
        self._commit_gate(folder, state, "strategy", payload, context, gate=gate)
        return load_run_state(folder)

    def normalize_saved_report_model(self, folder) -> dict:
        """Normalize and persist an already-generated report model locally."""
        folder = Path(folder)
        path = folder / "strategy/report_model.json"
        original = _read(path, {})
        normalized = normalize_report_model(original)
        if normalized != original:
            _write(path, normalized)
            state = load_run_state(folder)
            state.setdefault("events", []).append({
                "at": now_iso(), "stage": "report",
                "event": "REPORT_MODEL_NORMALIZED_LOCALLY",
                "detail": "Workflow provenance relabeled without changing research facts",
            })
            issues = _read(folder / "quality/issues.json", {"issues": []}).get("issues", [])
            _write(folder / "quality/issues.json", {
                "schema_version": "2.0",
                "issues": [row for row in issues if row.get("stage") != "report"],
            })
            self._save(folder, state)
        return normalized

    def _begin(self, folder: Path, state: dict, stage: str, attempt: int | None = None):
        current = state["stages"][stage]
        current["status"] = "RUNNING"
        current["started_at"] = current.get("started_at") or now_iso()
        if attempt is not None:
            current["attempt"] = attempt
        state["current_stage"] = stage
        state["overall_status"] = "RUNNING" if state.get("revision_id") == "rev_000" else "REVISION_IN_PROGRESS"
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "STAGE_STARTED", "attempt": attempt})
        self._save(folder, state)

    def _run_scope(self, folder: Path, state: dict) -> bool:
        self._begin(folder, state, "scope")
        payload = _read(folder / "00_analysis_scope.json", {})
        return self._commit_gate(folder, state, "scope", payload, {})

    def _request(self, folder: Path, state: dict, stage: str, attempt: int,
                 previous_output=None, errors=None, previous_invalid_output=None) -> dict:
        request = {
            "pipeline_version": "2.0", "strict_structured_output": True,
            "run_id": state["run_id"], "revision_id": state["revision_id"],
            "stage": stage, "attempt": attempt,
            "inputs": self._stage_inputs(folder, stage),
            "previous_structured_output": previous_output,
            "previous_invalid_output": previous_invalid_output,
            "error_packet": errors or [],
            "stage_contract": self._contract_description(stage),
            "output_schema": {
                "envelope": "2.0", "required_artifacts": self._expected(stage),
                "artifact_contract": self._artifact_contract(stage),
            },
            "remaining_attempts": max(0, self.max_attempts - attempt),
        }
        if stage == "data" and errors and {
            row.get("repair_type") for row in errors
        } == {"UPSTREAM_DATA_REQUIRED"}:
            request["repair_context"] = self._bounded_gap_context(folder, previous_output, errors)
        if stage == "data":
            targeted = _read(folder / "data/targeted_gap_search.json", {})
            if targeted.get("status") in {"REQUESTED", "RUNNING"}:
                request["repair_context"] = targeted.get("repair_context") or {}
                for relative in (
                    "data/requirements.json", "data/source_registry.json",
                    "data/observations.json", "data/sufficiency.json",
                ):
                    request["inputs"][relative] = _read(folder / relative, {})
                if targeted.get("status") == "REQUESTED":
                    targeted.update({
                        "status": "RUNNING", "started_at": now_iso(),
                        "attempt_count": int(targeted.get("attempt_count") or 0) + 1,
                    })
                    _write(folder / "data/targeted_gap_search.json", targeted)
        return request

    def _run_agent_stage(self, folder: Path, state: dict, stage: str) -> bool:
        previous = None
        previous_invalid = None
        last_errors = []
        start_attempt = max(1, int(state["stages"][stage].get("attempt", 0)) + 1)
        attempt_limit = self.max_attempts
        gap_search_started = any(
            row.get("stage") == stage and row.get("event") == "BOUNDED_GAP_SEARCH_STARTED"
            for row in state.get("events", [])
        )
        attempt = start_attempt
        while attempt <= attempt_limit:
            self._begin(folder, state, stage, attempt)
            request = self._request(
                folder, state, stage, attempt, previous, last_errors, previous_invalid
            )
            calls = state.setdefault("agent_calls", {"total": 0, "by_stage": {}})
            calls["total"] = int(calls.get("total", 0)) + 1
            calls.setdefault("by_stage", {})[stage] = int(calls["by_stage"].get(stage, 0)) + 1
            self._save(folder, state)
            raw = None
            try:
                raw = self.registry.get(stage).run(request)
                envelope = parse_envelope(
                    raw, stage=stage, attempt=attempt, run_id=state["run_id"],
                    revision_id=state["revision_id"],
                )
                previous = envelope
                previous_invalid = None
                candidate_folder = folder / "quality/candidates"
                candidate_folder.mkdir(parents=True, exist_ok=True)
                if stage == "data":
                    # Preserve the exact Agent response, then promote only the
                    # deterministic, normalized data candidate to the gate.
                    _write(candidate_folder / f"{stage}_attempt_{attempt}_agent.json", envelope)
                    self._merge_targeted_gap_artifacts(folder, envelope["artifacts"])
                    self._normalize_data_artifacts(folder, envelope["artifacts"])
                _write(candidate_folder / f"{stage}_attempt_{attempt}.json", envelope)
                payload, context = self._gate_payload(folder, stage, envelope["artifacts"])
                gate = validate_stage(stage, payload, context)
                if gate.can_continue:
                    if stage == "data":
                        self._finalize_targeted_gap_search(folder, envelope["artifacts"])
                    self._persist_artifacts(folder, stage, envelope["artifacts"])
                    if stage == "fact_check":
                        resolved = self._reconcile_review_after_fact_check(
                            folder, envelope["artifacts"]["verified_claims"],
                        )
                        if resolved:
                            state.setdefault("events", []).append({
                                "at": now_iso(), "stage": "fact_check",
                                "event": "REVIEW_VERIFICATION_ITEMS_AUTO_RESOLVED",
                                "resolved_count": resolved,
                            })
                    return self._commit_gate(folder, state, stage, payload, context, gate=gate)
                last_errors = [self._normalize_issue(x, attempt) for x in gate.errors]
            except AgentOutputError as error:
                last_errors = [error.to_issue()]
                previous_invalid = raw if isinstance(raw, (str, dict)) else repr(raw)
                candidate_folder = folder / "quality/candidates"
                candidate_folder.mkdir(parents=True, exist_ok=True)
                _write(candidate_folder / f"{stage}_attempt_{attempt}_invalid.json", {
                    "schema_version": "2.0", "stage": stage, "attempt": attempt,
                    "parse_error": last_errors[0], "raw_response": previous_invalid,
                })
                if isinstance(raw, dict):
                    previous = raw
                elif isinstance(raw, str):
                    try:
                        recovered = json.loads(raw)
                        previous = recovered if isinstance(recovered, dict) else None
                    except (TypeError, ValueError):
                        previous = None
            except Exception as error:  # technical failures stay distinct
                error_detail = describe_agent_error(error)
                transient = isinstance(error, (ConnectionError, TimeoutError)) or any(
                    token in str(error).lower() for token in TRANSIENT_AGENT_ERRORS
                )
                if transient and attempt < self.max_attempts:
                    state.setdefault("events", []).append({
                        "at": now_iso(), "stage": stage, "event": "AGENT_TECHNICAL_RETRY",
                        "detail": error_detail[:500], "attempt": attempt,
                    })
                    self._save(folder, state)
                    attempt += 1
                    continue
                state["stages"][stage]["status"] = "FAILED_TECHNICAL"
                state["overall_status"] = "FAILED_TECHNICAL"
                state["stages"][stage]["error_codes"] = ["AGENT_TECHNICAL_FAILURE"]
                state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "FAILED_TECHNICAL", "detail": error_detail[:500], "attempt": attempt})
                self._save(folder, state)
                return False

            repair_types = {x.get("repair_type") for x in last_errors}
            state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "GATE_RETRY_REQUIRED", "attempt": attempt, "error_codes": [x.get("rule_id") for x in last_errors]})
            if repair_types == {"UPSTREAM_DATA_REQUIRED"} and stage == "data" and not gap_search_started:
                gap_search_started = True
                if attempt >= attempt_limit:
                    attempt_limit = attempt + 1
                gap_context = self._bounded_gap_context(folder, previous, last_errors)
                _write(folder / "quality/upstream_action.json", {
                    "schema_version": "2.0", "stage": stage, "status": "SEARCHING",
                    "recommended_action": "BOUNDED_GAP_SEARCH",
                    "attempt": attempt, "remaining_attempts": attempt_limit - attempt,
                    "target_dataset_ids": gap_context["target_dataset_ids"],
                    "repair_context": gap_context,
                    "errors": last_errors,
                })
                state.setdefault("events", []).append({
                    "at": now_iso(), "stage": stage, "event": "BOUNDED_GAP_SEARCH_STARTED",
                    "attempt": attempt, "target_dataset_ids": gap_context["target_dataset_ids"],
                })
                self._save(folder, state)
                attempt += 1
                continue
            if repair_types != {"STAGE_RETRY"}:
                if "HUMAN_REQUIRED" in repair_types:
                    self._request_human(folder, state, stage, last_errors)
                else:
                    if "UPSTREAM_DATA_REQUIRED" in repair_types:
                        _write(folder / "quality/upstream_action.json", {
                            "schema_version": "2.0", "stage": stage, "status": "BLOCKED",
                            "recommended_action": "GAP_SEARCH" if stage == "data" else "CREATE_REVISION_PLAN",
                            "errors": last_errors,
                        })
                    self._block(folder, state, stage, last_errors, "BLOCKED_DATA" if "UPSTREAM_DATA_REQUIRED" in repair_types and stage == "data" else "BLOCKED_QUALITY")
                return False
            if attempt >= self.max_attempts:
                self._block(folder, state, stage, last_errors, "BLOCKED_QUALITY")
                return False
            self._save(folder, state)
            attempt += 1
        return False

    @staticmethod
    def _merge_targeted_gap_artifacts(folder: Path, artifacts: dict):
        """Preserve prior evidence and recompute coverage for a targeted search."""
        marker = _read(folder / "data/targeted_gap_search.json", {})
        if marker.get("status") not in {"REQUESTED", "RUNNING"}:
            return
        from research_platform.sufficiency import evaluate_sufficiency

        existing_requirements = _read(folder / "data/requirements.json", {"datasets": []})
        existing_sources = _read(folder / "data/source_registry.json", {"sources": []})
        existing_observations = _read(folder / "data/observations.json", {"observations": []})

        def merge_rows(previous, incoming, identity):
            merged = {}
            order = []
            for row in [*(previous or []), *(incoming or [])]:
                if not isinstance(row, dict):
                    continue
                key = identity(row)
                if not key:
                    continue
                if key not in merged:
                    order.append(key)
                merged[key] = {**merged.get(key, {}), **row}
            return [merged[key] for key in order]

        incoming_sources = (artifacts.get("source_registry") or {}).get("sources", [])
        incoming_observations = (artifacts.get("observations") or {}).get("observations", [])
        sources = merge_rows(
            existing_sources.get("sources", []), incoming_sources,
            lambda row: row.get("source_id") or row.get("url"),
        )
        observations = merge_rows(
            existing_observations.get("observations", []), incoming_observations,
            lambda row: row.get("observation_id"),
        )
        requirements = existing_requirements if existing_requirements.get("datasets") else artifacts.get("requirements", {})
        scope = _read(folder / "00_analysis_scope.json", {})
        previous_rounds = int(marker.get("previous_rounds") or 0)
        sufficiency = evaluate_sufficiency(
            requirements, observations, sources, scope,
            gap_rounds_completed=previous_rounds + 1,
            stop_reason="Targeted gap search completed; unresolved items remain explicit.",
        )
        artifacts["requirements"] = requirements
        artifacts["source_registry"] = {"schema_version": "1.0", "sources": sources}
        artifacts["observations"] = {"schema_version": "1.0", "observations": observations}
        artifacts["sufficiency"] = sufficiency

    @staticmethod
    def _normalize_data_artifacts(folder: Path, artifacts: dict):
        """Make canonical Data artifacts deterministic in every live run.

        The Data Agent performs web research, but it cannot weaken the planned
        requirement contract or declare its own unverified PASS. Fake fixtures
        intentionally retain their compact synthetic contract.
        """
        scope = _read(folder / "00_analysis_scope.json", {})
        incoming_sources = list((artifacts.get("source_registry") or {}).get("sources") or [])
        incoming_observations = list((artifacts.get("observations") or {}).get("observations") or [])
        synthetic_fixture = bool(incoming_sources and incoming_observations) and all(
            isinstance(row, dict) and row.get("is_test_fixture")
            for row in [*incoming_sources, *incoming_observations]
        )
        if scope.get("is_test_fixture") or synthetic_fixture:
            return

        from research_platform.data_requirements import build_requirements
        from research_platform.normalization import (
            canonicalize_entity, dedupe_observations, dedupe_sources,
            is_valid_observation, normalize_source,
        )
        from research_platform.search import comparison_cohort
        from research_platform.sufficiency import evaluate_sufficiency

        requirements = build_requirements(scope)
        raw_sources = incoming_sources
        normalized_all = [normalize_source(row) for row in raw_sources if isinstance(row, dict)]
        sources = dedupe_sources(normalized_all)
        canonical_by_identity = {
            (row.get("url") or row.get("source_id")): row.get("source_id") for row in sources
        }
        source_aliases = {
            row.get("source_id"): canonical_by_identity.get(row.get("url") or row.get("source_id"), row.get("source_id"))
            for row in normalized_all if row.get("source_id")
        }
        source_ids = {row.get("source_id") for row in sources if row.get("source_id")}
        known_entities = comparison_cohort(scope, len(scope.get("competitors") or []) + 1)
        raw_observations = []
        for raw in (artifacts.get("observations") or {}).get("observations") or []:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            row["source_id"] = source_aliases.get(row.get("source_id"), row.get("source_id"))
            row["entity"] = canonicalize_entity(row.get("entity"), known_entities)
            raw_observations.append(row)
        observations = dedupe_observations(raw_observations, sources, scope.get("industry"))
        observations = [
            row for row in observations if is_valid_observation(row, source_ids)[0]
        ]
        declared = artifacts.get("sufficiency") if isinstance(artifacts.get("sufficiency"), dict) else {}
        rounds = int(declared.get("gap_search_rounds_completed") or 0)
        stop_reason = str(declared.get("search_stop_reason") or "Deterministic coverage recomputed from canonical evidence.")
        sufficiency = evaluate_sufficiency(
            requirements, observations, sources, scope,
            gap_rounds_completed=rounds, stop_reason=stop_reason,
        )
        artifacts["requirements"] = requirements
        artifacts["source_registry"] = {"schema_version": "1.0", "sources": sources}
        artifacts["observations"] = {"schema_version": "1.0", "observations": observations}
        artifacts["sufficiency"] = sufficiency

    @staticmethod
    def _finalize_targeted_gap_search(folder: Path, artifacts: dict):
        path = folder / "data/targeted_gap_search.json"
        marker = _read(path, {})
        if marker.get("status") not in {"REQUESTED", "RUNNING"}:
            return
        sufficiency = artifacts.get("sufficiency")
        if not isinstance(sufficiency, dict):
            return
        previous_rounds = int(marker.get("previous_rounds") or 0)
        sufficiency["gap_search_rounds_completed"] = max(
            int(sufficiency.get("gap_search_rounds_completed") or 0), previous_rounds + 1,
        )
        targets = list(marker.get("target_dataset_ids") or [])
        status_by_dataset = {
            row.get("dataset_id"): row.get("status")
            for row in sufficiency.get("datasets", []) if isinstance(row, dict)
        }
        resolved = [dataset_id for dataset_id in targets if status_by_dataset.get(dataset_id) == "PASS"]
        remaining = [dataset_id for dataset_id in targets if dataset_id not in resolved]
        sufficiency["search_stop_reason"] = (
            "Targeted gap search closed all selected datasets."
            if not remaining else
            "Targeted gap search completed; selected datasets without sufficient verifiable evidence remain explicit."
        )
        marker.update({
            "status": "COMPLETED", "completed_at": now_iso(),
            "resolved_dataset_ids": resolved,
            "remaining_dataset_ids": remaining,
            "attempt_count": int(marker.get("attempt_count") or 0),
        })
        _write(path, marker)

    @staticmethod
    def _reconcile_review_after_fact_check(folder: Path, verified_payload: dict) -> int:
        """Close Review items made obsolete by the subsequent Fact Check."""
        import re

        if not isinstance(verified_payload, dict):
            return 0
        ledger = {
            row.get("observation_id"): str(row.get("verification_status") or "NOT_CHECKED").upper()
            for row in verified_payload.get("observation_verifications", [])
            if isinstance(row, dict) and row.get("observation_id")
        }
        path = folder / "02_review_notes.json"
        payload = _read(path, _read(folder / "review/review_notes.json", {"issues": []}))
        issues = list(payload.get("issues") or [])
        resolved = 0
        for issue in issues:
            if str(issue.get("status") or "OPEN").upper() != "OPEN":
                continue
            if "verification" not in str(issue.get("category") or "").lower():
                continue
            text = " ".join(str(issue.get(key) or "") for key in ("issue", "evidence", "required_action"))
            observation_ids = list(dict.fromkeys(re.findall(r"(?<![A-Za-z0-9_])O\d+(?!\d)", text)))
            if observation_ids and all(ledger.get(value) in {"SUPPORTED", "PARTIAL"} for value in observation_ids):
                issue["status"] = "RESOLVED"
                issue["resolution"] = "Fact Check subsequently verified the referenced Observation(s)."
                resolved += 1
        if resolved:
            normalized = {"schema_version": "2.0", "issues": issues}
            _write(path, normalized)
            _write(folder / "review/review_notes.json", normalized)
            _write(folder / "review/review_issues.json", normalized)
        return resolved

    @staticmethod
    def _bounded_gap_context(folder: Path, previous_output: dict | None, errors: list[dict]) -> dict:
        scope = _read(folder / "00_analysis_scope.json", {})
        artifacts = previous_output.get("artifacts", {}) if isinstance(previous_output, dict) else {}
        requirements = artifacts.get("requirements", {}) if isinstance(artifacts, dict) else {}
        requirement_map = {
            row.get("dataset_id"): row
            for row in requirements.get("datasets", [])
            if isinstance(row, dict) and row.get("dataset_id")
        }
        targets = []
        for issue in errors:
            dataset_id = issue.get("entity_id") or str(issue.get("location", "")).rsplit("/", 1)[-1]
            actual = issue.get("actual") if isinstance(issue.get("actual"), dict) else {}
            gaps = actual.get("gaps") if isinstance(actual.get("gaps"), list) else []
            normalized_gaps = []
            for gap in gaps or [{}]:
                gap = gap if isinstance(gap, dict) else {}
                entity = str(gap.get("entity") or scope.get("company") or scope.get("topic") or "").strip()
                missing = str(gap.get("missing_field") or "dataset").strip()
                queries = []
                for raw_query in gap.get("recommended_queries", []):
                    query = (
                        raw_query.get("query_text") or raw_query.get("query") or ""
                        if isinstance(raw_query, dict) else str(raw_query)
                    )
                    query = str(query).strip()
                    if query and query not in queries:
                        queries.append(query)
                if not queries:
                    query_subject = " ".join(x for x in (entity, dataset_id, missing) if x)
                    queries = [f"{query_subject} official filing investor relations {scope.get('analysis_date', '')}".strip()]
                normalized_gaps.append({
                    "gap_id": gap.get("gap_id"), "entity": entity,
                    "missing_field": missing,
                    "needed_observations": max(1, int(gap.get("needed_observations") or 1)),
                    "recommended_queries": queries,
                })
            targets.append({
                "dataset_id": dataset_id, "requirement": requirement_map.get(dataset_id, {}),
                "gaps": normalized_gaps,
            })
        target_ids = list(dict.fromkeys(row["dataset_id"] for row in targets if row["dataset_id"]))
        return {
            "mode": "BOUNDED_CRITICAL_GAP_SEARCH",
            "target_dataset_ids": target_ids,
            "targets": targets,
            "source_priority": ["official disclosures", "regulatory filings", "investor relations", "primary documentation"],
            "completion_rule": "Search only the listed targets; preserve valid prior evidence; recompute sufficiency; keep unresolved gaps explicit.",
        }

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
        self._save(folder, state)

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
        self._save(folder, state)

    def _run_report(self, folder: Path, state: dict) -> bool:
        self._begin(folder, state, "report")
        report_model = _read(folder / "strategy/report_model.json", {})
        verified_payload = _read(folder / "fact_check/verified_claims.json", {"claims": [], "observation_verifications": []})
        claims = verified_payload.get("claims", [])
        observation_verifications = verified_payload.get("observation_verifications", [])
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
        observations = _read(folder / "data/observations.json", {"observations": []}).get("observations", [])
        sufficiency = _read(folder / "data/sufficiency.json", {"datasets": []})
        recs = _read(folder / "strategy/recommendations.json", {"recommendations": []}).get("recommendations", [])
        rendered = folder / "rendered"
        rendered.mkdir(parents=True, exist_ok=True)
        research = _read(folder / "research/research_model.json", {"sections": []}).get("sections", [])
        research_claims = _read(folder / "research/claims.json", {"claims": []}).get("claims", [])
        review = _read(folder / "02_review_notes.json", _read(folder / "review/review_notes.json", {"issues": []})).get("issues", [])
        (rendered / "01_research_brief.md").write_text(render_research(research, research_claims), encoding="utf-8")
        (rendered / "02_review_notes.md").write_text(render_review(review), encoding="utf-8")
        (rendered / "03_fact_check.md").write_text(render_fact_check(claims, sources), encoding="utf-8")
        blocks = report_data_payload(
            report_model, claims, recs, "", run_id=state["run_id"], revision_id=state["revision_id"],
            observations=observations, sufficiency=sufficiency,
            observation_verifications=observation_verifications,
        )["content_blocks"]
        markdown = render_content_blocks(report_model.get("title", "战略研究报告"), blocks)
        (rendered / "04_final_report.md").write_text(markdown, encoding="utf-8")
        (folder / "04_final_report.md").write_text(markdown, encoding="utf-8")
        report_data = report_data_payload(
            report_model, claims, recs, markdown, run_id=state["run_id"], revision_id=state["revision_id"],
            observations=observations, sufficiency=sufficiency,
            observation_verifications=observation_verifications,
        )
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
        verified_payload = _read(folder / "fact_check/verified_claims.json", {"claims": [], "observation_verifications": []})
        claims = verified_payload.get("claims", [])
        dashboard_observations = attach_fact_verification(
            observations, claims, verified_payload.get("observation_verifications", []),
        )
        scope = _read(folder / "00_analysis_scope.json", {})
        sources = _read(folder / "data/sources.json", _read(folder / "data/source_registry.json", {"sources": []})).get("sources", [])
        source_map = {row.get("source_id"): row for row in sources}
        report_data = _read(folder / "04_report_data.json", {})
        final_markdown = (folder / "04_final_report.md").read_text(encoding="utf-8") if (folder / "04_final_report.md").is_file() else ""
        if not hash_file_consistent(folder / "04_final_report.md", report_data):
            self._block(folder, state, "dashboard", [{"rule_id": "REPORT_HASH_MISMATCH", "reason": "04_final_report.md changed after report_data was frozen", "stage": "dashboard", "repair_type": "STAGE_RETRY"}], "BLOCKED_QUALITY")
            return False
        dashboard_report = dashboard_report_data(scope, report_data, claims)
        quality = _read(folder / "quality/summary.json", {})
        quality_status = str(quality.get("status") or "UNKNOWN").upper()
        if quality_status not in {"PASS", "WARN", "FAIL", "UNKNOWN"}:
            quality_status = "WARN" if "WARN" in quality_status else "UNKNOWN"
        recommendations = dashboard_report["recommendations"]
        availability = dict(report_data.get("visual_availability", {}))
        if "roadmap" in availability:
            availability.setdefault("initiatives", availability["roadmap"])
        has_visual_gaps = bool(report_data.get("validation_errors") or report_data.get("data_gaps")) or any(
            row.get("status") != "AVAILABLE" for row in availability.values() if isinstance(row, dict)
        )
        payload = {
            "schema_version": "2.0", "derived_from_markdown": False,
            "dashboard_status": "READY_WITH_GAPS" if has_visual_gaps else "READY",
            "quality_status": quality_status,
            "meta": {"run_id": state["run_id"], "revision_id": state["revision_id"], "analysis_type": scope.get("analysis_type_id", "GENERIC_STRATEGY"), "topic": scope.get("topic", ""), "is_demo": bool(scope.get("is_test_fixture"))},
            "executive_summary": {
                "conclusion": next((row.get("text") for row in report_data.get("content_blocks", []) if row.get("claim_type") in {"RECOMMENDATION", "INFERENCE"} and row.get("text")), ""),
                "primary_recommendation_id": (report_data.get("recommendations") or [{}])[0].get("recommendation_id"),
            },
            "metrics": report_data.get("metrics", []),
            "time_series": report_data.get("time_series", []), "comparisons": report_data.get("comparisons", []),
            "matrices": report_data.get("matrices", []), "segments": report_data.get("segments", []),
            "geographies": report_data.get("geographies", []),
            "risks": report_data.get("risks", []), "opportunities": report_data.get("opportunities", []), "strategic_options": [],
            "recommendations": recommendations,
            "initiatives": report_data.get("roadmap", []),
            "scenarios": report_data.get("scenarios", []), "content_blocks": report_data.get("content_blocks", []),
            "observations": dashboard_observations,
            "data_coverage": _read(folder / "data/data_coverage.json", _read(folder / "data/sufficiency.json", {})),
            "data_gaps": report_data.get("data_gaps", []),
            "evidence": [{"observation_id": row.get("observation_id"), "source_id": row.get("source_id"), "source": source_map.get(row.get("source_id"), {}), "verification_status": row.get("verification_status"), "source_fact_ids": row.get("source_fact_ids", [])} for row in dashboard_observations],
            "quality": {"overall_status": quality_status, "quality_issues": quality.get("raw_issues", []), "excluded_fields": []},
            "revision": {"revision_id": state["revision_id"], "revision_count": sum(path.name != "rev_000" for path in (folder / "revisions").glob("rev_*") if path.is_dir()) if (folder / "revisions").is_dir() else 0},
            # Stable offline-dashboard compatibility envelope. Canonical V2
            # fields above remain the source; this view avoids Markdown parsing.
            "scope": dashboard_report["scope"],
            "report_version": state["revision_id"],
            "template_id": scope.get("analysis_type_id", "GENERIC_STRATEGY"),
            "industry_template_id": scope.get("selected_template") or "general",
            "component_availability": availability,
            "components": [
                {
                    "component_id": key,
                    "status": "READY" if value.get("status") == "AVAILABLE" else "INSUFFICIENT_DATA",
                    "reason": "" if value.get("status") == "AVAILABLE" else value.get("reason") or "",
                    "required_action": value.get("required_action") or "",
                }
                for key, value in availability.items() if isinstance(value, dict)
            ],
            "excluded_metrics": [], "validation_errors": [],
            "report_data": dashboard_report,
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
        issues = [
            row for row in issues
            if not (
                row.get("stage") in {"fact_check", "strategy", "report", "dashboard"}
                and state.get("stages", {}).get(row.get("stage"), {}).get("status")
                in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}
            )
        ]
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
            self._save(folder, state)
            return False
        current.update(status="COMPLETE_WITH_WARNINGS" if issues else "COMPLETE", validation_status="PASS", completed_at=now_iso())
        state["quality_summary"] = summary
        state["dependency_state"]["quality"] = "CURRENT"
        self._save(folder, state)
        return True

    def _finish_if_possible(self, folder: Path, state: dict, wanted: list[str]):
        required = [stage for stage in wanted if stage in state["stages"]]
        complete = {"COMPLETE", "COMPLETE_WITH_WARNINGS"}
        if "quality" not in required or any(state["stages"][stage]["status"] not in complete for stage in required):
            return
        state["overall_status"] = "COMPLETED_WITH_WARNINGS" if state["quality_summary"].get("warnings") else "COMPLETED"
        state["primary_action"] = "VIEW_RESULTS"
        state["current_stage"] = "quality"
        state.setdefault("events", []).append({"at": now_iso(), "stage": "quality", "event": "RUN_COMPLETED"})
        self._save(folder, state)

    def _commit_gate(self, folder, state, stage, payload, context, gate=None) -> bool:
        gate = gate or validate_stage(stage, payload, context)
        if not gate.can_continue:
            self._block(folder, state, stage, gate.errors, "BLOCKED_DATA" if stage == "data" else "BLOCKED_QUALITY")
            return False
        issues_path = Path(folder) / "quality/issues.json"
        issues = _read(issues_path, {"issues": []}).get("issues", [])
        if any(row.get("stage") == stage for row in issues):
            _write(issues_path, {
                "schema_version": "2.0",
                "issues": [row for row in issues if row.get("stage") != stage],
            })
        current = state["stages"][stage]
        current.update(status="COMPLETE_WITH_WARNINGS" if gate.warnings else "COMPLETE", validation_status=gate.status, completed_at=now_iso(), error_codes=[])
        state["dependency_state"][stage] = "CURRENT"
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "GATE_VALIDATED", "detail": gate.status})
        self._save(folder, state)
        return True

    def _block(self, folder: Path, state: dict, stage: str, errors: list[dict], overall: str):
        normalized = [self._normalize_issue(x, state["stages"][stage].get("attempt", 0)) for x in errors]
        current = state["stages"][stage]
        current.update(status="BLOCKED", validation_status="BLOCKED", error_codes=[x.get("rule_id") for x in normalized])
        state["overall_status"] = overall
        existing = _read(folder / "quality/issues.json", {"issues": []}).get("issues", [])
        _write(folder / "quality/issues.json", {"schema_version": "2.0", "issues": [x for x in existing if x.get("stage") != stage] + normalized})
        state.setdefault("events", []).append({"at": now_iso(), "stage": stage, "event": "STAGE_BLOCKED", "error_codes": current["error_codes"]})
        self._save(folder, state)

    @staticmethod
    def _normalize_issue(issue: dict, attempt: int) -> dict:
        payload = dict(issue)
        identity = payload.get("entity_id") or payload.get("location") or "root"
        payload.setdefault("error_id", f"{payload.get('stage')}:{attempt}:{payload.get('rule_id')}:{identity}")
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
    def _artifact_contract(stage):
        from .agents import stage_output_contract
        return stage_output_contract(stage)

    @staticmethod
    def _stage_inputs(folder: Path, stage: str) -> dict:
        if stage == "data":
            from research_platform.data_requirements import build_requirements
            from research_platform.search import build_search_plan

            scope = _read(folder / "00_analysis_scope.json", {})
            requirements = build_requirements(scope)
            return {
                "00_analysis_scope.json": scope,
                "data/planned_requirements.json": requirements,
                "data/search_plan.json": build_search_plan(scope, requirements),
            }
        paths = {
            "research": ["data/requirements.json", "data/source_registry.json", "data/observations.json", "data/sufficiency.json"],
            "review": [
                "research/claims.json", "research/research_model.json",
                "data/source_registry.json", "data/observations.json", "data/sufficiency.json",
            ],
            "fact_check": ["research/claims.json", "02_review_notes.json", "data/sources.json", "data/observations.json"],
            "strategy": ["00_analysis_scope.json", "fact_check/verified_claims.json", "human/feedback.json", "data/observations.json", "02_review_notes.json"],
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
            requirements = _read(folder / "data/requirements.json", {"datasets": []})
            required_dataset_ids = [
                row.get("dataset_id") for row in requirements.get("datasets", [])
                if row.get("priority") in {"CRITICAL", "IMPORTANT"} and row.get("dataset_id")
            ]
            return {"claims": artifacts["claims"]}, {
                "observations": obs, "sources": src,
                "required_dataset_ids": required_dataset_ids,
            }
        if stage == "review":
            artifacts["review_notes"] = normalize_review_notes(artifacts["review_notes"])
            return {"issues": artifacts["review_notes"]}, {}
        if stage == "fact_check":
            src = _read(folder / "data/sources.json", _read(folder / "data/source_registry.json", {"sources": []})).get("sources", [])
            obs = _read(folder / "data/observations.json", {"observations": []}).get("observations", [])
            research_claims = _read(folder / "research/claims.json", {"claims": []}).get("claims", [])
            normalized = normalize_fact_check(artifacts["verified_claims"], research_claims, obs, src)
            artifacts["verified_claims"] = normalized
            return normalized, {"sources": src, "observations": obs, "research_claims": research_claims}
        if stage == "strategy":
            artifacts["report_model"] = normalize_report_model(artifacts["report_model"])
            claims = _read(folder / "fact_check/verified_claims.json", {"claims": []}).get("claims", [])
            review_ids = [row.get("review_id") for row in _read(folder / "02_review_notes.json", {"issues": []}).get("issues", [])]
            return {
                "recommendations": artifacts["recommendations"],
                "report_model": artifacts["report_model"],
            }, {"claims": claims, "review_ids": review_ids}
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
            if name == "verified_claims":
                claims = value.get("claims", [])
                for index, claim in enumerate(claims, 1):
                    claim["display_id"] = claim.get("display_id") or f"F{index}"
                value = {
                    "schema_version": "2.0", "claims": claims,
                    "observation_verifications": value.get("observation_verifications", []),
                }
            if name in {"claims", "verified_claims", "recommendations", "review_notes"}:
                if name != "verified_claims":
                    key = {"review_notes": "issues"}.get(name, name)
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
                observation_verifications = value.get("observation_verifications", [])
                _write(folder / "03_fact_check.json", {"schema_version": "2.0", "claims": claims, "observation_verifications": observation_verifications})
        if stage == "data":
            from research_platform.search import build_search_plan
            from research_platform.sufficiency import build_gap_search_plan

            scope = _read(folder / "00_analysis_scope.json", {})
            search_plan = build_search_plan(scope, artifacts["requirements"])
            gap_plan = build_gap_search_plan(artifacts["sufficiency"], search_plan)
            _write(folder / "data/search_plan.json", search_plan)
            _write(folder / "data/gap_search_plan.json", gap_plan)
