from pathlib import Path

from pipeline_v2.ids import stable_id
from ui.repository import read_json


DECISION_OPTIONS = [
    "接受该限制并继续",
    "排除相关结论",
    "降级为推断",
    "暂缓，返回补充或修正",
]


def _decision_from_review(run_id, item, sufficiency=None):
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
    decision = {
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
    if item.get("category") == "sufficiency":
        text = " ".join(str(item.get(key) or "") for key in ("issue", "evidence", "required_action"))
        matching = []
        for dataset in (sufficiency or {}).get("datasets", []):
            if not isinstance(dataset, dict):
                continue
            dataset_id = str(dataset.get("dataset_id") or "")
            for gap in dataset.get("gaps") or []:
                if not isinstance(gap, dict):
                    continue
                gap_id = str(gap.get("gap_id") or "")
                if (gap_id and gap_id in text) or (dataset_id and dataset_id in text):
                    matching.append({**gap, "dataset_id": dataset_id, "priority": dataset.get("priority")})
        if matching:
            queries = []
            for gap in matching:
                for raw in gap.get("recommended_queries") or []:
                    query = (raw.get("query_text") or raw.get("query")) if isinstance(raw, dict) else str(raw)
                    if query and query not in queries:
                        queries.append(query)
            datasets = ", ".join(dict.fromkeys(gap["dataset_id"] for gap in matching))
            decision["evidence"] = f"{decision['evidence']}\n\n具体缺口数据集：{datasets}。"
            if queries:
                query_text = "；".join(queries)
                decision["required_action"] = f"{decision['required_action']}\n\n建议定向查询：{query_text}"
            decision["gap_details"] = matching
    return decision


def decisions_view_model(run):
    folder = Path(run["folder"])
    review = read_json(folder / "review/review_issues.json", {"issues": []})
    sufficiency = read_json(folder / "data/sufficiency.json", {"datasets": []})
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
        decision = _decision_from_review(run.get("run_id"), item, sufficiency)
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
