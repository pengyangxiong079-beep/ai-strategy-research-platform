def project_view_model(runs, query="", status="全部", analysis_type="全部"):
    query = str(query or "").lower()
    filtered = []
    for run in runs:
        if query and query not in f"{run.get('topic','')} {run.get('run_id','')}".lower():
            continue
        if status != "全部" and run.get("overall_status") != status:
            continue
        if analysis_type != "全部" and run.get("normalized_analysis_type") != analysis_type:
            continue
        filtered.append({
            "project_id": run.get("project_id"), "run_id": run.get("run_id"), "项目": run.get("topic"),
            "分析类型": run.get("normalized_analysis_type"), "行业": run.get("industry"), "地区": run.get("geography", ""),
            "当前阶段": run.get("current_stage"), "状态": run.get("overall_status"),
            "质量": run.get("quality_summary", {}).get("status", "UNKNOWN"), "版本": run.get("revision_id"),
            "更新时间": run.get("updated_at"), "Legacy": bool(run.get("legacy")), "folder": run.get("folder"),
        })
    return {"projects": filtered, "empty": not filtered, "count": len(filtered)}

