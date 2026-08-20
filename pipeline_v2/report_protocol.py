"""Structured report blocks, scenarios, lineage and hash consistency helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from jsonschema import Draft202012Validator

from research_platform.report_adapter import enrich_report_data


CLAIM_TAGS = {
    "FACT": "事实",
    "INFERENCE": "推断",
    "RECOMMENDATION": "建议",
    "PENDING": "待验证",
    "PROCESS": "流程记录",
}
FACT_TAG_RE = re.compile(r"【\s*事实(?:\s*[｜|]\s*(F\d+))?\s*】")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_content_blocks(report_model: dict, claims: list[dict], recommendations=()) -> list[dict]:
    claim_map = {row.get("claim_id"): row for row in claims}
    blocks = []
    for index, paragraph in enumerate(report_model.get("paragraphs", []), 1):
        label = str(paragraph.get("label") or "INFERENCE").upper()
        claim_type = {"ANALYSIS": "INFERENCE"}.get(label, label)
        if claim_type not in CLAIM_TAGS:
            claim_type = "INFERENCE"
        linked = [claim_map[value] for value in paragraph.get("claim_ids", []) if value in claim_map]
        fact_ids = [row.get("display_id") or row.get("claim_id") for row in linked]
        observation_ids = list(dict.fromkeys(value for row in linked for value in row.get("observation_ids", [])))
        blocks.append({
            "block_id": f"B{index}",
            "section_id": paragraph.get("section_id") or "body",
            "section_title": paragraph.get("section_title") or paragraph.get("section_id") or "正文",
            "claim_type": claim_type,
            "text": str(paragraph.get("text") or ""),
            "fact_ids": fact_ids,
            "claim_ids": list(paragraph.get("claim_ids") or []),
            "review_ids": list(paragraph.get("review_ids") or []),
            "human_feedback_ids": list(paragraph.get("human_feedback_ids") or []),
            "source_observation_ids": observation_ids,
            "recommendation_ids": list(paragraph.get("recommendation_ids") or []),
        })
    # Structured decision items are canonical too. If the Agent omitted a
    # matching prose paragraph, derive concise report sections so “关键风险”
    # and “关键机会” can never become blank while the structured arrays exist.
    for collection, section_id, section_title in (
        ("risks", "key_risks", "关键风险"),
        ("opportunities", "key_opportunities", "关键机会"),
    ):
        has_section = any(
            section_id in str(block.get("section_id") or "").lower()
            or section_title in str(block.get("section_title") or "")
            for block in blocks
        )
        if has_section:
            continue
        for item in normalize_strategic_items(report_model, claims, collection):
            claim_ids = list(item.get("claim_ids") or [])
            linked = [claim_map[value] for value in claim_ids if value in claim_map]
            blocks.append({
                "block_id": f"B{len(blocks) + 1}",
                "section_id": section_id,
                "section_title": section_title,
                "claim_type": "INFERENCE",
                "text": f"{item['label']}：{item['description']}",
                "fact_ids": list(item.get("source_fact_ids") or []),
                "claim_ids": claim_ids,
                "review_ids": [], "human_feedback_ids": [],
                "source_observation_ids": list(dict.fromkeys(
                    value for row in linked for value in row.get("observation_ids", [])
                )),
                "recommendation_ids": [],
            })
    return blocks


def normalize_strategic_items(report_model: dict, claims: list[dict], collection: str) -> list[dict]:
    """Normalize evidence-linked risks/opportunities without mining Markdown.

    New Strategy responses provide explicit structured collections.  The
    paragraph fallback keeps older V2 artifacts useful and is deliberately
    limited to an already-structured risk/opportunity section.
    """
    claim_map = {row.get("claim_id"): row for row in claims if row.get("claim_id")}
    prefixes = {
        "risks": ("risk", "风险", "風險"),
        "opportunities": ("opportun", "机会", "機會"),
    }
    raw_items = report_model.get(collection)
    if not isinstance(raw_items, list):
        raw_items = []
    if not raw_items:
        for paragraph in report_model.get("paragraphs", []):
            section = " ".join(str(paragraph.get(key) or "") for key in ("section_id", "section_title")).lower()
            if any(token in section for token in prefixes[collection]) and paragraph.get("text"):
                raw_items.append({
                    "label": paragraph.get("section_title") or paragraph.get("section_id"),
                    "description": paragraph.get("text"),
                    "claim_ids": paragraph.get("claim_ids", []),
                    "confidence": "MEDIUM",
                })

    normalized = []
    for index, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            continue
        claim_ids = list(dict.fromkeys(str(value) for value in raw.get("claim_ids", []) if value))
        fact_ids = list(dict.fromkeys(str(value) for value in raw.get("source_fact_ids", []) if value))
        for claim_id in claim_ids:
            claim = claim_map.get(claim_id, {})
            fact_id = claim.get("display_id") or claim.get("claim_id")
            if fact_id and fact_id not in fact_ids:
                fact_ids.append(fact_id)
        label = str(raw.get("label") or raw.get("title") or raw.get("name") or "").strip()
        description = str(raw.get("description") or raw.get("rationale") or raw.get("text") or "").strip()
        if not label or not description:
            continue
        item_id = str(
            raw.get("item_id") or raw.get("risk_id") or raw.get("opportunity_id")
            or f"{'RISK' if collection == 'risks' else 'OPP'}_{index:03d}"
        )
        normalized.append({
            "item_id": item_id,
            "label": label,
            "description": description,
            "severity": raw.get("severity"),
            "timeframe": raw.get("timeframe") or raw.get("time_horizon"),
            "owner": raw.get("owner") or raw.get("responsible_function"),
            "priority": raw.get("priority"),
            "confidence": raw.get("confidence"),
            "claim_ids": claim_ids,
            "source_fact_ids": fact_ids,
        })
    return normalized


def dashboard_report_data(scope: dict, report_data: dict, claims: list[dict]) -> dict:
    """Adapt canonical V2 report data to the dashboard's stable report model."""
    claim_map = {row.get("claim_id"): row for row in claims if row.get("claim_id")}

    def recommendation(raw, index):
        claim_ids = list(raw.get("claim_ids") or [])
        fact_ids = list(raw.get("source_fact_ids") or [])
        for claim_id in claim_ids:
            claim = claim_map.get(claim_id, {})
            fact_id = claim.get("display_id") or claim.get("claim_id")
            if fact_id and fact_id not in fact_ids:
                fact_ids.append(fact_id)
        return {
            **raw,
            "item_id": raw.get("item_id") or raw.get("recommendation_id") or f"REC_{index:03d}",
            "label": raw.get("label") or raw.get("title") or f"Recommendation {index}",
            "description": raw.get("description") or raw.get("rationale") or "",
            "source_fact_ids": fact_ids,
        }

    verification = {"verified": 0, "partial": 0, "unsupported": 0, "superseded": 0}
    for claim in claims:
        status = str(claim.get("verification_status") or "").upper()
        key = {"SUPPORTED": "verified", "PARTIAL": "partial", "UNSUPPORTED": "unsupported", "SUPERSEDED": "superseded"}.get(status)
        if key:
            verification[key] += 1
    conclusion = next((
        row.get("text") for row in report_data.get("content_blocks", [])
        if row.get("claim_type") in {"RECOMMENDATION", "INFERENCE"} and row.get("text")
    ), "")
    return {
        "schema_version": "1.0",
        "scope": {
            "topic": scope.get("topic") or "Strategy report",
            "analysis_type": scope.get("analysis_type_id") or scope.get("analysis_type") or "GENERIC_STRATEGY",
            "industry": scope.get("industry"),
            "geography": scope.get("geography") or "Unspecified",
            "analysis_date": scope.get("analysis_date") or "Unspecified",
            "selected_template": scope.get("selected_template"),
        },
        "executive_summary": conclusion,
        "kpis": list(report_data.get("metrics", [])),
        "time_series": list(report_data.get("time_series", [])),
        "market_segments": list(report_data.get("segments", [])),
        "competitor_comparisons": list(report_data.get("comparisons", [])),
        "risks": list(report_data.get("risks", [])),
        "opportunities": list(report_data.get("opportunities", [])),
        "recommendations": [recommendation(row, index) for index, row in enumerate(report_data.get("recommendations", []), 1)],
        "scenarios": list(report_data.get("scenarios", [])),
        "roadmap": list(report_data.get("roadmap", [])),
        "evidence_summary": verification,
        "data_gaps": list(report_data.get("data_gaps", [])),
    }


def render_content_blocks(title: str, blocks: list[dict]) -> str:
    lines = [f"# {title}", ""]
    section = None
    for block in blocks:
        if block.get("section_id") != section:
            section = block.get("section_id")
            lines.extend([f"## {block.get('section_title') or section}", ""])
        claim_type = block.get("claim_type", "INFERENCE")
        label = CLAIM_TAGS.get(claim_type, "推断")
        suffix = ""
        if claim_type == "FACT" and block.get("fact_ids"):
            first = str(block["fact_ids"][0])
            suffix = f"｜{first}" if first.startswith("F") else ""
        lines.extend([f"【{label}{suffix}】{block.get('text', '')}", ""])
    return "\n".join(lines).rstrip() + "\n"


def normalize_scenarios(scenarios):
    required = ("scenario_id", "label", "base_period", "end_period", "starting_value", "annual_points", "assumptions", "formula", "target_value", "target_gap", "trigger_conditions", "risks", "source_fact_ids", "source_observation_ids", "confidence")
    normalized, errors = [], []
    for index, raw in enumerate(scenarios or []):
        row = dict(raw)
        numeric_fields = {"starting_value", "annual_points", "formula", "target_value", "target_gap"}
        is_qualitative = not any(field in row for field in numeric_fields) and any(
            row.get(field) for field in ("conditions", "implications", "actions", "assumptions", "trigger_conditions")
        )
        if is_qualitative:
            semantic_label = str(row.get("label") or "").upper()
            if row.get("name") and semantic_label in {"FACT", "INFERENCE", "RECOMMENDATION", "PENDING", "PROCESS"}:
                row["claim_type"] = semantic_label
                row["label"] = row["name"]
            row.update({
                "value_type": "QUALITATIVE",
                "base_period": str(row.get("base_period") or ""),
                "end_period": str(row.get("end_period") or ""),
                "starting_value": None,
                "annual_points": [],
                "formula": "",
                "target_value": None,
                "target_gap": None,
                "risks": list(row.get("risks") or []),
                "source_observation_ids": list(row.get("source_observation_ids") or []),
                "confidence": row.get("confidence") or "LOW",
            })
            conditions = row.get("conditions")
            row["assumptions"] = list(row.get("assumptions") or ([conditions] if conditions else []))
            row["trigger_conditions"] = list(row.get("trigger_conditions") or ([conditions] if conditions else []))
            row["source_fact_ids"] = list(row.get("source_fact_ids") or row.get("claim_ids") or [])
            row["points"] = []
        else:
            row["value_type"] = "MODELLED"
            missing = [field for field in required if field not in row]
            if missing:
                errors.append({"rule_id": "SCENARIO_REQUIRED_FIELDS", "location": f"/scenarios/{index}", "reason": f"missing: {', '.join(missing)}"})
        normalized.append(row)
    return normalized, errors


def attach_fact_verification(observations, claims, observation_verifications=()):
    """Attach Fact verification to Observations without mutating canonical data."""
    by_observation = {}
    for claim in claims:
        fact_id = claim.get("display_id") or claim.get("claim_id")
        for observation_id in claim.get("observation_ids", []):
            current = by_observation.setdefault(observation_id, {"fact_ids": [], "statuses": []})
            if fact_id:
                current["fact_ids"].append(fact_id)
            current["statuses"].append(claim.get("verification_status", "NOT_CHECKED"))
    claim_fact_ids = {
        row.get("claim_id"): row.get("display_id") or row.get("claim_id")
        for row in claims if row.get("claim_id")
    }
    for record in observation_verifications or []:
        observation_id = record.get("observation_id")
        if not observation_id:
            continue
        current = by_observation.setdefault(observation_id, {"fact_ids": [], "statuses": []})
        current["statuses"].append(record.get("verification_status", "NOT_CHECKED"))
        current["fact_ids"].extend(
            claim_fact_ids[claim_id]
            for claim_id in record.get("claim_ids", []) if claim_id in claim_fact_ids
        )
    rank = {"UNSUPPORTED": 4, "NOT_CHECKED": 3, "PARTIAL": 2, "SUPPORTED": 1}
    rows = []
    for raw in observations or []:
        row = dict(raw)
        verification = by_observation.get(row.get("observation_id"), {})
        statuses = verification.get("statuses", [])
        row["verification_status"] = max(statuses, key=lambda value: rank.get(value, 9)) if statuses else "NOT_CHECKED"
        row["source_fact_ids"] = list(dict.fromkeys(verification.get("fact_ids", [])))
        rows.append(row)
    return rows


def _structured_views(observations, claims, sufficiency, observation_verifications=()):
    verified = attach_fact_verification(observations, claims, observation_verifications)
    enriched = enrich_report_data(
        {
            "kpis": [], "time_series": [], "market_segments": [],
            "competitor_comparisons": [], "data_gaps": [],
        },
        verified,
        sufficiency or {"datasets": []},
    )
    return {
        "metrics": enriched.get("kpis", []),
        "time_series": enriched.get("time_series", []),
        "comparisons": enriched.get("competitor_comparisons", []),
        "segments": enriched.get("market_segments", []),
        "data_gaps": enriched.get("data_gaps", []),
        "meta": enriched.get("_meta", {}),
    }


def _recommendation_roadmap(recommendations, claims):
    claim_map = {row.get("claim_id"): row for row in claims if row.get("claim_id")}
    roadmap = []
    for index, row in enumerate(recommendations or [], 1):
        fact_ids = list(row.get("source_fact_ids") or [])
        for claim_id in row.get("claim_ids") or []:
            claim = claim_map.get(claim_id, {})
            fact_id = claim.get("display_id") or claim.get("claim_id")
            if fact_id and fact_id not in fact_ids:
                fact_ids.append(fact_id)
        roadmap.append({
            "item_id": row.get("recommendation_id") or row.get("item_id") or f"ROADMAP_{index:03d}",
            "label": row.get("title") or row.get("label") or f"行动 {index}",
            "description": row.get("rationale") or row.get("description") or "",
            "start": row.get("start") or None,
            "end": row.get("end") or row.get("time_horizon") or None,
            "status": row.get("status") or "PLANNED",
            "owner": row.get("responsible_function") or row.get("owner"),
            "source_fact_ids": fact_ids,
        })
    return roadmap


def _visual_availability(payload, sufficiency):
    coverage = list((sufficiency or {}).get("datasets") or [])
    observed = sum(int(row.get("observation_count") or 0) for row in coverage)
    gap_ids = [
        gap.get("gap_id") for row in coverage if row.get("status") != "PASS"
        for gap in row.get("gaps") or [] if gap.get("gap_id")
    ]
    labels = {
        "metrics": "核心指标", "time_series": "趋势图", "comparisons": "竞品比较",
        "segments": "构成分析", "matrices": "矩阵分析", "geographies": "地理分布",
        "risks": "关键风险", "opportunities": "关键机会",
        "recommendations": "战略建议", "roadmap": "执行路线图", "scenarios": "情景分析",
    }
    result = {}
    for collection, label in labels.items():
        exported = len(payload.get(collection) or [])
        if exported:
            status, code = "AVAILABLE", "STRUCTURED_DATA_AVAILABLE"
            reason = f"{label}已有 {exported} 组可追溯结构化数据。"
            action = "查看图表并结合证据编号解读。"
        elif observed:
            status, code = "PARTIAL", "INSUFFICIENT_VISUAL_DIMENSIONS"
            reason = f"已采集 {observed} 条Observation，但尚不满足{label}所需的数值、口径、期间或核验维度。"
            action = "按Data Coverage缺口定向补搜，或在当前版本保留文字化证据说明。"
        else:
            status, code = "UNAVAILABLE", "NO_VERIFIED_OBSERVATIONS"
            reason = f"当前没有可用于{label}的已核验证据。"
            action = "先完成对应数据集的定向采集与Fact Check。"
        result[collection] = {
            "status": status, "reason_code": code, "reason": reason,
            "observed_count": observed, "exported_count": exported,
            "gap_ids": gap_ids, "search_stop_reason": (sufficiency or {}).get("search_stop_reason") or "",
            "required_action": action,
        }
    return result


def report_data_payload(
    report_model, claims, recommendations, final_markdown, *, run_id, revision_id,
    observations=(), sufficiency=None, observation_verifications=(),
):
    blocks = build_content_blocks(report_model, claims, recommendations)
    scenarios, scenario_errors = normalize_scenarios(report_model.get("scenarios", []))
    views = _structured_views(observations, claims, sufficiency, observation_verifications)
    payload = {
        "schema_version": "2.0",
        "meta": {"run_id": run_id, "revision_id": revision_id, "final_report_sha256": sha256_text(final_markdown)},
        "content_blocks": blocks,
        "metrics": views["metrics"],
        "time_series": views["time_series"],
        "comparisons": views["comparisons"],
        "segments": views["segments"],
        "data_gaps": views["data_gaps"],
        "risks": normalize_strategic_items(report_model, claims, "risks"),
        "opportunities": normalize_strategic_items(report_model, claims, "opportunities"),
        "recommendations": list(recommendations),
        "roadmap": _recommendation_roadmap(recommendations, claims),
        "matrices": [], "geographies": [],
        "scenarios": scenarios,
        "validation_errors": scenario_errors,
        "_meta": {
            **views["meta"],
            "observation_ids": [row.get("observation_id") for row in observations if row.get("observation_id")],
        },
    }
    payload["visual_availability"] = _visual_availability(payload, sufficiency)
    return payload


def hash_consistent(final_markdown: str, report_data: dict) -> bool:
    return report_data.get("meta", {}).get("final_report_sha256") == sha256_text(final_markdown)


def hash_file_consistent(path, report_data: dict) -> bool:
    meta = report_data.get("meta") or report_data.get("_meta") or {}
    return meta.get("final_report_sha256") == sha256_file(path)


def validate_report_data(report_data: dict) -> list[str]:
    schema_path = Path(__file__).with_name("schemas") / "report_data_v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [
        f"/{'/'.join(map(str, error.path))}: {error.message}"
        for error in sorted(Draft202012Validator(schema).iter_errors(report_data), key=lambda item: list(item.path))
    ]
