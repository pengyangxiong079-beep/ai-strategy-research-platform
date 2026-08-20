"""Dry-run planning and resumable dependency-aware revision execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import shutil

from .model import STAGE_ORDER, load_run_state, now_iso, save_run_state
from .orchestrator import AGENT_STAGES, PipelineV2Orchestrator


REVISION_TYPES = {"LOCAL_REPAIR", "STRATEGY_ONLY", "FACT_VERIFICATION", "FULL_RESEARCH", "TECHNICAL_RETRY", "FACT_CHECK_CONTRACT_REVALIDATION", "STRATEGY_CONTRACT_REVALIDATION", "TARGETED_GAP_SEARCH"}
EXECUTION_BY_TYPE = {
    "LOCAL_REPAIR": ["report", "quality", "dashboard"],
    "STRATEGY_ONLY": ["strategy", "report", "quality", "dashboard"],
    "FACT_VERIFICATION": ["fact_check", "human", "strategy", "report", "quality", "dashboard"],
    "FACT_CHECK_CONTRACT_REVALIDATION": ["human", "strategy", "report", "quality", "dashboard"],
    "STRATEGY_CONTRACT_REVALIDATION": ["report", "quality", "dashboard"],
    "TARGETED_GAP_SEARCH": ["data", "research", "review", "fact_check", "human", "strategy", "report", "quality", "dashboard"],
}


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _write(path: Path, payload):
    from main import atomic_write_json
    atomic_write_json(path, payload)


def _artifact_hashes(folder: Path):
    result = {}
    for relative in ("00_analysis_scope.json", "data/observations.json", "03_fact_check.json", "04_final_report.md", "04_report_data.json", "05_quality_check.json", "06_dashboard_data.json"):
        path = folder / relative
        if path.is_file():
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


@dataclass
class RevisionPlan:
    revision_id: str
    base_revision_id: str
    revision_type: str
    requested_changes: list[str] = field(default_factory=list)
    affected_object_ids: list[str] = field(default_factory=list)
    changed_artifacts: list[str] = field(default_factory=list)
    invalidated_stages: list[str] = field(default_factory=list)
    execution_stages: list[str] = field(default_factory=list)
    preserved_stages: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    estimated_agent_calls: int = 0
    estimated_local_steps: int = 0
    status: str = "PLANNED"
    created_at: str = field(default_factory=now_iso)
    scope_changed: bool = False
    scope_diff: dict = field(default_factory=dict)
    data_as_of_date: str = ""

    def to_dict(self):
        return asdict(self)


def next_revision_id(run_folder: Path) -> str:
    root = Path(run_folder) / "revisions"
    used = []
    if root.is_dir():
        for child in root.glob("rev_*" ):
            try:
                used.append(int(child.name.split("_")[-1]))
            except ValueError:
                continue
    return f"rev_{max(used, default=0) + 1:03d}"


def plan_revision(run_folder, revision_type: str, *, requested_changes=(),
                  affected_object_ids=(), scope_changed=False, scope_diff=None,
                  data_as_of_date="") -> RevisionPlan:
    folder = Path(run_folder)
    state = load_run_state(folder)
    if not state or state.get("pipeline_version") != "2.0":
        raise ValueError("Legacy运行只读；请先显式迁移到V2")
    revision_type = "FULL_RESEARCH" if revision_type == "FULL_RE_RESEARCH" else revision_type
    if revision_type not in REVISION_TYPES:
        raise ValueError(f"未知revision_type：{revision_type}")
    if revision_type == "FULL_RESEARCH":
        execution = (["scope"] if scope_changed else []) + [
            "data", "research", "review", "fact_check", "human", "strategy", "report", "quality", "dashboard"
        ]
    elif revision_type == "TECHNICAL_RETRY":
        failed_stage = state.get("current_stage")
        if state.get("overall_status") != "FAILED_TECHNICAL" or failed_stage not in AGENT_STAGES:
            raise ValueError("TECHNICAL_RETRY requires a FAILED_TECHNICAL Agent stage")
        execution = list(STAGE_ORDER[STAGE_ORDER.index(failed_stage):])
    else:
        execution = list(EXECUTION_BY_TYPE[revision_type])
    preserved = [x for x in STAGE_ORDER if x not in execution]
    affected = [str(x).strip() for x in affected_object_ids if str(x).strip()]
    requires_human = revision_type in {"FULL_RESEARCH", "TECHNICAL_RETRY", "FACT_CHECK_CONTRACT_REVALIDATION", "TARGETED_GAP_SEARCH"} or (revision_type == "FACT_VERIFICATION" and bool(affected))
    changed = {
        "LOCAL_REPAIR": ["strategy/report_model.json"],
        "STRATEGY_ONLY": ["strategy/recommendations.json", "strategy/report_model.json"],
        "FACT_VERIFICATION": ["fact_check/verified_claims.json"],
        "FULL_RESEARCH": ["00_analysis_scope.json", "data/source_registry.json", "data/observations.json"],
        "TECHNICAL_RETRY": [f"stage:{state.get('current_stage')}"],
        "FACT_CHECK_CONTRACT_REVALIDATION": ["fact_check/verified_claims.json", "03_fact_check.json"],
        "STRATEGY_CONTRACT_REVALIDATION": ["strategy/recommendations.json", "strategy/report_model.json"],
        "TARGETED_GAP_SEARCH": ["data/source_registry.json", "data/observations.json", "data/sufficiency.json"],
    }[revision_type]
    plan = RevisionPlan(
        revision_id=next_revision_id(folder),
        base_revision_id=state.get("active_revision_id") or state.get("revision_id", "rev_000"),
        revision_type=revision_type,
        requested_changes=[str(x).strip() for x in requested_changes if str(x).strip()],
        affected_object_ids=affected,
        changed_artifacts=changed,
        invalidated_stages=execution,
        execution_stages=execution,
        preserved_stages=preserved,
        requires_human_review=requires_human,
        estimated_agent_calls=sum(x in AGENT_STAGES for x in execution),
        estimated_local_steps=sum(x not in AGENT_STAGES and x != "human" for x in execution),
        scope_changed=bool(scope_changed), scope_diff=scope_diff or {}, data_as_of_date=data_as_of_date,
    )
    plan_root = folder / "revision_plans"
    _write(plan_root / f"{plan.revision_id}.json", plan.to_dict())
    return plan


class RevisionExecutor:
    def __init__(self, orchestrator: PipelineV2Orchestrator):
        self.orchestrator = orchestrator

    def create(self, base_folder, plan: RevisionPlan, *, updated_scope: dict | None = None,
               source_folder=None) -> Path:
        base = Path(base_folder)
        revision = base / "revisions" / plan.revision_id
        if revision.exists():
            raise FileExistsError(f"Revision已存在：{plan.revision_id}")
        revision.mkdir(parents=True)
        source = Path(source_folder) if source_folder else base
        self._copy_base(source, revision)
        state = load_run_state(revision)
        state["revision_id"] = plan.revision_id
        state["overall_status"] = "REVISION_IN_PROGRESS"
        state["active_revision_id"] = plan.base_revision_id
        for stage in plan.invalidated_stages:
            state["stages"][stage]["status"] = "STALE"
            state["stages"][stage]["stale_reason"] = f"Revision {plan.revision_id}: {plan.revision_type}"
            state["stages"][stage]["attempt"] = 0
            state["dependency_state"][stage] = "STALE"
        state.setdefault("events", []).append({"at": now_iso(), "stage": plan.execution_stages[0], "event": "REVISION_CREATED", "revision_id": plan.revision_id})
        save_run_state(revision, state)
        if updated_scope is not None:
            _write(revision / "00_analysis_scope.json", updated_scope)
        self._mark_feedback(revision, plan.affected_object_ids)
        plan.status = "CREATED"
        _write(revision / "revision_plan.json", plan.to_dict())
        _write(revision / "revision_manifest.json", {
            "schema_version": "2.0", "revision_id": plan.revision_id,
            "parent_revision": plan.base_revision_id, "base_revision": plan.base_revision_id,
            "revision_type": plan.revision_type, "status": "CREATED",
            "created_at": plan.created_at, "started_at": None, "completed_at": None,
            "final_status": "CREATED", "active": False,
            "rerun_stages": plan.execution_stages, "preserved_stages": plan.preserved_stages,
            "invalidated_artifacts": plan.changed_artifacts,
            "input_hashes": _artifact_hashes(source), "output_hashes": {}, "error_message": "",
            "scope_diff": plan.scope_diff, "data_as_of_date": plan.data_as_of_date,
        })
        self._save_execution(revision, plan, "CREATED", [], plan.execution_stages)
        return revision

    def create_targeted_gap_search(self, base_folder, source_folder, targets: list[dict],
                                   *, max_rounds=2) -> tuple[RevisionPlan, Path]:
        """Create an auditable revision that searches only selected data gaps."""
        base, source = Path(base_folder), Path(source_folder)
        state = load_run_state(source)
        if not state or state.get("pipeline_version") != "2.0":
            raise ValueError("Targeted gap search requires a Pipeline V2 source run")
        if any(
            row.get("status") == "RUNNING"
            for name, row in state.get("stages", {}).items() if name in AGENT_STAGES
        ):
            raise RuntimeError("An Agent stage is already running; wait before starting targeted gap search")
        prior_rounds = sum(
            1 for marker_path in (base / "revisions").glob("rev_*/data/targeted_gap_search.json")
            if _read(marker_path, {}).get("status") in {"RUNNING", "COMPLETED"}
        )
        max_rounds = max(0, int(max_rounds))
        if prior_rounds >= max_rounds:
            raise RuntimeError(
                f"Targeted gap search limit reached ({prior_rounds}/{max_rounds}); "
                "accept the evidence boundary or create a manually scoped revision"
            )
        normalized = [row for row in targets if row.get("dataset_id")]
        if not normalized:
            raise ValueError("No eligible CRITICAL/IMPORTANT gap is available")
        plan = plan_revision(
            base, "TARGETED_GAP_SEARCH",
            requested_changes=["Search only confirmed CRITICAL/IMPORTANT evidence gaps"],
            affected_object_ids=[row.get("gap_id") or row["dataset_id"] for row in normalized],
        )
        plan.base_revision_id = state.get("revision_id", "rev_000")
        _write(base / "revision_plans" / f"{plan.revision_id}.json", plan.to_dict())
        revision = self.create(base, plan, source_folder=source)
        # A new Review/Fact Check result requires a fresh decision.  Prior
        # feedback remains preserved in the source revision's audit trail.
        _write(revision / "human/feedback.json", {"schema_version": "2.0", "feedback": []})
        sufficiency = _read(source / "data/sufficiency.json", {})
        requirements = _read(source / "data/requirements.json", {})
        requirement_map = {
            row.get("dataset_id"): row for row in requirements.get("datasets", [])
            if isinstance(row, dict) and row.get("dataset_id")
        }
        target_ids = list(dict.fromkeys(row["dataset_id"] for row in normalized))
        queries = []
        for row in normalized:
            for raw in row.get("recommended_queries") or []:
                query = dict(raw) if isinstance(raw, dict) else {"query": str(raw), "query_text": str(raw)}
                if query.get("query_text") or query.get("query"):
                    queries.append(query)
        previous_marker = _read(source / "data/targeted_gap_search.json", {})
        marker = {
            "schema_version": "1.0", "status": "REQUESTED", "requested_at": now_iso(),
            "target_dataset_ids": target_ids, "targets": normalized,
            "previous_rounds": int(sufficiency.get("gap_search_rounds_completed") or 0),
            "attempt_count": max(prior_rounds, int(previous_marker.get("attempt_count") or 0)),
            "repair_context": {
                "mode": "TARGETED_GAP_SEARCH", "target_dataset_ids": target_ids,
                "targets": [{**row, "requirement": requirement_map.get(row["dataset_id"], {})} for row in normalized],
                "queries": queries,
                "source_priority": ["official disclosures", "regulatory filings", "investor relations", "primary documentation"],
                "completion_rule": "Search only confirmed targets; merge verified additions with existing evidence; keep unresolved gaps explicit.",
            },
        }
        _write(revision / "data/targeted_gap_search.json", marker)
        return plan, revision

    def execute(self, base_folder, revision_id: str, *, human_feedback: dict | None = None) -> dict:
        revision = Path(base_folder) / "revisions" / revision_id
        plan = RevisionPlan(**_read(revision / "revision_plan.json", {}))
        execution = _read(revision / "execution_state.json", {})
        if execution.get("plan_status") in {"CANCELLED", "COMPLETED"}:
            return execution
        execution["plan_status"] = "RUNNING"
        manifest = _read(revision / "revision_manifest.json", {})
        if not manifest.get("started_at"):
            manifest["started_at"] = now_iso()
        manifest["status"] = "RUNNING"
        _write(revision / "revision_manifest.json", manifest)
        _write(revision / "execution_state.json", execution)
        while execution.get("pending_stages"):
            control = _read(revision / "execution_state.json", {})
            if control.get("plan_status") in {"PAUSED", "CANCELLED"}:
                return control
            stage = execution["pending_stages"][0]
            execution["current_stage"] = stage
            _write(revision / "execution_state.json", execution)
            if stage == "human" and plan.requires_human_review and human_feedback is None:
                self.orchestrator.execute(revision, stages=["human"], stop_before_human=True)
                execution["plan_status"] = "AWAITING_HUMAN_REVIEW"
                execution["checkpoint_at"] = now_iso()
                _write(revision / "execution_state.json", execution)
                return execution
            state = self.orchestrator.execute(revision, stages=[stage], human_feedback=human_feedback if stage == "human" else None)
            if state["stages"][stage]["status"] not in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}:
                execution.update(plan_status="FAILED" if state["stages"][stage]["status"] != "AWAITING_USER" else "AWAITING_HUMAN_REVIEW", failed_stage=stage)
                execution["attempts"][stage] = state["stages"][stage].get("attempt", 0)
                execution["checkpoint_at"] = now_iso()
                _write(revision / "execution_state.json", execution)
                self._update_manifest(revision, execution["plan_status"], False)
                return execution
            execution["pending_stages"].pop(0)
            execution["completed_stages"].append(stage)
            execution["attempts"][stage] = state["stages"][stage].get("attempt", 0)
            execution["failed_stage"] = None
            execution["checkpoint_at"] = now_iso()
            _write(revision / "execution_state.json", execution)
            control = _read(revision / "execution_state.json", {})
            if control.get("plan_status") in {"PAUSED", "CANCELLED"}:
                return control
        execution.update(plan_status="COMPLETED", current_stage=None, checkpoint_at=now_iso())
        _write(revision / "execution_state.json", execution)
        state = load_run_state(revision)
        state["overall_status"] = (
            "COMPLETED_WITH_WARNINGS"
            if state.get("quality_summary", {}).get("warnings") else "COMPLETED"
        )
        state["current_stage"] = "quality"
        state["primary_action"] = "VIEW_RESULTS"
        state.setdefault("events", []).append({
            "at": now_iso(), "stage": "quality", "event": "REVISION_COMPLETED",
            "revision_id": revision_id,
        })
        self.orchestrator._save(revision, state)
        self._update_manifest(revision, "COMPLETED", True)
        self._activate(Path(base_folder), revision_id)
        return execution

    def recover_blocked_fact_check(self, base_folder, *, feedback_source=None) -> dict:
        """Recover a legacy contract false-negative from its saved candidate."""
        base = Path(base_folder)
        state = load_run_state(base)
        if state.get("overall_status") != "BLOCKED_QUALITY" or state.get("current_stage") != "fact_check":
            raise ValueError("Local Fact Check recovery requires a run blocked at fact_check")
        candidates = sorted(
            path for path in (base / "quality/candidates").glob("fact_check_attempt_*.json")
            if not path.stem.endswith("_invalid")
        )
        if not candidates:
            raise ValueError("No structured Fact Check candidate is available for local recovery")
        candidate = _read(candidates[-1], {})
        artifact = candidate.get("artifacts", {}).get("verified_claims")
        if not isinstance(artifact, (dict, list)):
            raise ValueError("Latest Fact Check candidate has no recoverable verified_claims artifact")

        plan = plan_revision(
            base, "FACT_CHECK_CONTRACT_REVALIDATION",
            requested_changes=["Normalize and revalidate the saved Fact Check candidate under the current contract"],
        )
        revision = self.create(base, plan)
        self.orchestrator.revalidate_fact_check_artifact(revision, artifact)
        if feedback_source:
            source = Path(feedback_source) / "human/feedback.json"
            payload = _read(source, {"schema_version": "2.0", "feedback": []})
            if payload.get("feedback"):
                _write(revision / "human/feedback.json", payload)
        result = self.execute(base, plan.revision_id)
        return {**result, "revision_id": plan.revision_id}

    def recover_blocked_data_candidate(self, base_folder, revision_id) -> dict:
        """Recover a Data envelope that lost only its final root brace.

        The saved candidate is re-parsed and deterministically gated locally;
        downstream research stages then resume normally. No Data Agent call is
        made and no search round is consumed.
        """
        from .envelope import parse_envelope

        base = Path(base_folder)
        revision = base / "revisions" / revision_id
        state = load_run_state(revision)
        execution = self._load_execution(base, revision_id)
        if (
            execution.get("plan_status") != "FAILED"
            or execution.get("failed_stage") != "data"
            or state.get("current_stage") != "data"
        ):
            raise ValueError("Local Data recovery requires a revision failed at data")
        candidates = sorted(
            (revision / "quality/candidates").glob("data_attempt_*_invalid.json"),
            key=lambda path: path.stat().st_mtime,
        )
        if not candidates:
            raise ValueError("No saved invalid Data candidate is available")
        saved = _read(candidates[-1], {})
        attempt = int(saved.get("attempt") or state.get("stages", {}).get("data", {}).get("attempt") or 1)
        envelope = parse_envelope(
            saved.get("raw_response"), stage="data", attempt=attempt,
            run_id=state["run_id"], revision_id=state.get("revision_id", revision_id),
        )
        _write(
            revision / "quality/candidates" / f"data_attempt_{attempt}_recovered.json",
            envelope,
        )
        self.orchestrator.revalidate_data_artifacts(revision, envelope["artifacts"])
        pending = list(execution.get("pending_stages") or [])
        if pending and pending[0] == "data":
            pending.pop(0)
        completed = list(execution.get("completed_stages") or [])
        if "data" not in completed:
            completed.append("data")
        execution.update({
            "plan_status": "CREATED", "current_stage": None,
            "completed_stages": completed, "pending_stages": pending,
            "failed_stage": None, "checkpoint_at": now_iso(),
        })
        execution.setdefault("attempts", {})["data"] = attempt
        _write(revision / "execution_state.json", execution)
        return self.execute(base, revision_id)

    def recover_blocked_strategy(self, base_folder) -> dict:
        """Recover an equivalent but wrapped Strategy artifact without an Agent call."""
        from .envelope import parse_envelope

        base = Path(base_folder)
        state = load_run_state(base)
        if state.get("overall_status") != "BLOCKED_QUALITY" or state.get("current_stage") != "strategy":
            raise ValueError("Local Strategy recovery requires a run blocked at strategy")
        candidates = sorted((base / "quality/candidates").glob("strategy_attempt_*_invalid.json"))
        if not candidates:
            raise ValueError("No saved Strategy candidate is available for local recovery")
        saved = _read(candidates[-1], {})
        attempt = int(saved.get("attempt") or state.get("stages", {}).get("strategy", {}).get("attempt") or 1)
        envelope = parse_envelope(
            saved.get("raw_response"), stage="strategy", attempt=attempt,
            run_id=state["run_id"], revision_id=state.get("revision_id", "rev_000"),
        )
        plan = plan_revision(
            base, "STRATEGY_CONTRACT_REVALIDATION",
            requested_changes=["Normalize and revalidate the saved Strategy candidate under the current contract"],
        )
        revision = self.create(base, plan)
        self.orchestrator.revalidate_strategy_artifacts(revision, envelope["artifacts"])
        result = self.execute(base, plan.revision_id)
        return {**result, "revision_id": plan.revision_id}

    def pause(self, base_folder, revision_id):
        return self._set_status(base_folder, revision_id, "PAUSED")

    def resume(self, base_folder, revision_id, *, human_feedback=None):
        execution = self._load_execution(base_folder, revision_id)
        revision = Path(base_folder) / "revisions" / revision_id
        state = load_run_state(revision)
        running_stage = execution.get("current_stage")
        if (
            execution.get("plan_status") == "RUNNING"
            and running_stage in AGENT_STAGES
            and state.get("stages", {}).get(running_stage, {}).get("status") == "RUNNING"
        ):
            raise RuntimeError(
                f"{running_stage} Agent is already running for {revision_id}; "
                "wait for it to finish before retrying"
            )
        if execution.get("plan_status") not in {"PAUSED", "FAILED", "AWAITING_HUMAN_REVIEW", "CREATED", "RUNNING"}:
            return execution
        return self.execute(base_folder, revision_id, human_feedback=human_feedback)

    def retry_failed_stage(self, base_folder, revision_id, *, human_feedback=None):
        execution = self._load_execution(base_folder, revision_id)
        failed = execution.get("failed_stage")
        if failed and (not execution.get("pending_stages") or execution["pending_stages"][0] != failed):
            execution["pending_stages"].insert(0, failed)
        execution["plan_status"] = "CREATED"
        execution["failed_stage"] = None
        revision = Path(base_folder) / "revisions" / revision_id
        state = load_run_state(revision)
        if failed:
            state["stages"][failed]["attempt"] = 0
            state["stages"][failed]["status"] = "STALE"
            state["stages"][failed]["error_codes"] = []
            save_run_state(revision, state)
        _write(revision / "execution_state.json", execution)
        return self.execute(base_folder, revision_id, human_feedback=human_feedback)

    def repair_report_and_resume_locally(self, base_folder, revision_id):
        """Resume a report-only contract false negative without Agent calls."""
        revision = Path(base_folder) / "revisions" / revision_id
        execution = self._load_execution(base_folder, revision_id)
        if execution.get("plan_status") != "FAILED" or execution.get("failed_stage") != "report":
            raise ValueError("Local report repair requires a revision failed at report")
        self.orchestrator.normalize_saved_report_model(revision)
        return self.retry_failed_stage(base_folder, revision_id)

    def cancel(self, base_folder, revision_id):
        execution = self._set_status(base_folder, revision_id, "CANCELLED")
        self._update_manifest(Path(base_folder) / "revisions" / revision_id, "CANCELLED", False)
        return execution

    @staticmethod
    def _copy_base(base: Path, revision: Path):
        for name in ("data", "research", "review", "fact_check", "human", "strategy", "quality", "dashboard", "rendered"):
            source = base / name
            if source.is_dir():
                shutil.copytree(source, revision / name)
        for name in ("run_state.json", "00_analysis_scope.json", "run_manifest.json", "02_review_notes.json", "03_fact_check.json", "04_final_report.md", "04_report_data.json", "05_quality_check.json", "06_dashboard_data.json"):
            source = base / name
            if source.is_file():
                shutil.copy2(source, revision / name)

    @staticmethod
    def _mark_feedback(revision: Path, affected_ids: list[str]):
        path = revision / "human/feedback.json"
        payload = _read(path, {"schema_version": "2.0", "feedback": []})
        affected = set(affected_ids)
        for row in payload.get("feedback", []):
            referenced = set(row.get("claim_ids", [])) | set(row.get("affected_object_ids", []))
            if referenced & affected:
                row["status"] = "NEEDS_REVALIDATION"
        _write(path, payload)

    @staticmethod
    def _save_execution(revision: Path, plan: RevisionPlan, status: str, completed, pending):
        _write(revision / "execution_state.json", {
            "plan_status": status, "current_stage": None, "completed_stages": list(completed),
            "pending_stages": list(pending), "failed_stage": None, "attempts": {}, "checkpoint_at": now_iso(),
        })

    @staticmethod
    def _load_execution(base_folder, revision_id):
        return _read(Path(base_folder) / "revisions" / revision_id / "execution_state.json", {})

    @staticmethod
    def _set_status(base_folder, revision_id, status):
        path = Path(base_folder) / "revisions" / revision_id / "execution_state.json"
        execution = _read(path, {})
        execution["plan_status"] = status
        execution["checkpoint_at"] = now_iso()
        _write(path, execution)
        return execution

    @staticmethod
    def _update_manifest(revision: Path, status: str, active: bool):
        path = revision / "revision_manifest.json"
        manifest = _read(path, {})
        manifest.update(status=status, final_status=status, active=active, updated_at=now_iso(), output_hashes=_artifact_hashes(revision))
        if status == "COMPLETED":
            manifest["completed_at"] = now_iso()
            manifest["error_message"] = ""
        elif status in {"FAILED", "CANCELLED"}:
            execution = _read(revision / "execution_state.json", {})
            manifest["error_message"] = str(execution.get("failed_stage") or status)
        _write(path, manifest)

    @staticmethod
    def _activate(base: Path, revision_id: str):
        state = load_run_state(base)
        state["active_revision_id"] = revision_id
        state.setdefault("events", []).append({"at": now_iso(), "stage": "quality", "event": "REVISION_ACTIVATED", "revision_id": revision_id})
        save_run_state(base, state)
