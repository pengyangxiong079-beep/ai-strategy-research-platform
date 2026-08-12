"""Deterministic dataset-level coverage and gap calculations."""

from collections import Counter, defaultdict
import re

from .data_acquisition.search_vocabulary import build_dataset_queries


COMPARABILITY_DATASETS = {
    "financial_time_series", "operating_metrics", "competitors", "prices",
    "price_observations", "product_prices", "pricing", "comparable_products",
    "market_size", "business_segments", "geographies", "geographic_structure",
}
NON_COMPARABLE_DATASETS = {
    "company_profile", "strategic_initiatives", "risks", "capabilities",
    "regulations", "opportunities", "qualitative_findings",
}


def _filled(value):
    return value is not None and str(value).strip() not in {"", "N/A", "UNKNOWN"}


def _recommended_queries(dataset_id, entity, field, scope):
    schema_fields = {
        "entity", "value", "text_value", "unit", "currency", "geography",
        "period", "source_id", "channel", "price_type", "metric_definition",
        "observation", "dataset", "data",
    }
    return build_dataset_queries(
        scope, dataset_id, entity=entity or None,
        missing_field=field if field not in {"metric", "data"} else None,
        missing_metric=field if field not in schema_fields else None,
        limit=5,
    )


def _valid_row(row, source_by_id):
    if row.get("verification_status") == "UNSUPPORTED" or row.get("temporal_status") == "SUPERSEDED":
        return False
    if not _filled(row.get("dataset_id")) or not _filled(row.get("entity")) or not _filled(row.get("metric")):
        return False
    if not _filled(row.get("source_id")) or row.get("source_id") not in source_by_id:
        return False
    return row.get("value") is not None or _filled(row.get("text_value"))


def _comparison_key(row):
    values = (
        row.get("metric_id") or row.get("metric"), row.get("unit"), row.get("currency"),
        row.get("geography"), row.get("period_type"), row.get("entity_scope"),
    )
    if row.get("dataset_id") in {"prices", "price_observations", "product_prices", "pricing", "comparable_products"}:
        values = (*values, row.get("period"), row.get("channel"), row.get("price_type"))
    return tuple(str(value or "N/A").strip().lower() for value in values)


def _comparability_rate(dataset_id, rows):
    if dataset_id in NON_COMPARABLE_DATASETS or dataset_id not in COMPARABILITY_DATASETS:
        return None
    numeric = [row for row in rows if row.get("value") is not None]
    if not numeric:
        return 0.0
    # Score consistency within each metric, never Revenue against EBIT/Passengers/Load Factor.
    by_metric = defaultdict(list)
    for row in numeric:
        # Fiscal-year and quarterly series are separate legitimate comparison scopes.
        partition = (
            str(row.get("metric_id") or row.get("metric") or "UNKNOWN"),
            str(row.get("period_type") or "UNKNOWN"),
            str(row.get("entity_scope") or "ENTITY"),
        )
        by_metric[partition].append(row)
    comparable = 0
    for metric_rows in by_metric.values():
        groups = Counter(_comparison_key(row) for row in metric_rows)
        comparable += max(groups.values()) if groups else 0
    return comparable / len(numeric)


def _series_period_count(rows):
    groups = defaultdict(set)
    for row in rows:
        if row.get("value") is None or not _filled(row.get("period")):
            continue
        key = (
            row.get("metric_id") or row.get("metric"), row.get("unit"), row.get("currency"),
            row.get("geography"), row.get("period_type"), row.get("entity_scope"), row.get("entity"),
        )
        groups[key].add(row.get("period"))
    return max((len(periods) for periods in groups.values()), default=0)


def _comparable_entity_count(rows):
    groups = defaultdict(set)
    for row in rows:
        if row.get("value") is not None:
            groups[_comparison_key(row)].add(row.get("entity"))
    return max((len(entities) for entities in groups.values()), default=0)


def evaluate_sufficiency(requirements, observations, sources, scope, *, gap_rounds_completed=0, stop_reason=""):
    source_by_id = {item.get("source_id"): item for item in sources}
    datasets = []
    critical_gaps = []
    topic_entity = re.split(r"在|进入|公司战略|的竞品|行业分析", str(scope.get("topic", "")), maxsplit=1)[0].strip()
    target_entities = [scope.get("target_entity") or topic_entity, *(scope.get("competitors") or [])]
    target_entities = [item for item in dict.fromkeys(target_entities) if item]
    for req in requirements.get("datasets", []):
        rows = [row for row in observations if row.get("dataset_id") == req["dataset_id"] and _valid_row(row, source_by_id)]
        entities = sorted({row.get("entity") for row in rows if _filled(row.get("entity"))})
        periods = sorted({row.get("period") for row in rows if _filled(row.get("period"))})
        fields = list(dict.fromkeys([*(req.get("required_fields") or []), *(req.get("required_comparability_fields") or [])]))
        completeness = {field: (sum(_filled(row.get(field)) for row in rows) / len(rows) if rows else 0.0) for field in fields}
        comparability_rate = _comparability_rate(req["dataset_id"], rows)
        counts = Counter(row.get("entity") for row in rows if _filled(row.get("entity")))
        entity_requirement_met = len(entities) >= req.get("minimum_entities", 0)
        per_entity_met = bool(entities) and sum(count >= req.get("minimum_observations_per_entity", 0) for count in counts.values()) >= req.get("minimum_entities", 0)
        minimum_periods = req.get("minimum_periods", 0)
        periods_met = (
            _series_period_count(rows) >= minimum_periods
            if minimum_periods > 1 else len(periods) >= minimum_periods
        )
        fields_met = all(completeness.get(field, 0) >= 0.9 for field in req.get("required_fields") or [])
        present_metrics = {str(row.get("metric_id") or row.get("metric") or "") for row in rows}
        missing_metrics = [metric for metric in req.get("required_metrics") or [] if metric not in present_metrics]
        metrics_met = not missing_metrics
        if entity_requirement_met and per_entity_met and periods_met and fields_met and metrics_met:
            status = "PASS"
        elif rows:
            status = "PARTIAL"
        else:
            status = "INSUFFICIENT"
        readiness = {}
        series_periods = _series_period_count(rows)
        comparable_entities = _comparable_entity_count(rows)
        numeric_observations = sum(row.get("value") is not None for row in rows)
        for component in req.get("dashboard_components") or []:
            threshold = (req.get("component_minimums") or {}).get(component, {})
            ready = len(rows) > 0 and len(entities) >= threshold.get("entities", req.get("minimum_entities", 1))
            ready = ready and numeric_observations >= threshold.get("numeric_observations", 0)
            ready = ready and series_periods >= threshold.get("periods_per_metric", 0)
            if threshold.get("requires_comparability"):
                ready = ready and comparable_entities >= threshold.get("entities", req.get("minimum_entities", 1))
            if "comparability_rate" in threshold:
                ready = ready and comparability_rate is not None and comparability_rate >= threshold["comparability_rate"]
            readiness[component] = bool(ready)
        gaps = []
        missing_target_entities = []
        if req.get("priority") == "CRITICAL" and target_entities and req["dataset_id"] in {"competitor_profiles", "product_portfolios", "price_observations", "positioning", "channel_or_store_coverage"}:
            missing_target_entities = [entity for entity in target_entities if counts.get(entity, 0) < req.get("minimum_observations_per_entity", 1)]
        for entity in missing_target_entities:
            needed = max(0, req.get("minimum_observations_per_entity", 1) - counts.get(entity, 0))
            gaps.append({"gap_id": f"G_{req['dataset_id']}_{len(gaps)+1:03d}", "entity": entity, "missing_field": "observation", "needed_observations": needed, "recommended_queries": _recommended_queries(req["dataset_id"], entity, "observation", scope)})
        for field in req.get("required_fields") or []:
            rate = completeness.get(field, 0.0)
            if rate < 0.9 and rows:
                gaps.append({"gap_id": f"G_{req['dataset_id']}_{len(gaps)+1:03d}", "entity": "", "missing_field": field, "needed_observations": sum(not _filled(row.get(field)) for row in rows), "recommended_queries": _recommended_queries(req["dataset_id"], "", field, scope)})
        for metric_id in missing_metrics:
            gaps.append({"gap_id": f"G_{req['dataset_id']}_{len(gaps)+1:03d}", "entity": "", "missing_field": "metric", "missing_metric": metric_id, "needed_observations": 1, "recommended_queries": _recommended_queries(req["dataset_id"], "", metric_id, scope)})
        if not rows:
            gaps.append({"gap_id": f"G_{req['dataset_id']}_001", "entity": "", "missing_field": "dataset", "needed_observations": req.get("minimum_entities", 1) * req.get("minimum_observations_per_entity", 1), "recommended_queries": _recommended_queries(req["dataset_id"], "", "data", scope)})
        grade_distribution = Counter(source_by_id.get(row.get("source_id"), {}).get("source_grade", row.get("source_grade", "UNKNOWN")) for row in rows)
        item = {
            "dataset_id": req["dataset_id"], "priority": req["priority"], "status": status,
            "entity_count": len(entities), "entities": entities, "observation_count": len(rows),
            "periods": periods, "required_entity_count": req.get("minimum_entities", 0),
            "required_observations_per_entity": req.get("minimum_observations_per_entity", 0),
            "field_completeness": {key: round(value, 3) for key, value in completeness.items()},
            "comparability_rate": round(comparability_rate, 3) if comparability_rate is not None else None,
            "comparability_status": "N/A" if comparability_rate is None else "CALCULATED",
            "source_count": len({row.get("source_id") for row in rows if row.get("source_id")}),
            "source_grade_distribution": dict(grade_distribution),
            "dashboard_readiness": readiness, "gaps": gaps,
            "auto_gap_eligible": req["priority"] in {"CRITICAL", "IMPORTANT"},
        }
        datasets.append(item)
        if req["priority"] == "CRITICAL" and status != "PASS":
            critical_gaps.extend({**gap, "dataset_id": req["dataset_id"]} for gap in gaps)
    gap_candidates = [
        {**gap, "dataset_id": item["dataset_id"], "priority": item["priority"]}
        for item in datasets if item["priority"] in {"CRITICAL", "IMPORTANT"} and item["status"] != "PASS"
        for gap in item.get("gaps") or []
    ]
    critical_statuses = [item["status"] for item in datasets if item["priority"] == "CRITICAL"]
    overall = "PASS" if critical_statuses and all(status == "PASS" for status in critical_statuses) else ("INSUFFICIENT" if "INSUFFICIENT" in critical_statuses else "PARTIAL")
    return {
        "schema_version": "1.0", "analysis_type": requirements.get("analysis_type", "GENERIC_STRATEGY"),
        "observation_count": sum(item["observation_count"] for item in datasets),
        "overall_status": overall, "gap_search_rounds_completed": gap_rounds_completed,
        "search_stop_reason": stop_reason, "datasets": datasets, "critical_gaps": critical_gaps,
        "gap_search_candidates": gap_candidates,
    }


def build_gap_search_plan(sufficiency, search_plan, *, include_optional=False):
    gaps = list(sufficiency.get("gap_search_candidates") or sufficiency.get("critical_gaps") or [])
    if include_optional:
        gaps.extend(
            {**gap, "dataset_id": item["dataset_id"], "priority": "OPTIONAL"}
            for item in sufficiency.get("datasets") or [] if item.get("priority") == "OPTIONAL" and item.get("status") != "PASS"
            for gap in item.get("gaps") or []
        )
    queries, seen = [], set()
    for gap in gaps:
        for raw_query in gap.get("recommended_queries") or []:
            query_spec = dict(raw_query) if isinstance(raw_query, dict) else {"query": str(raw_query), "query_text": str(raw_query)}
            query = query_spec.get("query_text") or query_spec.get("query") or ""
            if not query or query in seen:
                continue
            seen.add(query)
            queries.append({
                **query_spec,
                "query_id": query_spec.get("query_id") or f"GQ_{len(queries) + 1:03d}",
                "gap_id": gap.get("gap_id") or query_spec.get("gap_id") or "",
                "dataset_id": gap.get("dataset_id") or query_spec.get("dataset_id") or "",
                "priority": gap.get("priority", "CRITICAL"),
                "entity": gap.get("entity", "") or query_spec.get("entity", ""),
                "missing_field": gap.get("missing_field", "") or query_spec.get("missing_field", ""),
                "language": query_spec.get("language") or "unknown",
                "domain_filter": query_spec.get("domain_filter") or "",
                "source_type": query_spec.get("source_type") or "",
                "file_type": query_spec.get("file_type") or "",
                "geography": query_spec.get("geography") or "",
                "period": query_spec.get("period") or "",
                "metric": query_spec.get("metric") or "",
                "gap_reason": query_spec.get("gap_reason") or gap.get("missing_field") or "dataset coverage",
                "query": query, "query_text": query,
            })
    remaining = max(0, search_plan.get("budget", {}).get("max_queries", 0) - len(search_plan.get("queries") or []))
    return {"schema_version": "1.0", "round": sufficiency.get("gap_search_rounds_completed", 0) + 1, "only_missing_data": True, "queries": queries[:remaining], "existing_query_count": len(search_plan.get("queries") or []), "stop_if_access_blocked": True}
