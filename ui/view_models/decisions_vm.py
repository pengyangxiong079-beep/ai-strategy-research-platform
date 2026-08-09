from pathlib import Path
from pipeline_v2.ids import stable_id
from ui.repository import read_json


def decisions_view_model(run):
    folder = Path(run["folder"])
    review = read_json(folder / "review/review_issues.json", {"issues": []})
    feedback = read_json(folder / "human/feedback.json", {"feedback": []})
    resolved_ids = {x.get("decision_id") for x in feedback.get("feedback", []) if x.get("status") == "RESOLVED"}
    pending = []
    for item in review.get("issues", []):
        decision_id = stable_id("decision", run.get("run_id"), item.get("review_id"))
        if decision_id not in resolved_ids and item.get("status", "OPEN") != "RESOLVED":
            pending.append({"decision_id": decision_id, "source_stage": "review", "title": item.get("title") or item.get("reason") or "审查事项", "why": item.get("reason", "需要用户确认处理方式"), "claim_id": item.get("claim_id"), "source_ids": item.get("source_ids", []), "agent_suggestion": item.get("suggested_action", ""), "options": ["接受", "要求修改", "删除结论", "降级为推断", "要求补搜", "暂缓"]})
    if run.get("overall_status") == "AWAITING_HUMAN_REVIEW" and not pending and not feedback.get("feedback"):
        pending.append({"decision_id": stable_id("decision", run.get("run_id"), "overall-approval"), "source_stage": "fact_check", "title": "确认事实核验结果", "why": "Strategy开始前需要确认核验结论和数据限制。", "claim_id": None, "source_ids": [], "agent_suggestion": "接受后继续Strategy；如证据不足可要求补搜。", "options": ["接受", "要求修改", "删除结论", "降级为推断", "要求补搜", "暂缓"]})
    return {"pending": pending, "resolved": feedback.get("feedback", []), "can_continue": run.get("overall_status") == "AWAITING_HUMAN_REVIEW" and not pending, "next_stage": "strategy", "read_only": bool(run.get("read_only"))}

