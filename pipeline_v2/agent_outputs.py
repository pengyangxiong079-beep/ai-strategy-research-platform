"""Strict tagged JSON extraction for Agent stage contracts."""

from __future__ import annotations

import json
from pathlib import Path
import re

from .ids import stable_id
from .contracts import validate_stage
from .service import PipelineV2Service
from .renderer import render_report
from .model import load_run_state
from .envelope import AgentOutputError, EXPECTED_ARTIFACTS


def _json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _record(folder, stage, payload, context=None):
    result = validate_stage(stage, payload, context or {})
    PipelineV2Service(Path(folder).parent).record_gate_result(folder, stage, result)
    return result


def extract_json_block(text, tag):
    match = re.search(rf"<{re.escape(tag)}>\s*(.*?)\s*</{re.escape(tag)}>", str(text), re.I | re.S)
    if not match:
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", match.group(1).strip(), flags=re.I)
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError):
        return None


def extract_text_block(text, tag):
    match = re.search(rf"<{re.escape(tag)}>\s*(.*?)\s*</{re.escape(tag)}>", str(text), re.I | re.S)
    return match.group(1).strip() if match else None


def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reject_tagged_output_for_strict_v2(folder, stage, raw):
    state = load_run_state(folder)
    if state and state.get("configuration", {}).get("strict_structured_output"):
        attempt = int(state.get("stages", {}).get(stage, {}).get("attempt", 0)) + 1
        raise AgentOutputError(
            "AGENT_OUTPUT_NOT_STRUCTURED", stage, attempt, str(raw)[:500],
            ["严格V2不接受标签JSON、Markdown或从正文提取的对象"],
            list(EXPECTED_ARTIFACTS.get(stage, ())),
        )


def persist_research_model(folder, raw):
    _reject_tagged_output_for_strict_v2(folder, "research", raw)
    payload = extract_json_block(raw, "research_model_json")
    if not payload:
        return None
    claims = []
    for item in payload.get("claims", []):
        item = dict(item)
        item["claim_id"] = item.get("claim_id") or stable_id("claim", item.get("text"), item.get("scope"))
        item.setdefault("display_id", None); item.setdefault("parent_claim_id", None); item.setdefault("status", "ACTIVE")
        claims.append(item)
    _write(Path(folder) / "research/claims.json", {"schema_version": "2.0", "claims": claims})
    _write(Path(folder) / "research/research_model.json", {**payload, "schema_version": "2.0", "claims": claims})
    observations = _json(Path(folder) / "data/observations.json", {"observations": []}).get("observations", [])
    sources = _json(Path(folder) / "data/source_registry.json", {"sources": []}).get("sources", [])
    _record(folder, "research", {"claims": claims}, {"observations": observations, "sources": sources})
    return payload


def persist_review_model(folder, raw):
    _reject_tagged_output_for_strict_v2(folder, "review", raw)
    payload = extract_json_block(raw, "review_issues_json")
    if not payload:
        return None
    from .review import render_review_notes, validate_review_notes
    issues = [dict(item) for item in payload.get("issues", [])]
    errors = validate_review_notes(issues)
    if errors:
        _record(folder, "review", {"issues": issues})
        return None
    canonical = {"schema_version": "2.0", "issues": issues}
    _write(Path(folder) / "review/review_notes.json", canonical)
    _write(Path(folder) / "review/review_issues.json", canonical)
    _write(Path(folder) / "02_review_notes.json", canonical)
    rendered = Path(folder) / "rendered/02_review_notes.md"
    rendered.parent.mkdir(parents=True, exist_ok=True)
    rendered.write_text(render_review_notes(issues), encoding="utf-8")
    _record(folder, "review", {"issues": issues})
    return payload


def persist_fact_model(folder, raw):
    _reject_tagged_output_for_strict_v2(folder, "fact_check", raw)
    payload = extract_json_block(raw, "verified_claims_json")
    if payload:
        _write(Path(folder) / "fact_check/verified_claims.json", {**payload, "schema_version": "2.0"})
        sources = _json(Path(folder) / "data/source_registry.json", {"sources": []}).get("sources", [])
        _record(folder, "fact_check", payload, {"sources": sources})
    return payload


def persist_strategy_model(folder, raw):
    _reject_tagged_output_for_strict_v2(folder, "strategy", raw)
    payload = extract_json_block(raw, "strategy_model_json")
    if not payload:
        return None
    recommendations = []
    for item in payload.get("recommendations", []):
        item = dict(item)
        item["recommendation_id"] = item.get("recommendation_id") or stable_id("recommendation", item.get("title"), item.get("claim_ids"))
        recommendations.append(item)
    _write(Path(folder) / "strategy/recommendations.json", {"schema_version": "2.0", "recommendations": recommendations})
    _write(Path(folder) / "strategy/report_model.json", {**payload.get("report_model", {}), "schema_version": "2.0"})
    claims = _json(Path(folder) / "fact_check/verified_claims.json", {"claims": []}).get("claims", [])
    _record(folder, "strategy", {"recommendations": recommendations}, {"claims": claims})
    return payload


def render_persisted_report(folder, required_sections=()):
    """Render Final deterministically when the structured report contract passes."""
    folder = Path(folder)
    report_model = _json(folder / "strategy/report_model.json", {})
    claims = _json(folder / "fact_check/verified_claims.json", {"claims": []}).get("claims", [])
    sources = _json(folder / "data/source_registry.json", {"sources": []}).get("sources", [])
    recommendations = _json(folder / "strategy/recommendations.json", {"recommendations": []}).get("recommendations", [])
    if not report_model.get("paragraphs"):
        return None
    gate = validate_stage("report", report_model, {"claims": claims, "required_sections": list(required_sections)})
    PipelineV2Service(folder.parent).record_gate_result(folder, "report", gate)
    if not gate.can_continue:
        return None
    markdown = render_report(report_model, claims, sources, recommendations)
    rendered = folder / "rendered/04_final_report.md"
    rendered.parent.mkdir(parents=True, exist_ok=True)
    rendered.write_text(markdown, encoding="utf-8")
    (folder / "04_final_report.md").write_text(markdown, encoding="utf-8")
    return markdown
