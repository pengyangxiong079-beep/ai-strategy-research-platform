"""Deterministic Markdown renderers fed only by structured objects."""

from __future__ import annotations

from .ids import assign_display_ids
from .review import render_review_notes


def source_link(source):
    title = source.get("title") or source.get("publisher") or source.get("source_id") or "来源"
    url = source.get("url") or ""
    return f"[{title}]({url})" if url else title


def render_fact_check(claims, sources):
    source_map = {x.get("source_id"): x for x in sources}
    lines = ["# Fact Check", ""]
    for claim in assign_display_ids([x for x in claims if x.get("status", "ACTIVE") == "ACTIVE"], "F"):
        linked = [source_map[x] for x in claim.get("source_ids", []) if x in source_map]
        lines.extend([
            f"### {claim['display_id']}", "",
            f"- 原始事实：{claim.get('text', '')}",
            f"- 核验结果：{claim.get('verification_status', 'NOT_CHECKED')}",
            f"- temporal_status：{claim.get('temporal_status', 'UNKNOWN')}",
            f"- 来源：{'；'.join(source_link(x) for x in linked) or 'N/A'}",
            f"- source_grade：{claim.get('source_grade_max') or 'N/A'}", "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def render_research(sections, claims):
    """Render human-readable research notes from structured sections only."""
    claim_map = {x.get("claim_id"): x for x in claims}
    lines = ["# Research brief", ""]
    for section in sections:
        lines.extend([f"## {section.get('title') or section.get('section_id') or 'Section'}", ""])
        if section.get("analysis"):
            lines.extend([f"【分析】{section['analysis']}", ""])
        for claim_id in section.get("claim_ids", []):
            if claim_id in claim_map:
                lines.extend([f"【事实】{claim_map[claim_id].get('text', '')}", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_review(issues):
    lines = ["# Review notes", ""]
    if not issues:
        lines.extend(["未发现阻塞性结构化审查问题。", ""])
    for item in issues:
        lines.extend([f"## {item.get('review_id') or 'Review issue'}", "", item.get("reason") or item.get("title") or "", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_report(report_model, claims, sources, recommendations=()):
    claim_map = {x.get("claim_id"): x for x in claims}
    source_map = {x.get("source_id"): x for x in sources}
    recommendation_map = {x.get("recommendation_id"): x for x in recommendations}
    lines = [f"# {report_model.get('title', '战略研究报告')}", ""]
    current_section = None
    for paragraph in report_model.get("paragraphs", []):
        section = paragraph.get("section_id") or "正文"
        if section != current_section:
            lines.extend([f"## {paragraph.get('section_title') or section}", ""])
            current_section = section
        label = paragraph.get("label", "ANALYSIS")
        text = paragraph.get("text", "")
        linked_claims = [claim_map[x] for x in paragraph.get("claim_ids", []) if x in claim_map]
        linked_sources = []
        for claim in linked_claims:
            linked_sources.extend(source_map[x] for x in claim.get("source_ids", []) if x in source_map)
        recs = [recommendation_map[x] for x in paragraph.get("recommendation_ids", []) if x in recommendation_map]
        if recs and not text:
            text = "；".join(x.get("title", "") for x in recs)
        unique_sources = list({x.get("source_id"): x for x in linked_sources}.values())
        provenance = "；".join(source_link(x) for x in unique_sources)
        lines.append(f"【{label}】{text}" + (f" {provenance}" if provenance else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def markdown_matches_model(markdown, report_model):
    return all(str(p.get("text") or "").strip() in markdown for p in report_model.get("paragraphs", []))


# Keep the human-readable projection strictly downstream of canonical JSON.
def render_review(issues):
    return render_review_notes(issues)
