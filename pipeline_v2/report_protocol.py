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
    return blocks


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
        row["value_type"] = "MODELLED"
        missing = [field for field in required if field not in row]
        if missing:
            errors.append({"rule_id": "SCENARIO_REQUIRED_FIELDS", "location": f"/scenarios/{index}", "reason": f"missing: {', '.join(missing)}"})
        normalized.append(row)
    return normalized, errors


def attach_fact_verification(observations, claims):
    """Attach Fact verification to Observations without mutating canonical data."""
    by_observation = {}
    for claim in claims:
        fact_id = claim.get("display_id") or claim.get("claim_id")
        for observation_id in claim.get("observation_ids", []):
            current = by_observation.setdefault(observation_id, {"fact_ids": [], "statuses": []})
            if fact_id:
                current["fact_ids"].append(fact_id)
            current["statuses"].append(claim.get("verification_status", "NOT_CHECKED"))
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


def _structured_views(observations, claims, sufficiency):
    verified = attach_fact_verification(observations, claims)
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


def report_data_payload(
    report_model, claims, recommendations, final_markdown, *, run_id, revision_id,
    observations=(), sufficiency=None,
):
    blocks = build_content_blocks(report_model, claims, recommendations)
    scenarios, scenario_errors = normalize_scenarios(report_model.get("scenarios", []))
    views = _structured_views(observations, claims, sufficiency) if observations else {
        "metrics": [], "time_series": [], "comparisons": [], "segments": [],
        "data_gaps": [], "meta": {},
    }
    return {
        "schema_version": "2.0",
        "meta": {"run_id": run_id, "revision_id": revision_id, "final_report_sha256": sha256_text(final_markdown)},
        "content_blocks": blocks,
        "metrics": views["metrics"],
        "time_series": views["time_series"],
        "comparisons": views["comparisons"],
        "segments": views["segments"],
        "data_gaps": views["data_gaps"],
        "recommendations": list(recommendations),
        "scenarios": scenarios,
        "validation_errors": scenario_errors,
        "_meta": {
            **views["meta"],
            "observation_ids": [row.get("observation_id") for row in observations if row.get("observation_id")],
        },
    }


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
