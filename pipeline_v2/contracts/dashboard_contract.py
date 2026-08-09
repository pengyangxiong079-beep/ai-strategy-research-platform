from .base import StageContract
from .validators import dashboard_gate
CONTRACT = StageContract("dashboard", ("04_report_data.json", "data/observations.json", "quality/summary.json"), "dashboard_data.schema.json", ("quality_gate_passed", "report_hash_current"), ("structured_only",), ("unsupported_metric", "markdown_extraction", "stale_report_hash"), ("partial_metric",), "LOCAL_REPAIRABLE", (), dashboard_gate)
