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
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict) or not metadata.get("generated_at") or not metadata.get("agent_role"):
            errors.append("/metadata 必须包含 generated_at 和 agent_role")
    if errors:
        raise AgentOutputError("AGENT_OUTPUT_SCHEMA_INVALID", stage, attempt, excerpt, errors, list(EXPECTED_ARTIFACTS.get(stage, ())))

    missing = [name for name in EXPECTED_ARTIFACTS.get(stage, ()) if name not in payload["artifacts"]]
    if missing:
        raise AgentOutputError(
            "AGENT_OUTPUT_CONTRACT_FAILED", stage, attempt, excerpt,
            [f"缺少 artifacts.{name}" for name in missing], list(EXPECTED_ARTIFACTS.get(stage, ())),
        )
    return payload
