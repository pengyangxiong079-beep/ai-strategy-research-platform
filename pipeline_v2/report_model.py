"""Safe local normalization for structured report semantics."""

from __future__ import annotations


PROCESS_SECTION_TOKENS = (
    "human feedback", "review问题处理", "review issue", "人工反馈", "人工决策",
)


def normalize_report_model(model):
    """Relabel workflow provenance without weakening external FACT lineage."""
    result = dict(model or {})
    paragraphs = []
    for raw in result.get("paragraphs", []):
        row = dict(raw)
        section = str(row.get("section_id") or row.get("section_title") or "").lower()
        text = str(row.get("text") or "").lower()
        is_process_provenance = (
            any(token in section for token in PROCESS_SECTION_TOKENS)
            and any(token in text for token in ("feedback", "resolved", "接受", "决定", "decision"))
        )
        if row.get("label") == "FACT" and not row.get("claim_ids") and is_process_provenance:
            row["label"] = "PROCESS"
            row["normalized_by"] = "PipelineV2Orchestrator"
            row["normalization_reason"] = "Human decision provenance is not an external research fact"
        paragraphs.append(row)
    result["paragraphs"] = paragraphs
    return result
