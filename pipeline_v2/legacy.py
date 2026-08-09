"""Read-only adapter for historical V1 folders; never writes into them."""

from __future__ import annotations

import json
from pathlib import Path

from .model import STAGE_ORDER


def _json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default if default is not None else {}


def is_v2_run(folder):
    return (Path(folder) / "run_state.json").is_file()


def legacy_view(folder):
    folder = Path(folder)
    manifest = _json(folder / "run_manifest.json", {})
    scope = _json(folder / "00_analysis_scope.json", {})
    final = manifest.get("final_status", "UNKNOWN")
    mapping = {
        "AWAITING_SCOPE_CONFIRMATION": "AWAITING_SCOPE_CONFIRMATION",
        "AWAITING_APPROVAL": "AWAITING_HUMAN_REVIEW", "COMPLETED": "COMPLETED",
        "ERROR": "FAILED_TECHNICAL", "FAILED": "FAILED_TECHNICAL",
    }
    stages = {}
    status_fields = {
        "research": "research_status", "review": "review_status", "fact_check": "fact_check_status",
        "human": "approval_status", "strategy": "strategy_status", "quality": "quality_check_status",
    }
    for stage in STAGE_ORDER:
        raw = manifest.get(status_fields.get(stage, ""), "PENDING")
        status = "COMPLETE" if raw in {"COMPLETED", "APPROVED", "PASS", "PASS_WITH_WARNINGS"} else ("AWAITING_USER" if raw in {"AWAITING_APPROVAL", "PENDING_APPROVAL"} else "PENDING")
        stages[stage] = {"status": status, "attempt": 0, "started_at": None, "completed_at": None, "input_artifacts": [], "output_artifacts": [], "validation_status": raw, "error_codes": [], "stale_reason": ""}
    if (folder / "00_analysis_scope.json").is_file():
        stages["scope"]["status"] = "COMPLETE"
    return {
        "schema_version": "1.x-legacy", "legacy": True, "read_only": True,
        "run_id": manifest.get("run_id", folder.name), "revision_id": manifest.get("latest_revision") or "rev_000",
        "topic": manifest.get("topic") or scope.get("topic") or folder.name,
        "normalized_analysis_type": scope.get("analysis_type_id") or manifest.get("analysis_type", "GENERIC_STRATEGY"),
        "industry": scope.get("industry") or manifest.get("industry", ""), "geography": scope.get("geography") or manifest.get("geography", ""),
        "current_stage": manifest.get("current_stage", "legacy"), "overall_status": mapping.get(final, "RUNNING"),
        "primary_action": "VIEW_RESULTS" if (folder / "04_final_report.md").is_file() else "VIEW_PIPELINE",
        "stages": stages, "quality_summary": {"status": manifest.get("quality_check_status", "UNKNOWN"), "blocking": len([x for x in manifest.get("quality_issues", []) if x.get("status") == "FAIL"]), "warnings": len([x for x in manifest.get("quality_issues", []) if x.get("status") == "WARN"]), "resolved": 0},
        "created_at": manifest.get("created_at", ""), "updated_at": manifest.get("updated_at", ""),
        "artifacts": manifest.get("output_files", {}), "events": [],
    }

