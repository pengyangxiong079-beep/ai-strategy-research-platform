import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_FILE = Path(__file__).resolve().parent / "schemas" / "report_data.schema.json"
DASHBOARD_SCHEMA_FILE = (
    Path(__file__).resolve().parent / "schemas" / "dashboard_data.schema.json"
)
MONETARY_LABEL_PATTERN = re.compile(
    r"金额|价格|售价|收入|营收|成本|利润|估值|市值|GMV|revenue|price|cost|profit|valuation",
    re.IGNORECASE,
)
CURRENCY_UNIT_PATTERN = re.compile(
    r"人民币|美元|欧元|英镑|日元|港元|元|EUR|USD|CNY|RMB|GBP|JPY|HKD|[$€£¥￥]",
    re.IGNORECASE,
)
NON_MONETARY_RATE_UNIT_PATTERN = re.compile(
    r"%|％|百分点|基点|bps|percent|percentage|同比|环比|增速|变化率",
    re.IGNORECASE,
)
NON_MONETARY_OPERATIONAL_PATTERN = re.compile(
    r"收入客公里|客公里|座公里|RPK|RSK|ASK|revenue (?:passenger|seat)[- ]kilomet|available seat[- ]kilomet",
    re.IGNORECASE,
)
MARKET_PATTERN = re.compile(
    r"市场|GMV|出货量|销量|注册量|用户量|market|sales|shipment|users",
    re.IGNORECASE,
)


class ReportDataValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


def load_report_schema():
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def load_dashboard_schema():
    return json.loads(DASHBOARD_SCHEMA_FILE.read_text(encoding="utf-8"))


def iter_metrics(report_data):
    for metric in report_data.get("kpis", []):
        yield "kpis", metric
    for series in report_data.get("time_series", []):
        for metric in series.get("points", []):
            yield "time_series", metric
    for segment in report_data.get("market_segments", []):
        for metric in segment.get("metrics", []):
            yield "market_segments", metric


def is_monetary_metric(metric):
    """Return True only when a numeric metric represents a monetary amount.

    Magnitude words such as ``亿`` and operational terms such as ``收入客公里``
    do not identify a currency. Cost/revenue rate changes expressed as percentages
    are ratios rather than monetary amounts.
    """
    label = str(metric.get("label") or metric.get("dimension") or "")
    unit = str(metric.get("unit") or "")
    if CURRENCY_UNIT_PATTERN.search(unit):
        return True
    if NON_MONETARY_RATE_UNIT_PATTERN.search(unit):
        return False
    if NON_MONETARY_OPERATIONAL_PATTERN.search(f"{label} {unit}"):
        return False
    return bool(MONETARY_LABEL_PATTERN.search(label))


def validate_report_data(report_data):
    errors = []
    validator = Draft202012Validator(load_report_schema())
    for error in sorted(validator.iter_errors(report_data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")

    for section, metric in iter_metrics(report_data if isinstance(report_data, dict) else {}):
        metric_id = metric.get("metric_id") or metric.get("comparison_id") or "UNKNOWN"
        if isinstance(metric.get("value"), (int, float)):
            if is_monetary_metric(metric) and not metric.get("currency"):
                errors.append(f"{section}.{metric_id}: 金额型指标缺少currency")
            label = str(metric.get("label") or metric.get("dimension") or "")
            if MARKET_PATTERN.search(label):
                if not metric.get("period"):
                    errors.append(f"{section}.{metric_id}: 市场指标缺少period")
                if not metric.get("geography"):
                    errors.append(f"{section}.{metric_id}: 市场指标缺少geography")
    if errors:
        raise ReportDataValidationError(errors)
    return report_data


def validate_dashboard_data(dashboard_data):
    errors = []
    validator = Draft202012Validator(load_dashboard_schema())
    for error in sorted(
        validator.iter_errors(dashboard_data), key=lambda item: list(item.path)
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    if errors:
        raise ReportDataValidationError(errors)
    return dashboard_data
