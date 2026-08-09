from pathlib import Path
from ui.repository import read_json, read_text


def results_view_model(run):
    folder = Path(run["folder"])
    report_data = read_json(folder / "04_report_data.json", {})
    final_path = folder / "rendered/04_final_report.md" if (folder / "rendered/04_final_report.md").is_file() else folder / "04_final_report.md"
    level2 = [
        ("Research Brief", "rendered/01_research_brief.md", "01_research_brief.md"),
        ("Review Notes", "rendered/02_review_notes.md", "02_review_notes.md"),
        ("Fact Check", "rendered/03_fact_check.md", "03_fact_check.md"),
        ("Human Feedback", "rendered/03_human_feedback.md", "03_human_feedback.md"),
        ("Quality Check", "rendered/05_quality_check.md", "05_quality_check.md"),
    ]
    supporting = []
    for label, canonical, legacy in level2:
        path = folder / canonical if (folder / canonical).is_file() else folder / legacy
        if path.is_file():
            supporting.append({"label": label, "path": str(path), "content": read_text(path)})
    dashboard = folder / "dashboard/dashboard.html"
    if not dashboard.is_file():
        dashboard = folder / "dashboard" / "dashboard.html"
    return {
        "available": final_path.is_file(), "final_path": str(final_path), "final_markdown": read_text(final_path),
        "report_data": report_data, "executive_summary": report_data.get("executive_summary", ""),
        "opportunities": report_data.get("opportunities", [])[:3], "risks": report_data.get("risks", [])[:3],
        "recommendations": report_data.get("recommendations", [])[:4], "data_gaps": report_data.get("data_gaps", [])[:3],
        "supporting": supporting, "dashboard_path": str(dashboard) if dashboard.is_file() else None,
        "status": run.get("overall_status"), "revision": run.get("revision_id"), "read_only": bool(run.get("read_only")),
    }

