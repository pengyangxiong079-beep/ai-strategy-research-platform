"""Dry-run planning and resumable dependency-aware revision execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import shutil

from .model import STAGE_ORDER, load_run_state, now_iso, save_run_state
from .orchestrator import AGENT_STAGES, PipelineV2Orchestrator


REVISION_TYPES = {"LOCAL_REPAIR", "STRATEGY_ONLY", "FACT_VERIFICATION", "FULL_RESEARCH"}
EXECUTION_BY_TYPE = {
    "LOCAL_REPAIR": ["report", "quality", "dashboard"],
    "STRATEGY_ONLY": ["strategy", "report", "quality", "dashboard"],
    "FACT_VERIFICATION": ["fact_check", "human", "strategy", "report", "quality", "dashboard"],
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
    else:
        execution = list(EXECUTION_BY_TYPE[revision_type])
    preserved = [x for x in STAGE_ORDER if x not in execution]
    affected = [str(x).strip() for x in affected_object_ids if str(x).strip()]
    requires_human = revision_type == "FULL_RESEARCH" or (revision_type == "FACT_VERIFICATION" and bool(affected))
    changed = {
        "LOCAL_REPAIR": ["strategy/report_model.json"],
        "STRATEGY_ONLY": ["strategy/recommendations.json", "strategy/report_model.json"],
        "FACT_VERIFICATION": ["fact_check/verified_claims.json"],
        "FULL_RESEARCH": ["00_analysis_scope.json", "data/source_registry.json", "data/observations.json"],
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

    def create(self, base_folder, plan: RevisionPlan, *, updated_scope: dict | None = None) -> Path:
        base = Path(base_folder)
        revision = base / "revisions" / plan.revision_id
        if revision.exists():
            raise FileExistsError(f"Revision已存在：{plan.revision_id}")
        revision.mkdir(parents=True)
        self._copy_base(base, revision)
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
            "input_hashes": _artifact_hashes(base), "output_hashes": {}, "error_message": "",
            "scope_diff": plan.scope_diff, "data_as_of_date": plan.data_as_of_date,
        })
        self._save_execution(revision, plan, "CREATED", [], plan.execution_stages)
        return revision

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
        self._update_manifest(revision, "COMPLETED", True)
        self._activate(Path(base_folder), revision_id)
        return execution

    def pause(self, base_folder, revision_id):
        return self._set_status(base_folder, revision_id, "PAUSED")

    def resume(self, base_folder, revision_id, *, human_feedback=None):
        execution = self._load_execution(base_folder, revision_id)
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
