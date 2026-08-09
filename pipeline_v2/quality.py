"""Quality status aggregation, structured errors and bounded repair decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import uuid

REPAIR_TYPES = {"LOCAL_REPAIRABLE", "STAGE_RETRY", "UPSTREAM_DATA_REQUIRED", "HUMAN_REQUIRED"}


@dataclass(frozen=True)
class ErrorPacket:
    rule_id: str
    stage: str
    artifact: str
    location: str
    entity_id: str
    excerpt: str
    reason: str
    expected: str
    actual: str
    suggested_action: str
    repair_type: str
    severity: str = "ERROR"
    error_id: str = ""
    allowed_actions: tuple[str, ...] = ()

    def to_dict(self):
        payload = asdict(self)
        payload["error_id"] = self.error_id or f"ERR_{uuid.uuid4().hex}"
        payload["json_pointer"] = payload.pop("location")
        payload["allowed_actions"] = list(payload["allowed_actions"])
        return payload


def aggregate_quality(issues, *, data_blocked=False, technical_failure=False):
    if technical_failure:
        status = "FAILED_TECHNICAL"
    elif data_blocked:
        status = "BLOCKED_DATA"
    elif any(i.get("severity") == "ERROR" and not i.get("resolved") for i in issues):
        status = "BLOCKED_QUALITY"
    elif any(i.get("severity") == "WARNING" and not i.get("resolved") for i in issues):
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"
    root_causes = aggregate_root_causes(issues)
    return {
        "status": status,
        "blocking": sum(i.get("severity") == "ERROR" and not i.get("resolved") for i in issues),
        "warnings": sum(i.get("severity") == "WARNING" and not i.get("resolved") for i in issues),
        "resolved": sum(bool(i.get("resolved")) for i in issues),
        "raw_issues": list(issues),
        "root_causes": root_causes,
        "affected_items": sum(len(row["affected_items"]) for row in root_causes),
        "automatic_fixability": all(row["automatic_fixability"] for row in root_causes) if root_causes else True,
        "recommended_revision_type": _recommended_revision_type(root_causes),
    }


def aggregate_root_causes(issues):
    """Group repeated item-level failures without hiding raw audit records."""
    groups = {}
    for row in issues:
        rule = str(row.get("rule_id") or row.get("code") or "UNKNOWN")
        root = str(row.get("root_cause") or row.get("reason") or row.get("message") or rule)
        # Missing sequential Review IDs are one contract failure, not N unrelated errors.
        if rule.startswith("REVIEW_"):
            root = "Review output did not satisfy the canonical sequential R1-Rn contract"
        elif rule == "OBSERVATION_LINEAGE_COUNT_MISMATCH":
            root = "Canonical Observation lineage is not preserved across Coverage, Fact Check, Report Data, and Dashboard"
        key = (row.get("stage") or "quality", rule, root)
        group = groups.setdefault(key, {
            "root_cause_id": f"RC_{len(groups) + 1:03d}", "stage": key[0], "rule_id": rule,
            "root_cause": root, "affected_items": [],
            "automatic_fixability": row.get("repair_type") in {"LOCAL_REPAIRABLE", "STAGE_RETRY"},
            "recommended_action": "RETRY_REVIEW" if rule.startswith("REVIEW_") else row.get("repair_type", "HUMAN_REQUIRED"),
        })
        if rule == "OBSERVATION_LINEAGE_COUNT_MISMATCH":
            affected = row.get("artifact")
        else:
            affected = row.get("entity_id") or row.get("location") or row.get("json_pointer") or row.get("error_id")
        if affected and affected not in group["affected_items"]:
            group["affected_items"].append(affected)
    return list(groups.values())


def _recommended_revision_type(root_causes):
    actions = {row.get("recommended_action") for row in root_causes}
    if "RETRY_REVIEW" in actions:
        return "RETRY_REVIEW"
    if "UPSTREAM_DATA_REQUIRED" in actions:
        return "FULL_RESEARCH"
    if "STAGE_RETRY" in actions:
        return "FACT_VERIFICATION"
    return "LOCAL_REPAIR" if root_causes else "NONE"


def request_repair(state, stage, repair_type):
    if repair_type not in REPAIR_TYPES:
        raise ValueError(f"未知repair_type：{repair_type}")
    budget = state.setdefault("repair_budget", {"stage_max": 2, "run_max": 6, "used": 0, "by_stage": {}})
    used_stage = int(budget.setdefault("by_stage", {}).get(stage, 0))
    allowed = used_stage < int(budget["stage_max"]) and int(budget["used"]) < int(budget["run_max"])
    if allowed:
        budget["used"] += 1
        budget["by_stage"][stage] = used_stage + 1
        return {"allowed": True, "action": repair_type}
    state["stages"][stage]["status"] = "BLOCKED"
    state["overall_status"] = "BLOCKED_QUALITY"
    return {"allowed": False, "action": "HUMAN_REQUIRED", "reason": "AUTO_REPAIR_LIMIT_REACHED"}
