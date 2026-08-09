from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ContractResult:
    status: str
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    @property
    def can_continue(self):
        return not self.errors


@dataclass(frozen=True)
class StageContract:
    stage: str
    required_inputs: tuple[str, ...]
    output_schema: str
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    blocking_errors: tuple[str, ...]
    allowed_warnings: tuple[str, ...]
    repair_strategy: str
    downstream_dependencies: tuple[str, ...]
    validator: Callable[[dict, dict], ContractResult]

    def validate(self, payload, context=None):
        return self.validator(payload or {}, context or {})


def result(errors=(), warnings=()):
    return ContractResult("BLOCKED" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS"), list(errors), list(warnings))


def issue(rule_id, reason, *, stage, artifact="", location="", expected="", actual="", repair_type="STAGE_RETRY", severity="ERROR", entity_id=""):
    return {
        "rule_id": rule_id, "stage": stage, "artifact": artifact, "location": location,
        "entity_id": entity_id, "excerpt": str(actual)[:300], "reason": reason,
        "expected": expected, "actual": actual, "suggested_action": reason,
        "repair_type": repair_type, "severity": severity,
    }

