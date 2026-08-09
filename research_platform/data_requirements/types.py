"""Types and helpers used by the deterministic requirements registry."""

from dataclasses import asdict, dataclass, field
from typing import Any


PRIORITIES = {"CRITICAL", "IMPORTANT", "OPTIONAL"}
COMPARABILITY_DATASETS = {
    "financial_time_series", "operating_metrics", "competitors", "prices",
    "price_observations", "product_prices", "pricing", "comparable_products",
    "market_size", "business_segments", "geographies", "geographic_structure",
}
STANDARD_COMPARABILITY_FIELDS = (
    "metric_id", "unit", "currency", "geography", "period_type", "entity_scope"
)


@dataclass(frozen=True)
class DatasetRequirement:
    dataset_id: str
    priority: str
    purpose: str
    required_fields: tuple[str, ...] = ("entity", "metric", "text_value", "source_id")
    minimum_entities: int = 1
    minimum_observations_per_entity: int = 1
    minimum_periods: int = 1
    required_comparability_fields: tuple[str, ...] = (
        "geography", "period", "unit"
    )
    required_metrics: tuple[str, ...] = ()
    preferred_sources: tuple[str, ...] = ()
    fallback_sources: tuple[str, ...] = ()
    proxy_allowed: bool = False
    dashboard_components: tuple[str, ...] = ()
    component_minimums: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in list(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def requirement(
    dataset_id: str,
    priority: str,
    purpose: str,
    *,
    fields: tuple[str, ...] | None = None,
    entities: int = 1,
    per_entity: int = 1,
    periods: int = 1,
    comparable: tuple[str, ...] | None = None,
    required_metrics: tuple[str, ...] = (),
    primary: tuple[str, ...] = (),
    fallback: tuple[str, ...] = (),
    proxy: bool = False,
    components: tuple[str, ...] = (),
    component_minimums: dict[str, dict[str, Any]] | None = None,
) -> DatasetRequirement:
    if priority not in PRIORITIES:
        raise ValueError(f"Unsupported priority: {priority}")
    numeric_tokens = ("size", "growth", "financial", "price", "valuation", "margin", "cost", "revenue", "metrics", "sales", "cash_flow", "debt", "unit_economics")
    default_fields = (
        ("entity", "metric", "value", "unit", "period", "geography", "source_id")
        if any(token in dataset_id.lower() for token in numeric_tokens)
        else ("entity", "metric", "text_value", "source_id")
    )
    return DatasetRequirement(
        dataset_id=dataset_id,
        priority=priority,
        purpose=purpose,
        required_fields=fields or default_fields,
        minimum_entities=entities,
        minimum_observations_per_entity=per_entity,
        minimum_periods=periods,
        required_comparability_fields=(
            comparable
            if comparable is not None
            else (STANDARD_COMPARABILITY_FIELDS if dataset_id in COMPARABILITY_DATASETS else ())
        ),
        required_metrics=required_metrics,
        preferred_sources=primary,
        fallback_sources=fallback,
        proxy_allowed=proxy,
        dashboard_components=components,
        component_minimums=component_minimums or {},
    )


COMMON_PRIMARY = (
    "政府或监管机构", "正式财报或交易所文件", "公司官方公告", "官方产品或价格页面"
)
COMMON_FALLBACK = ("行业协会", "高质量研究机构", "可信媒体实测", "可识别日期的平台公开页面")
