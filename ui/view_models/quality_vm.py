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
    }
