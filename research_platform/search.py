"""Search language, budget and query planning without paid search APIs."""

from copy import deepcopy

from .data_acquisition.search_vocabulary import (
    build_dataset_queries,
    compact_geographies,
    entity_search_profile,
    route_industry,
)


BUDGETS = {
    "简版": {"max_rounds": 1, "max_queries": 8, "max_source_pages": 12, "max_gap_rounds": 0},
    "标准版": {"max_rounds": 2, "max_queries": 16, "max_source_pages": 25, "max_gap_rounds": 1},
    "深度版": {"max_rounds": 3, "max_queries": 30, "max_source_pages": 50, "max_gap_rounds": 2},
}


COMPARISON_DATASETS = {
    "competitor_profiles", "product_portfolios", "price_observations",
    "positioning", "channel_or_store_coverage", "customer_segments",
    "product_features", "financial_or_operational_metrics", "capabilities",
}


def comparison_cohort(scope, minimum_entities=1):
    """Return the explicit target plus only the peers required by a contract."""
    profile = entity_search_profile(scope)
    target = str(scope.get("target_entity") or profile["names"][0]).strip()
    values = [target, *(str(value).strip() for value in scope.get("competitors") or [])]
    unique = [value for value in dict.fromkeys(values) if value]
    return unique[:max(1, int(minimum_entities or 1))]


def search_languages(geography):
    value = str(geography or "").lower()
    if any(x in value for x in ("中国", "china", "湖南", "长沙")):
        return ["zh", "en"]
    if any(x in value for x in ("德国", "germany", "deutschland")):
        return ["de", "en", "zh"]
    if any(x in value for x in ("法国", "france")):
        return ["fr", "en"]
    if any(x in value for x in ("日本", "japan")):
        return ["ja", "en"]
    return ["en", "zh"]


def search_budget(depth):
    return deepcopy(BUDGETS.get(str(depth), BUDGETS["标准版"]))


def build_search_plan(scope, requirements):
    languages = search_languages(scope.get("geography"))
    budget = search_budget(scope.get("depth"))
    reserved_gap_queries = 0 if budget["max_gap_rounds"] == 0 else (4 if budget["max_gap_rounds"] == 1 else 8)
    initial_query_limit = max(1, budget["max_queries"] - reserved_gap_queries)
    profile = entity_search_profile(scope)
    entities = list(profile["names"])
    local_entities = list(profile["local_names"])
    geographies = list(compact_geographies(scope))
    primary_entity = entities[0]
    current_year = int(str(scope.get("analysis_date") or "2026")[:4])
    prior_year = current_year - 1
    competitors = scope.get("competitors") or []
    queries = []
    priority_rank = {"CRITICAL": 0, "IMPORTANT": 1}
    datasets = [item for item in requirements.get("datasets", []) if item.get("priority") in priority_rank]
    datasets.sort(key=lambda item: (priority_rank[item["priority"]], 0 if item["dataset_id"] == "operating_metrics" else 1))

    max_required_entities = max(
        (int(item.get("minimum_entities") or 1) for item in datasets if item.get("dataset_id") in COMPARISON_DATASETS),
        default=1,
    )
    discovery_entities = comparison_cohort(scope, max_required_entities)
    for entity in discovery_entities:
        language = languages[0]
        query = (
            f'"{entity}" official website annual report {prior_year}'
            if language == "en" else
            f'"{entity}" {"Geschäftsbericht" if language == "de" else "官网 年报"} {prior_year}'
        )
        queries.append({
            "round": 1, "dataset_id": "source_discovery", "language": language,
            "entity": entity, "query": query, "query_text": query,
        })
    if budget["max_rounds"] >= 2:
        for item in datasets:
            required_entities = (
                comparison_cohort(scope, item.get("minimum_entities", 1))
                if item.get("dataset_id") in COMPARISON_DATASETS
                else comparison_cohort(scope, 1)
            )
            for entity in required_entities:
                remaining = initial_query_limit - len(queries)
                if remaining <= 0:
                    break
                planned = build_dataset_queries(
                    scope, item["dataset_id"], entity=entity, languages=languages,
                    limit=min(4, remaining) if item["dataset_id"] == "operating_metrics" else 1,
                )
                for query in planned:
                    queries.append({"round": 2, "priority": item["priority"], **query})
            if len(queries) >= initial_query_limit:
                break

    # Query IDs produced independently by dataset builders are only local IDs.
    # Re-key the final auditable plan globally to prevent collision downstream.
    for index, query in enumerate(queries[:initial_query_limit], 1):
        query["query_id"] = f"Q{index:03d}"
        query["query_text"] = query.get("query_text") or query.get("query") or ""
    coverage_targets = []
    for item in datasets:
        expected = (
            comparison_cohort(scope, item.get("minimum_entities", 1))
            if item.get("dataset_id") in COMPARISON_DATASETS else comparison_cohort(scope, 1)
        )
        covered = list(dict.fromkeys(
            query.get("entity") for query in queries[:initial_query_limit]
            if query.get("dataset_id") == item["dataset_id"] and query.get("entity")
        ))
        coverage_targets.append({
            "dataset_id": item["dataset_id"], "priority": item["priority"],
            "expected_entities": expected, "query_covered_entities": covered,
            "coverage_complete": set(expected) <= set(covered),
        })
    return {
        "schema_version": "1.0",
        "languages": languages,
        "entity_name_variants": {"target": entities, "local": local_entities, "competitors": competitors},
        "geography_variants": geographies,
        "industry_route": route_industry(scope.get("industry")),
        "industry_term_variants": [scope.get("industry", "")],
        "currency_unit_variants": [scope.get("currency", "未指定")],
        "budget": budget,
        "coverage_targets": coverage_targets,
        "queries": queries[:initial_query_limit],
    }
