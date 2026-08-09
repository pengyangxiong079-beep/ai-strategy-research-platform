from .types import COMMON_FALLBACK, COMMON_PRIMARY, requirement

REQUIREMENTS = tuple(
    requirement(
        x, "CRITICAL", f"公司战略核心数据：{x}",
        periods=3 if x == "financial_time_series" else 1,
        primary=COMMON_PRIMARY, fallback=COMMON_FALLBACK,
        components=("TimeSeriesChart",) if x == "financial_time_series" else (),
        component_minimums={"TimeSeriesChart": {"periods_per_metric": 3}} if x == "financial_time_series" else {},
    )
    for x in ("company_profile", "financial_time_series", "business_segments", "products_or_services", "geographic_structure", "strategic_initiatives")
) + tuple(
    requirement(
        x, "IMPORTANT", f"公司诊断数据：{x}", proxy=x in {"capabilities", "risks"},
        components=("OperatingMetricSummary", "OperatingMetricsTimeSeries") if x == "operating_metrics" else (),
        required_metrics=(
            "passenger_count", "flight_count", "available_seat_km", "revenue_passenger_km",
            "passenger_load_factor", "yield", "rask", "cask_ex_fuel",
        ) if x == "operating_metrics" else (),
        component_minimums={
            "OperatingMetricSummary": {"numeric_observations": 1},
            "OperatingMetricsTimeSeries": {"periods_per_metric": 2},
        } if x == "operating_metrics" else {},
    )
    for x in ("market_position", "competitors", "operating_metrics", "capabilities", "investments", "risks")
) + tuple(
    requirement(x, "OPTIONAL", f"公司补充数据：{x}", proxy=True)
    for x in ("employee_metrics", "ESG_metrics", "detailed_unit_economics")
)
