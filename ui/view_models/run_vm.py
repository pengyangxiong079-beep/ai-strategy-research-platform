from pipeline_v2.model import STAGE_ORDER
from pipeline_v2.service import PipelineV2Service


def overview_view_model(run):
    stages = run.get("stages", {})
    complete = sum((stages.get(x) or {}).get("status") in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} for x in STAGE_ORDER)
    action = PipelineV2Service.primary_action(run.get("overall_status"))
    issues = []
    quality = run.get("quality_summary", {})
    if quality.get("blocking"):
        issues.append({"title": "存在阻塞性质量问题", "count": quality["blocking"]})
    if quality.get("warnings"):
        issues.append({"title": "存在质量警告", "count": quality["warnings"]})
    events = list(reversed(run.get("events", [])))[:5]
    summaries = [
        {"label": "当前阶段", "value": run.get("current_stage", "—")},
        {"label": "数据准备度", "value": (stages.get("data") or {}).get("validation_status", "PENDING")},
        {"label": "质量状态", "value": quality.get("status", "PENDING")},
        {"label": "Revision", "value": run.get("revision_id", "rev_000")},
    ]
    return {**run, "progress": complete / len(STAGE_ORDER), "primary_action": action, "summary_metrics": summaries, "recent_activity": events, "key_issues": issues[:3]}

