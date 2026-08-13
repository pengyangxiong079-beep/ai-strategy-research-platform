"""Deterministic shift-left gates for canonical Pipeline V2 artifacts."""

from __future__ import annotations

from .base import issue, result
from pipeline_v2.review import validate_review_notes


def scope_gate(payload, context):
    del context
    errors = []
    for field in ("analysis_type_id", "topic", "geography", "analysis_date", "required_sections"):
        if not payload.get(field):
            errors.append(issue(f"SCOPE_REQUIRED_{field.upper()}", f"Scope is missing {field}", stage="scope", artifact="00_analysis_scope.json", location=f"/{field}", expected="non-empty"))
    if not isinstance(payload.get("focus_questions", []), list) or not isinstance(payload.get("competitors", []), list):
        errors.append(issue("SCOPE_ARRAY_FIELDS", "focus_questions and competitors must be arrays", stage="scope", artifact="00_analysis_scope.json", repair_type="LOCAL_REPAIRABLE"))
    return result(errors)


def data_gate(payload, context):
    sources = {row.get("source_id"): row for row in context.get("sources", [])}
    observations = payload.get("observations", [])
    coverage = context.get("sufficiency", {})
    errors, warnings = [], []
    declared_count = coverage.get("observation_count")
    if declared_count is not None and int(declared_count) != len(observations):
        errors.append(issue("DATA_COVERAGE_COUNT_MISMATCH", "Coverage observation_count must equal canonical observations.json count", stage="data", artifact="data/data_coverage.json", expected=len(observations), actual=declared_count, repair_type="STAGE_RETRY"))
    if declared_count and not observations:
        errors.append(issue("DATA_COVERAGE_WITHOUT_OBSERVATIONS", "Coverage cannot be positive when observations.json is empty", stage="data", artifact="data/data_coverage.json", repair_type="STAGE_RETRY"))
    for index, row in enumerate(observations):
        if not row.get("source_id") or row.get("source_id") not in sources:
            errors.append(issue("DATA_SOURCE_LINK", "Observation must link to Source Registry", stage="data", artifact="data/observations.json", location=f"/observations/{index}/source_id", entity_id=row.get("observation_id", ""), repair_type="UPSTREAM_DATA_REQUIRED"))
    for dataset in coverage.get("datasets", []):
        if dataset.get("priority") == "CRITICAL" and dataset.get("status") == "INSUFFICIENT":
            dataset_id = dataset.get("dataset_id", "")
            gaps = dataset.get("gaps") or []
            gap_text = "; ".join(
                str(row.get("reason") or row.get("missing_field") or row.get("description") or row)
                for row in gaps
            ) or "No gap details supplied"
            errors.append(issue(
                "DATA_CRITICAL_INSUFFICIENT",
                f"CRITICAL dataset {dataset_id} is insufficient: {gap_text}",
                stage="data", artifact="data/data_coverage.json",
                location=f"/datasets/{dataset_id}", entity_id=dataset_id,
                expected={"status": "PASS"},
                actual={"status": dataset.get("status"), "observation_count": dataset.get("observation_count", 0), "gaps": gaps},
                repair_type="UPSTREAM_DATA_REQUIRED",
            ))
        elif dataset.get("priority") == "OPTIONAL" and dataset.get("status") != "PASS":
            warnings.append(issue("DATA_OPTIONAL_INSUFFICIENT", "OPTIONAL dataset is insufficient and does not block the pipeline", stage="data", artifact="data/data_coverage.json", entity_id=dataset.get("dataset_id", ""), repair_type="HUMAN_REQUIRED", severity="WARNING"))
    return result(errors, warnings)


def research_gate(payload, context):
    observations = {row.get("observation_id") for row in context.get("observations", [])}
    sources = {row.get("source_id") for row in context.get("sources", [])}
    errors = []
    for index, claim in enumerate(payload.get("claims", [])):
        if claim.get("claim_type") == "FACT":
            if not claim.get("source_ids") or any(value not in sources for value in claim.get("source_ids", [])):
                errors.append(issue("RESEARCH_FACT_SOURCE", "FACT must link to registered sources", stage="research", artifact="research/claims.json", location=f"/claims/{index}/source_ids", entity_id=claim.get("claim_id", "")))
            if any(value not in observations for value in claim.get("observation_ids", [])):
                errors.append(issue("RESEARCH_FACT_OBSERVATION", "Claim references a missing Observation", stage="research", artifact="research/claims.json", location=f"/claims/{index}/observation_ids", entity_id=claim.get("claim_id", "")))
        if claim.get("atomicity_status") != "ATOMIC":
            errors.append(issue("RESEARCH_ATOMICITY", "Claim must be atomic", stage="research", artifact="research/claims.json", entity_id=claim.get("claim_id", ""), repair_type="STAGE_RETRY"))
    return result(errors)


def review_gate(payload, context):
    del context
    errors = [issue(row["rule_id"], row["reason"], stage="review", artifact="02_review_notes.json", location=row["location"], repair_type="STAGE_RETRY") for row in validate_review_notes(payload.get("issues", []))]
    return result(errors)


def fact_check_gate(payload, context):
    sources = {row.get("source_id"): row for row in context.get("sources", [])}
    observations = {row.get("observation_id") for row in context.get("observations", [])}
    errors = []
    ledger = payload.get("observation_verifications", [])
    linked_observations = {row.get("observation_id") for row in ledger if row.get("observation_id")}
    if observations and linked_observations != observations:
        errors.append(issue("FACT_OBSERVATION_COVERAGE", "Fact Check must account for every canonical Observation, including NOT_CHECKED records", stage="fact_check", artifact="03_fact_check.json", expected=sorted(observations), actual=sorted(linked_observations), repair_type="STAGE_RETRY"))
    if "research_claims" in context:
        research_claim_ids = {row.get("claim_id") for row in context.get("research_claims", []) if row.get("claim_id")}
        verified_claim_ids = {row.get("claim_id") for row in payload.get("claims", []) if row.get("claim_id")}
        if research_claim_ids != verified_claim_ids:
            errors.append(issue("FACT_CLAIM_COVERAGE", "Fact Check must account for every research Claim", stage="fact_check", artifact="fact_check/verified_claims.json", expected=sorted(research_claim_ids), actual=sorted(verified_claim_ids), repair_type="STAGE_RETRY"))
    for index, record in enumerate(ledger):
        if record.get("observation_id") not in observations:
            errors.append(issue("FACT_OBSERVATION_LINK", "Fact Check references a missing Observation", stage="fact_check", artifact="03_fact_check.json", location=f"/observation_verifications/{index}/observation_id", entity_id=record.get("observation_id", ""), repair_type="STAGE_RETRY"))
    for index, claim in enumerate(payload.get("claims", [])):
        if claim.get("verification_status") == "SUPPORTED":
            linked = [sources.get(value) for value in claim.get("source_ids", [])]
            grades = {row.get("source_grade") for row in linked if row}
            if not linked or not grades.intersection({"GRADE_A", "GRADE_B", "GRADE_C"}):
                eligible = any(row.get("source_grade") in {"GRADE_A", "GRADE_B", "GRADE_C"} for row in sources.values())
                errors.append(issue("FACT_VERIFIED_SOURCE", "SUPPORTED must link to an A/B/reliable-C source", stage="fact_check", artifact="03_fact_check.json", location=f"/claims/{index}/source_ids", entity_id=claim.get("claim_id", ""), repair_type="STAGE_RETRY" if eligible else "UPSTREAM_DATA_REQUIRED"))
        if claim.get("verification_status") == "PARTIAL" and not claim.get("source_ids"):
            errors.append(issue("FACT_PARTIAL_SOURCE", "PARTIAL needs at least one source", stage="fact_check", artifact="03_fact_check.json", entity_id=claim.get("claim_id", "")))
        for observation_id in claim.get("observation_ids", []):
            if observation_id not in observations:
                errors.append(issue("FACT_OBSERVATION_LINK", "Fact Check references a missing Observation", stage="fact_check", artifact="03_fact_check.json", location=f"/claims/{index}/observation_ids", entity_id=claim.get("claim_id", ""), repair_type="STAGE_RETRY"))
    return result(errors)


def human_gate(payload, context):
    del context
    errors = [issue("HUMAN_FEEDBACK_ID", "Feedback must have a stable feedback_id", stage="human", artifact="human/feedback.json", location=f"/feedback/{index}") for index, row in enumerate(payload.get("feedback", [])) if not row.get("feedback_id")]
    return result(errors)


def strategy_gate(payload, context):
    claims = {row.get("claim_id"): row for row in context.get("claims", [])}
    review_ids = set(context.get("review_ids", []))
    errors = []
    for index, recommendation in enumerate(payload.get("recommendations", [])):
        linked = [claims.get(value) for value in recommendation.get("claim_ids", [])]
        if not linked:
            errors.append(issue("STRATEGY_EVIDENCE", "Recommendation must link to a Claim", stage="strategy", artifact="strategy/recommendations.json", location=f"/recommendations/{index}/claim_ids", entity_id=recommendation.get("recommendation_id", "")))
        if any(row and row.get("verification_status") == "UNSUPPORTED" for row in linked):
            errors.append(issue("STRATEGY_UNSUPPORTED", "UNSUPPORTED Claim cannot support a deterministic recommendation", stage="strategy", artifact="strategy/recommendations.json", entity_id=recommendation.get("recommendation_id", "")))
        unknown = set(recommendation.get("review_ids") or []) - review_ids
        if unknown:
            errors.append(issue("STRATEGY_UNKNOWN_REVIEW_ID", "Strategy references review IDs that do not exist", stage="strategy", artifact="strategy/recommendations.json", location=f"/recommendations/{index}/review_ids", actual=sorted(unknown), repair_type="STAGE_RETRY"))
    report_model = payload.get("report_model") or {}
    for collection in ("risks", "opportunities"):
        items = report_model.get(collection)
        if not isinstance(items, list) or not items:
            errors.append(issue(
                f"STRATEGY_{collection.upper()}_REQUIRED",
                f"Strategy must provide at least one structured {collection} item",
                stage="strategy", artifact="strategy/report_model.json",
                location=f"/{collection}", repair_type="STAGE_RETRY",
            ))
            continue
        for index, item in enumerate(items):
            claim_ids = item.get("claim_ids") if isinstance(item, dict) else None
            if not item.get("label") or not (item.get("description") or item.get("rationale") or item.get("text")):
                errors.append(issue(
                    "STRATEGY_DECISION_ITEM_CONTENT", "Structured risk/opportunity needs label and description",
                    stage="strategy", artifact="strategy/report_model.json",
                    location=f"/{collection}/{index}", repair_type="STAGE_RETRY",
                ))
            linked = [claims.get(value) for value in (claim_ids or [])]
            if not linked or any(row and row.get("verification_status") == "UNSUPPORTED" for row in linked):
                errors.append(issue(
                    "STRATEGY_DECISION_ITEM_EVIDENCE", "Structured risk/opportunity must link to supported or partial Claims",
                    stage="strategy", artifact="strategy/report_model.json",
                    location=f"/{collection}/{index}/claim_ids", repair_type="STAGE_RETRY",
                ))
    return result(errors)


def report_gate(payload, context):
    claims = {row.get("claim_id") for row in context.get("claims", []) if row.get("status", "ACTIVE") == "ACTIVE"}
    required = set(context.get("required_sections", []))
    present = {row.get("section_id") for row in payload.get("paragraphs", [])}
    errors = []
    if required - present:
        errors.append(issue("REPORT_REQUIRED_SECTIONS", "Report is missing required sections", stage="report", artifact="strategy/report_model.json", expected=sorted(required), actual=sorted(present)))
    for index, paragraph in enumerate(payload.get("paragraphs", [])):
        if paragraph.get("label") == "FACT" and (not paragraph.get("claim_ids") or any(value not in claims for value in paragraph.get("claim_ids", []))):
            errors.append(issue("REPORT_FACT_CLAIM", "FACT block must reference a valid Claim", stage="report", artifact="strategy/report_model.json", location=f"/paragraphs/{index}/claim_ids"))
    if context.get("requires_scenarios") and not payload.get("scenarios"):
        errors.append(issue("REPORT_SCENARIOS_REQUIRED", "Scenario narrative requires structured scenarios", stage="report", artifact="04_report_data.json", location="/scenarios", repair_type="STAGE_RETRY"))
    return result(errors)


def dashboard_gate(payload, context):
    del context
    errors = []
    for collection in ("metrics", "time_series", "comparisons"):
        for index, item in enumerate(payload.get(collection, [])):
            if item.get("verification_status") == "UNSUPPORTED":
                errors.append(issue("DASHBOARD_UNSUPPORTED", "UNSUPPORTED data must not enter Dashboard main data", stage="dashboard", artifact="06_dashboard_data.json", location=f"/{collection}/{index}"))
    if payload.get("derived_from_markdown"):
        errors.append(issue("DASHBOARD_MARKDOWN_EXTRACTION", "Dashboard must not extract numbers from Markdown", stage="dashboard", artifact="06_dashboard_data.json"))
    return result(errors)
