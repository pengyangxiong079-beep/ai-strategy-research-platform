from pathlib import Path

from pipeline_v2.ids import stable_id
from ui.repository import read_json


DECISION_OPTIONS = [
    "接受该限制并继续",
    "排除相关结论",
    "降级为推断",
    "暂缓，返回补充或修正",
]


def _decision_from_review(run_id, item):
    issue = item.get("issue") or item.get("reason") or "未提供问题说明"
    required_action = (
        item.get("required_action")
        or item.get("suggested_action")
        or item.get("suggested_fix")
        or "人工确认如何处理该限制"
    )
    claim_ids = list(item.get("claim_ids") or [])
    if item.get("claim_id") and item["claim_id"] not in claim_ids:
        claim_ids.append(item["claim_id"])
    return {
        "decision_id": stable_id("decision", run_id, item.get("review_id")),
        "review_id": item.get("review_id"),
        "source_stage": "review",
        "title": item.get("title") or issue,
        "why": issue,
        "issue": issue,
        "evidence": item.get("evidence") or "未提供具体证据说明",
        "required_action": required_action,
        "severity": item.get("severity") or "UNKNOWN",
        "category": item.get("category") or "general",
        "claim_ids": claim_ids,
        "source_ids": list(item.get("source_ids") or []),
        "agent_suggestion": required_action,
        "options": DECISION_OPTIONS,
    }


def decisions_view_model(run):
    folder = Path(run["folder"])
    review = read_json(folder / "review/review_issues.json", {"issues": []})
    feedback = read_json(folder / "human/feedback.json", {"feedback": []})
    resolved_ids = {
        row.get("decision_id")
        for row in feedback.get("feedback", [])
        if row.get("status") == "RESOLVED"
    }
    deferred_ids = {
        row.get("decision_id")
        for row in feedback.get("feedback", [])
        if row.get("status") == "PENDING"
    }
    pending = []
    for item in review.get("issues", []):
        decision = _decision_from_review(run.get("run_id"), item)
        if (
            decision["decision_id"] not in resolved_ids
            and decision["decision_id"] not in deferred_ids
            and item.get("status", "OPEN") != "RESOLVED"
        ):
            pending.append(decision)
    if (
        run.get("overall_status") == "AWAITING_HUMAN_REVIEW"
        and not pending
        and not feedback.get("feedback")
    ):
        pending.append({
            "decision_id": stable_id("decision", run.get("run_id"), "overall-approval"),
            "review_id": None,
            "source_stage": "fact_check",
            "title": "确认事实核验结果",
            "why": "Strategy 开始前需要确认核验结论和已披露的数据限制。",
            "issue": "确认是否在当前证据边界内继续生成策略。",
            "evidence": "请查看 Fact Check 中的支持状态以及未核验 Observation。",
            "required_action": "接受限制后继续；若证据不足则暂缓并返回补充。",
            "severity": "MEDIUM",
            "category": "fact_check",
            "claim_ids": [],
            "source_ids": [],
            "agent_suggestion": "接受限制后继续；若证据不足则暂缓并返回补充。",
            "options": DECISION_OPTIONS,
        })
    resolved = []
    deferred = []
    seen_feedback = set()
    for row in reversed(feedback.get("feedback", [])):
        identity = (row.get("decision_id"), row.get("status"))
        if identity in seen_feedback:
            continue
        seen_feedback.add(identity)
        (resolved if row.get("status") == "RESOLVED" else deferred).append(row)
    return {
        "pending": pending,
        "resolved": list(reversed(resolved)),
        "deferred": list(reversed(deferred)),
        "can_continue": run.get("overall_status") == "AWAITING_HUMAN_REVIEW" and not pending and not deferred,
        "next_stage": "strategy",
        "read_only": bool(run.get("read_only")),
    }
