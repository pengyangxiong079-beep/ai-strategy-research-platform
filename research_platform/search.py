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
    discovery = [
        (languages[0], f'"{local_entities[0]}" official corporate website'),
        ("en", f'"{primary_entity}" annual report {prior_year} investor relations filetype:pdf'),
        ("de" if "de" in languages else languages[0], f'"{local_entities[0]}" {"Geschäftsbericht" if "de" in languages else "官方数据"} {prior_year}'),
    ]
    for language, query in discovery:
        queries.append({"round": 1, "dataset_id": "source_discovery", "language": language, "query": query})
    if budget["max_rounds"] >= 2:
        priority_rank = {"CRITICAL": 0, "IMPORTANT": 1}
        datasets = [item for item in requirements.get("datasets", []) if item.get("priority") in priority_rank]
        # Operational evidence is decision-critical for company/industry work even if registered IMPORTANT.
        datasets.sort(key=lambda item: (priority_rank[item["priority"]], 0 if item["dataset_id"] == "operating_metrics" else 1))
        for item in datasets:
            remaining = initial_query_limit - len(queries)
            if remaining <= 0:
                break
            planned = build_dataset_queries(
                scope, item["dataset_id"], languages=languages,
                limit=min(5 if item["dataset_id"] == "operating_metrics" else 2, remaining),
            )
            for query in planned:
                queries.append({"round": 2, "dataset_id": item["dataset_id"], **query})
    return {
        "schema_version": "1.0",
        "languages": languages,
        "entity_name_variants": {"target": entities, "local": local_entities, "competitors": competitors},
        "geography_variants": geographies,
        "industry_route": route_industry(scope.get("industry")),
        "industry_term_variants": [scope.get("industry", "")],
        "currency_unit_variants": [scope.get("currency", "未指定")],
        "budget": budget,
        "queries": queries[:initial_query_limit],
    }
