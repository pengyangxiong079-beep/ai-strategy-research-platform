"""Canonical run-state model and atomic persistence."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time

SCHEMA_VERSION = "2.0"
STAGE_ORDER = (
    "scope", "data", "research", "review", "fact_check", "human",
    "strategy", "report", "quality", "dashboard",
)
STAGE_STATUSES = {
    "PENDING", "RUNNING", "VALIDATING", "COMPLETE", "COMPLETE_WITH_WARNINGS",
    "AWAITING_USER", "BLOCKED", "STALE", "FAILED_TECHNICAL",
}
OVERALL_STATUSES = {
    "DRAFT_SCOPE", "AWAITING_SCOPE_CONFIRMATION", "RUNNING", "AWAITING_HUMAN_REVIEW",
    "BLOCKED_DATA", "BLOCKED_QUALITY", "COMPLETED", "COMPLETED_WITH_WARNINGS",
    "REVISION_IN_PROGRESS", "FAILED_TECHNICAL",
}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stage_state(inputs=(), outputs=()):
    return {
        "status": "PENDING", "attempt": 0, "started_at": None, "completed_at": None,
        "input_artifacts": list(inputs), "output_artifacts": list(outputs),
        "validation_status": "PENDING", "error_codes": [], "stale_reason": "",
    }


def create_run_state(run_id: str, scope: dict, revision_id="rev_000"):
    from research_platform.data_acquisition.search_vocabulary import route_industry

    analysis_type = scope.get("analysis_type_id") or "GENERIC_STRATEGY"
    industry_template = route_industry(scope.get("industry"))
    stages = {name: stage_state() for name in STAGE_ORDER}
    stages["scope"] = stage_state((), ("00_analysis_scope.json",))
    stages["scope"].update(status="AWAITING_USER", validation_status="PASS")
    now = now_iso()
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "revision_id": revision_id,
        "pipeline_version": "2.0",
        "configuration": {
            "pipeline_version": "2.0",
            "strict_structured_output": True,
            "allow_legacy_agent_output": False,
        },
        "topic": scope.get("topic", ""), "normalized_analysis_type": analysis_type,
        "industry": scope.get("industry", ""), "base_template": analysis_type.lower(),
        "industry_templates": [industry_template],
        "effective_templates": ["general", analysis_type.lower(), industry_template],
        "current_stage": "scope", "overall_status": "AWAITING_SCOPE_CONFIRMATION",
        "primary_action": "CONFIRM_SCOPE", "artifacts": {}, "stages": stages,
        "quality_summary": {"status": "PENDING", "blocking": 0, "warnings": 0, "resolved": 0},
        "dependency_state": {name: "CURRENT" if name == "scope" else "PENDING" for name in STAGE_ORDER},
        "repair_budget": {"stage_max": 2, "run_max": 6, "used": 0, "by_stage": {}},
        "agent_calls": {"total": 0, "by_stage": {}},
        "active_revision_id": revision_id,
        "events": [{"at": now, "stage": "scope", "event": "RUN_CREATED"}],
        "created_at": now, "updated_at": now,
    }


def validate_run_state(state):
    errors = []
    for field in ("run_id", "topic", "normalized_analysis_type", "current_stage", "overall_status", "stages"):
        if not state.get(field):
            errors.append(f"missing:{field}")
    if state.get("overall_status") not in OVERALL_STATUSES:
        errors.append("invalid:overall_status")
    for name in STAGE_ORDER:
        stage = (state.get("stages") or {}).get(name)
        if not stage:
            errors.append(f"missing:stages.{name}")
        elif stage.get("status") not in STAGE_STATUSES:
            errors.append(f"invalid:stages.{name}.status")
    return errors


def save_run_state(folder, state):
    folder = Path(folder)
    state = dict(state)
    state["updated_at"] = now_iso()
    errors = validate_run_state(state)
    if errors:
        raise ValueError("run_state无效：" + ", ".join(errors))
    path = folder / "run_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".run_state_", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temp = Path(temp_name)
    try:
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for attempt in range(3):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if temp.exists():
            temp.unlink()
    return state


def load_run_state(folder):
    path = Path(folder) / "run_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
