from .base import StageContract
from .validators import data_gate
CONTRACT = StageContract("data", ("00_analysis_scope.json",), "observations.schema.json", ("scope_complete",), ("critical_assessed",), ("critical_insufficient", "missing_source"), ("optional_insufficient",), "UPSTREAM_DATA_REQUIRED", ("research", "review", "fact_check", "human", "strategy", "report", "dashboard", "quality"), data_gate)
