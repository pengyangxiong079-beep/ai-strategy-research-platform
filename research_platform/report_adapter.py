"""Use verified observations to enrich the report's structured data locally."""

from collections import defaultdict
import hashlib
from statistics import median


GRADE_MAP = {"GRADE_A": "A", "GRADE_B": "B", "GRADE_C": "C", "GRADE_D": "D", "GRADE_E": "D", "UNKNOWN": "N/A"}
VALUE_TYPE_MAP = {"HISTORICAL": "ACTUAL", "PROXY": "ESTIMATE"}
METRIC_LABELS = {
    "available_seat_km": "可用座公里（ASK）", "revenue_passenger_km": "收入客公里（RPK）",
    "passenger_load_factor": "客座率", "passenger_count": "旅客量", "flight_count": "航班量",
    "yield": "收益率（Yield）", "rask": "单位收入（RASK）", "cask_ex_fuel": "非燃油及排放CASK",
    "punctuality": "准点率", "regularity": "航班正常率", "employee_count": "员工人数",
    "specific_co2_emissions": "单位二氧化碳排放", "adjusted_ebit_margin": "Adjusted EBIT利润率",
}


def _fact_ids(rows):
    return list(dict.fromkeys(fact_id for row in rows for fact_id in row.get("source_fact_ids", []) if str(fact_id).startswith("F")))


def _metric_payload(row):
    metric_id = str(row.get("metric_id") or row.get("metric") or row.get("observation_id"))
    confidence = str(row.get("confidence") or "MEDIUM").upper()
    if confidence not in {"HIGH", "MEDIUM", "LOW"}:
        confidence = "MEDIUM"
    return {
        "metric_id": f"OBS_{row.get('observation_id')}",
        "label": METRIC_LABELS.get(metric_id, metric_id),
        "value": row.get("value"),
        "unit": row.get("unit") or None,
        "currency": row.get("currency") or None,
        "geography": row.get("geography") or None,
        "period": row.get("period") or None,
        "value_type": VALUE_TYPE_MAP.get(str(row.get("value_type") or "UNKNOWN"), str(row.get("value_type") or "UNKNOWN")),
        "metric_definition": row.get("metric_definition") or metric_id,
        "channel_scope": row.get("channel") or None,
        "entity_scope": row.get("entity_scope") or row.get("entity") or None,
        "comparability_group": row.get("comparability_group") or "",
        "source_fact_ids": _fact_ids([row]),
        "source_observation_ids": [row.get("observation_id")] if row.get("observation_id") else [],
        "source_grade": GRADE_MAP.get(row.get("source_grade"), "N/A"),
        "confidence": confidence,
    }


def enrich_report_data(report_data, observations, sufficiency):
    """Add only supported/partial observations; never mine narrative Markdown."""
    if not isinstance(report_data, dict):
        return report_data
    usable = [row for row in observations if row.get("verification_status") in {"SUPPORTED", "PARTIAL"} and row.get("source_fact_ids")]
    gaps = []
    for dataset in sufficiency.get("datasets", []):
        if dataset.get("status") == "PASS":
            continue
        comparability = "N/A" if dataset.get("comparability_rate") is None else f"{dataset['comparability_rate']:.0%}"
        required_action = (
            "OPTIONAL数据不触发自动补搜；如确有决策需要，可在Data Coverage主动选择补充可选数据。"
            if dataset.get("priority") == "OPTIONAL"
            else "可使用Data Coverage中的定向补搜；报告按现有证据降级展示。"
        )
        gaps.append({"gap_id": f"DATA_{dataset['dataset_id']}", "label": f"{dataset['dataset_id']}数据{dataset['status']}", "reason": f"Observation {dataset.get('observation_count', 0)}条，可比率{comparability}；未满足全部最低要求。", "required_action": required_action})
    report_data["data_gaps"] = [
        item for item in report_data.get("data_gaps", [])
        if not str(item.get("gap_id") or "").startswith("DATA_")
    ]
    existing_gap_ids = {item.get("gap_id") for item in report_data["data_gaps"]}
    report_data["data_gaps"].extend(item for item in gaps if item["gap_id"] not in existing_gap_ids)
    # Rebuild generated series so reruns cannot retain stale scope/geography groupings.
    report_data["time_series"] = [
        item for item in report_data.get("time_series", [])
        if not str(item.get("series_id") or "").startswith("OBS_TS_")
    ]
    # Create time series only within one metric, entity scope, geography, unit, currency and period type.
    series_groups = defaultdict(list)
    for row in usable:
        if row.get("value") is None or row.get("dataset_id") not in {
            "operating_metrics", "financial_time_series", "historical_growth",
            "forecast_growth", "market_size", "geographies", "geographic_structure",
        }:
            continue
        key = (
            row.get("dataset_id"), row.get("metric_id") or row.get("metric"), row.get("entity"),
            row.get("entity_scope"), row.get("geography"), row.get("unit"), row.get("currency"),
            row.get("period_type"),
        )
        series_groups[key].append(row)
    existing_series = {item.get("series_id") for item in report_data.get("time_series", [])}
    for key, rows in series_groups.items():
        periods = {}
        for row in rows:
            if row.get("period") and row.get("source_fact_ids"):
                periods.setdefault(row["period"], row)
        if len(periods) < 2:
            continue
        dataset_id, metric_id, entity, entity_scope, geography, unit, currency, period_type = key
        suffix = hashlib.sha256("|".join(str(value or "") for value in key).encode("utf-8")).hexdigest()[:10]
        series_id = f"OBS_TS_{suffix}"
        if series_id in existing_series:
            continue
        report_data.setdefault("time_series", []).append({
            "series_id": series_id,
            "label": f"{entity} · {METRIC_LABELS.get(metric_id, metric_id)}",
            "chart_type": "LINE",
            "points": [_metric_payload(periods[period]) for period in sorted(periods)],
            "source_observation_ids": [periods[period].get("observation_id") for period in sorted(periods)],
            "comparability_note": "Only identical metric definition, unit, currency, geography, period type and entity scope are joined.",
        })
        existing_series.add(series_id)
    # Generate comparable medians only when at least two entities share one strict comparability group.
    groups = defaultdict(list)
    for row in usable:
        if row.get("value") is not None:
            groups[(row.get("dataset_id"), row.get("metric"), row.get("comparability_group"))].append(row)
    existing_comparisons = {item.get("comparison_id") for item in report_data.get("competitor_comparisons", [])}
    for (dataset_id, metric, group), rows in groups.items():
        by_entity = defaultdict(list)
        for row in rows:
            by_entity[row.get("entity")].append(row)
        if len(by_entity) < 2:
            continue
        suffix = hashlib.sha256(f"{metric}|{group}".encode("utf-8")).hexdigest()[:8]
        comparison_id = f"OBS_{dataset_id}_{suffix}"
        if comparison_id in existing_comparisons:
            continue
        sample = rows[0]
        report_data.setdefault("competitor_comparisons", []).append({
            "comparison_id": comparison_id, "metric_id": comparison_id,
            "entities": list(by_entity), "metric": metric or dataset_id,
            "geography": sample.get("geography") or None, "period": sample.get("period") or None,
            "unit": sample.get("unit") or None, "currency": sample.get("currency") or None,
            "comparable": True, "is_comparable": True, "comparability_issues": [],
            "metric_definition": sample.get("metric_definition") or metric or dataset_id,
            "channel_scope": sample.get("channel") or None, "entity_scope": "同一comparability_group",
            "comparison_basis": "同一地区、期间、单位、币种、渠道与价格类型的Observation中位数",
            "ranking_claim": False, "source_fact_ids": _fact_ids(rows),
            "source_observation_ids": [row.get("observation_id") for row in rows if row.get("observation_id")],
            "values": [{"entity": entity, "value": median([r["value"] for r in entity_rows])} for entity, entity_rows in by_entity.items()],
        })
    report_data.setdefault("_meta", {})["observation_ids"] = [row.get("observation_id") for row in observations if row.get("observation_id")]
    report_data["_meta"]["used_observation_ids"] = [row.get("observation_id") for row in usable if row.get("observation_id")]
    coverage_periods = sorted({row.get("period") for row in usable if row.get("period")})
    exported_periods = sorted({point.get("period") for series in report_data.get("time_series", []) for point in series.get("points", []) if point.get("period")})
    report_data["_meta"]["coverage_periods"] = coverage_periods
    report_data["_meta"]["exported_time_series_periods"] = exported_periods
    report_data["_meta"]["time_series_exclusions"] = [
        {"period": period, "exclusion_reason": "No comparable multi-period series after metric-definition and scope partitioning"}
        for period in coverage_periods if period not in exported_periods
    ]
    return report_data
