"""Strict Pipeline V2 Agent envelope parsing and validation.

V2 intentionally accepts one JSON object only. Tagged blocks, Markdown fences and
prose extraction are V1 compatibility concerns and never enter this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .model import now_iso


EXPECTED_ARTIFACTS = {
    "data": ("requirements", "source_registry", "observations", "sufficiency"),
    "research": ("claims", "research_sections"),
    "review": ("review_notes",),
    "fact_check": ("verified_claims",),
    "strategy": ("recommendations", "report_model"),
}

ARTIFACT_TYPES = {
    "data": {
        "requirements": dict,
        "source_registry": dict,
        "observations": dict,
        "sufficiency": dict,
    },
    "research": {"claims": list, "research_sections": list},
    "review": {"review_notes": list},
    "fact_check": {"verified_claims": (dict, list)},
    "strategy": {"recommendations": list, "report_model": dict},
}

DATA_COLLECTIONS = {
    "requirements": "datasets",
    "source_registry": "sources",
    "observations": "observations",
    "sufficiency": "datasets",
}


def _normalize_single_collection_wrappers(payload: dict, stage: str) -> list[str]:
    """Unwrap an unambiguous ``{"name": [...]}`` around list artifacts.

    Agents occasionally mirror the persisted-file shape even though the
    Envelope contract asks for a bare array.  The two representations contain
    exactly the same information, so spending another live call on this shape
    difference is both wasteful and brittle.  Only exact, same-name,
    single-key wrappers are accepted; additional keys or non-list values still
    fail the strict artifact contract.
    """
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    normalized = []
    for name, expected_type in ARTIFACT_TYPES.get(stage, {}).items():
        accepts_list = expected_type is list or (
            isinstance(expected_type, tuple) and list in expected_type
        )
        value = artifacts.get(name)
        if (
            accepts_list
            and isinstance(value, dict)
            and set(value) == {name}
            and isinstance(value.get(name), list)
        ):
            artifacts[name] = value[name]
            normalized.append(name)
    return normalized


@dataclass
class AgentOutputError(ValueError):
    code: str
    stage: str
    attempt: int
    excerpt: str
    schema_errors: list[str]
    expected_artifact: list[str]
    repair_strategy: str = "STAGE_RETRY"

    def __str__(self):
        return f"{self.code}: {self.stage} attempt {self.attempt}"

    def to_issue(self) -> dict:
        return {
            "error_id": f"{self.stage}:{self.attempt}:{self.code}",
            "rule_id": self.code,
            "stage": self.stage,
            "attempt": self.attempt,
            "artifact": ",".join(self.expected_artifact),
            "json_pointer": "/",
            "location": "/",
            "entity_id": "",
            "excerpt": self.excerpt[:500],
            "reason": "; ".join(self.schema_errors) or self.code,
            "expected": self.expected_artifact,
            "actual": self.excerpt[:500],
            "allowed_actions": ["RETRY_STAGE", "REQUEST_HUMAN_REVIEW"],
            "suggested_action": self.repair_strategy,
            "repair_strategy": self.repair_strategy,
            "repair_type": self.repair_strategy,
            "severity": "ERROR",
        }


def make_envelope(*, run_id: str, revision_id: str, stage: str, attempt: int,
                  artifacts: dict, agent_role: str, warnings=(), unresolved_items=()) -> dict:
    return {
        "schema_version": "2.0",
        "pipeline_version": "2.0",
        "run_id": run_id,
        "revision_id": revision_id,
        "stage": stage,
        "attempt": attempt,
        "status": "COMPLETE",
        "artifacts": artifacts,
        "warnings": list(warnings),
        "unresolved_items": list(unresolved_items),
        "metadata": {"generated_at": now_iso(), "agent_role": agent_role},
    }


def parse_envelope(raw: Any, *, stage: str, attempt: int, run_id: str,
                   revision_id: str) -> dict:
    if isinstance(raw, dict):
        payload = raw
        excerpt = json.dumps(raw, ensure_ascii=False)[:500]
    elif isinstance(raw, str):
        excerpt = raw.strip()[:500]
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as error:
            code = "AGENT_OUTPUT_NOT_STRUCTURED" if raw.lstrip().startswith(("#", "```")) else "AGENT_OUTPUT_SCHEMA_INVALID"
            raise AgentOutputError(code, stage, attempt, excerpt, [str(error)], list(EXPECTED_ARTIFACTS.get(stage, ()))) from None
    else:
        raise AgentOutputError("AGENT_OUTPUT_NOT_STRUCTURED", stage, attempt, repr(raw)[:500], ["输出必须是JSON对象"], list(EXPECTED_ARTIFACTS.get(stage, ())))

    errors = []
    required = {
        "schema_version": "2.0", "pipeline_version": "2.0", "run_id": run_id,
        "revision_id": revision_id, "stage": stage, "attempt": attempt, "status": "COMPLETE",
    }
    if not isinstance(payload, dict):
        errors.append("根节点必须是对象")
    else:
        for key, expected in required.items():
            if payload.get(key) != expected:
                errors.append(f"/{key} 必须等于 {expected!r}")
        if not isinstance(payload.get("artifacts"), dict):
            errors.append("/artifacts 必须是对象")
        if not isinstance(payload.get("warnings", []), list):
            errors.append("/warnings 必须是数组")
        if not isinstance(payload.get("unresolved_items", []), list):
            errors.append("/unresolved_items 必须是数组")
        # Envelope provenance is orchestration metadata, not research evidence.
        # Older/compact Agent responses may omit it even when every canonical
        # artifact is valid. Fill only these deterministic fields locally so a
        # second live Agent call is never spent on timestamps or role labels.
        metadata = payload.get("metadata")
        if metadata is None:
            metadata = {}
            payload["metadata"] = metadata
        if not isinstance(metadata, dict):
            errors.append("/metadata 必须是对象")
        else:
            normalized_fields = []
            if not metadata.get("generated_at"):
                metadata["generated_at"] = now_iso()
                normalized_fields.append("generated_at")
            if not metadata.get("agent_role"):
                metadata["agent_role"] = f"Pipeline V2 {stage} Agent"
                normalized_fields.append("agent_role")
            if normalized_fields:
                metadata["normalized_by"] = "PipelineV2Orchestrator"
                metadata["normalized_fields"] = normalized_fields
    if errors:
        raise AgentOutputError("AGENT_OUTPUT_SCHEMA_INVALID", stage, attempt, excerpt, errors, list(EXPECTED_ARTIFACTS.get(stage, ())))

    missing = [name for name in EXPECTED_ARTIFACTS.get(stage, ()) if name not in payload["artifacts"]]
    if missing:
        raise AgentOutputError(
            "AGENT_OUTPUT_CONTRACT_FAILED", stage, attempt, excerpt,
            [f"缺少 artifacts.{name}" for name in missing], list(EXPECTED_ARTIFACTS.get(stage, ())),
        )
    normalized_artifacts = _normalize_single_collection_wrappers(payload, stage)
    if normalized_artifacts:
        metadata = payload.setdefault("metadata", {})
        metadata["normalized_by"] = "PipelineV2Orchestrator"
        existing = list(metadata.get("normalized_artifacts") or [])
        metadata["normalized_artifacts"] = list(dict.fromkeys(existing + normalized_artifacts))
    artifact_errors = []
    for name, expected_type in ARTIFACT_TYPES.get(stage, {}).items():
        value = payload["artifacts"].get(name)
        if not isinstance(value, expected_type):
            expected_name = " or ".join(row.__name__ for row in expected_type) if isinstance(expected_type, tuple) else expected_type.__name__
            artifact_errors.append(
                f"/artifacts/{name} must be {expected_name}; got {type(value).__name__}"
            )
    if stage == "data":
        for name, collection in DATA_COLLECTIONS.items():
            value = payload["artifacts"].get(name)
            if isinstance(value, dict):
                rows = value.get(collection)
                if not isinstance(rows, list):
                    artifact_errors.append(f"/artifacts/{name}/{collection} must be an array")
                elif any(not isinstance(row, dict) for row in rows):
                    artifact_errors.append(f"/artifacts/{name}/{collection} items must be objects")
    for name, expected_type in ARTIFACT_TYPES.get(stage, {}).items():
        value = payload["artifacts"].get(name)
        accepts_list = expected_type is list or (isinstance(expected_type, tuple) and list in expected_type)
        if accepts_list and isinstance(value, list) and any(
            not isinstance(row, dict) for row in value
        ):
            artifact_errors.append(f"/artifacts/{name} items must be objects")
    if artifact_errors:
        raise AgentOutputError(
            "AGENT_ARTIFACT_SCHEMA_INVALID", stage, attempt, excerpt,
            artifact_errors, list(EXPECTED_ARTIFACTS.get(stage, ())),
        )
    return payload
