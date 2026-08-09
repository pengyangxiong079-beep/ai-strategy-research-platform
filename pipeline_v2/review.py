"""Canonical Review V2 contract and deterministic Markdown projection."""

from __future__ import annotations

import re

REVIEW_RANGE_PATTERN = re.compile(r"^\s*R\d+\s*(?:-|–|—|~|至)\s*R?\d+\s*$", re.IGNORECASE)
REVIEW_ID_PATTERN = re.compile(r"^R([1-9]\d*)$")
REQUIRED_FIELDS = ("review_id", "severity", "category", "issue", "evidence", "required_action", "status")
ALLOWED_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "ERROR", "WARNING", "INFO"}
ALLOWED_STATUSES = {"OPEN", "RESOLVED", "ACCEPTED", "DEFERRED"}


def validate_review_notes(notes):
    """Return contract errors; range IDs are never partially parsed."""
    errors = []
    if not isinstance(notes, list):
        return [{"rule_id": "REVIEW_NOT_ARRAY", "location": "/issues", "reason": "issues must be an array"}]
    seen = set()
    for index, raw in enumerate(notes):
        item = raw if isinstance(raw, dict) else {}
        location = f"/issues/{index}"
        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            errors.append({"rule_id": "REVIEW_REQUIRED_FIELDS", "location": location, "reason": f"missing required fields: {', '.join(missing)}"})
        review_id = str(item.get("review_id") or "").strip()
        if REVIEW_RANGE_PATTERN.fullmatch(review_id) or re.search(r"R\d+\s*(?:-|–|—|~|至)\s*R?\d+", review_id, re.I):
            errors.append({"rule_id": "REVIEW_ID_RANGE_FORBIDDEN", "location": f"{location}/review_id", "reason": f"range review_id is forbidden: {review_id}"})
            continue
        match = REVIEW_ID_PATTERN.fullmatch(review_id)
        if not match:
            errors.append({"rule_id": "REVIEW_ID_INVALID", "location": f"{location}/review_id", "reason": "review_id must exactly match R1, R2, ..."})
        elif int(match.group(1)) != index + 1:
            errors.append({"rule_id": "REVIEW_ID_SEQUENCE", "location": f"{location}/review_id", "reason": f"expected R{index + 1}, got {review_id}"})
        if review_id in seen:
            errors.append({"rule_id": "REVIEW_ID_DUPLICATE", "location": f"{location}/review_id", "reason": f"duplicate review_id: {review_id}"})
        seen.add(review_id)
        severity = str(item.get("severity") or "").upper()
        status = str(item.get("status") or "").upper()
        if severity not in ALLOWED_SEVERITIES:
            errors.append({"rule_id": "REVIEW_SEVERITY_INVALID", "location": f"{location}/severity", "reason": f"unsupported severity: {severity or 'EMPTY'}"})
        if status not in ALLOWED_STATUSES:
            errors.append({"rule_id": "REVIEW_STATUS_INVALID", "location": f"{location}/status", "reason": f"unsupported status: {status or 'EMPTY'}"})
        if status == "OPEN" and not str(item.get("required_action") or "").strip():
            errors.append({"rule_id": "REVIEW_OPEN_ACTION_REQUIRED", "location": f"{location}/required_action", "reason": "OPEN review issue must define required_action"})
    return errors


def render_review_notes(notes):
    if not notes:
        return "# Review Notes\n\nNo open structured review issues.\n"
    lines = ["# Review Notes", ""]
    for item in notes:
        lines.extend([f"## {item['review_id']} · {item['category']}", "", f"- Severity: {item['severity']}", f"- Status: {item['status']}", f"- Issue: {item['issue']}", f"- Evidence: {item['evidence']}", f"- Required action: {item['required_action']}", ""])
    return "\n".join(lines).rstrip() + "\n"
