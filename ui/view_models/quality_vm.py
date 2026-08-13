from pathlib import Path
from ui.repository import read_json
from pipeline_v2.quality import aggregate_quality


def quality_view_model(run):
    folder = Path(run["folder"])
    sufficiency = read_json(folder / "data/sufficiency.json", {"datasets": []})
    sources = read_json(folder / "data/source_registry.json", {"sources": []})
    quality = read_json(folder / "quality/issues.json", {})
    if not quality.get("issues"):
        legacy = read_json(folder / "05_quality_check.json", {})
        quality = {"issues": legacy.get("issues", []) or run.get("quality_issues", [])}
    claims = read_json(folder / "research/claims.json", {"claims": []})
    report_data = read_json(folder / "04_report_data.json", {})
    issues = quality.get("issues", [])
    blocking = [x for x in issues if x.get("severity") == "ERROR" or x.get("status") == "FAIL"]
    warnings = [x for x in issues if x not in blocking and not x.get("resolved")]
    resolved = [x for x in issues if x.get("resolved")]
    aggregation = aggregate_quality(issues)
    evidence = report_data.get("evidence_summary", {})
    supported = int(evidence.get("verified", evidence.get("supported", 0)) or 0)
    evidence_total = sum(int(evidence.get(key, 0) or 0) for key in ("verified", "partial", "unsupported", "superseded"))
    targeted = read_json(folder / "data/targeted_gap_search.json", {})
    settings = read_json(Path(".workspace/settings.json"), {})
    gap_limit = max(0, min(2, int(settings.get("gap_limit", 2) or 0)))
    dataset_status = {
        row.get("dataset_id"): row.get("status")
        for row in sufficiency.get("datasets", []) if isinstance(row, dict)
    }
    candidates, seen = [], set()
    for raw in sufficiency.get("gap_search_candidates", []):
        if not isinstance(raw, dict) or raw.get("priority") not in {"CRITICAL", "IMPORTANT"}:
            continue
        if dataset_status.get(raw.get("dataset_id")) == "PASS":
            continue
        identity = (raw.get("gap_id"), raw.get("dataset_id"))
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(raw)
    base = Path(run.get("base_folder") or run["folder"])
    historical_attempts = sum(
        1 for marker_path in (base / "revisions").glob("rev_*/data/targeted_gap_search.json")
        if read_json(marker_path, {}).get("status") in {"RUNNING", "COMPLETED"}
    )
    attempts = max(historical_attempts, int(targeted.get("attempt_count") or 0) if targeted.get("status") in {"RUNNING", "COMPLETED"} else 0)
    agent_running = any(
        row.get("status") == "RUNNING"
        for row in run.get("stages", {}).values()
    )
    if agent_running:
        gap_blocker = "当前已有 Agent 阶段运行中，请等待其完成。"
    elif attempts >= gap_limit:
        gap_blocker = f"已达到自动补搜上限（{gap_limit} 轮）；请接受证据限制或创建人工修订。"
    elif not candidates:
        gap_blocker = "当前没有可自动补搜的 CRITICAL/IMPORTANT 缺口。"
    else:
        gap_blocker = ""
    return {
        "datasets": sufficiency.get("datasets", []), "sources": sources.get("sources", []),
        "blocking": blocking, "warnings": warnings, "resolved": resolved,
        "claims": claims.get("claims", []), "raw_issues": aggregation["raw_issues"],
        "root_causes": aggregation["root_causes"], "affected_items": aggregation["affected_items"],
        "automatic_fixability": aggregation["automatic_fixability"],
        "recommended_revision_type": aggregation["recommended_revision_type"],
        "read_only": bool(run.get("read_only")),
        "decision_gaps": report_data.get("data_gaps", []),
        "evidence_summary": evidence,
        "support_rate": supported / evidence_total if evidence_total else None,
        "targeted_gap_search": {
            "targets": candidates, "target_count": len(candidates),
            "query_count": sum(len(row.get("recommended_queries") or []) for row in candidates),
            "attempt_count": attempts, "limit": gap_limit,
            "status": targeted.get("status") or "NOT_STARTED",
            "remaining_dataset_ids": targeted.get("remaining_dataset_ids", []),
            "can_start": bool(candidates) and attempts < gap_limit and not agent_running,
            "blocker": gap_blocker,
            "agent_stages": ["Data", "Research", "Review", "Fact Check"],
        },
    }
